"""Offline evidence-driven finalization without live Gemini traffic."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from google.genai import _api_client, _common, models as sdk_models, types
import pytest

from backend.agent.prompts import FINAL_REPORT_INSTRUCTION
from backend.agent.schemas import AgentLimits
from backend.agent.service import CORE_FIELDS, RequestState, _normal_evidence_ready
from backend.storage import InspectionStorageBase
from tests.test_agent_service import report_response, call_response, normal_responses, report_payload, service_for, text_response, with_quality_facts
from tests.test_agent_tools import make_log, make_record
from tests.agent_error_fixtures import error_logs, error_record, with_error_facts
from tests.agent_deadline_control import ControlledDeadlines


@pytest.fixture(autouse=True)
def no_live_requests():
    with patch("backend.agent.service.genai.Client", side_effect=AssertionError("Offline only")), \
         patch.object(_api_client.BaseApiClient, "request", side_effect=AssertionError("Offline only")) as sync_request, \
         patch.object(_api_client.BaseApiClient, "async_request", side_effect=AssertionError("Offline only")) as async_request:
        yield
        sync_request.assert_not_called()
        async_request.assert_not_called()


@pytest.fixture
def storage():
    instance = Mock(spec=InspectionStorageBase)
    instance.get_inspection.return_value = make_record()
    instance.get_logs.return_value = [make_log()]
    instance.list_inspections.return_value = [make_record()]
    return instance


def test_normal_result_finishes_without_optional_tools_or_readiness_request(storage):
    service, generator = service_for(storage, normal_responses())
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    assert generator.await_count == 2
    assert result.tools_used == ["get_inspection_result"]
    assert len(result.observed_facts) == len(CORE_FIELDS)
    assert len(result.tool_execution_trace) == 1
    storage.get_inspection.assert_called_once_with("INSP-000001")
    storage.get_logs.assert_not_called()
    storage.list_inspections.assert_not_called()
    final = generator.call_args_list[1].kwargs
    assert final["config"].tools is None
    assert final["config"].response_mime_type == "application/json"
    assert FINAL_REPORT_INSTRUCTION in final["config"].system_instruction
    assert [content.role for content in final["contents"]] == ["user"]
    envelope = json.loads(final["contents"][0].parts[0].text)
    assert {entry["evidence_id"] for entry in envelope["catalog"]} == {"E0001"}


@pytest.mark.parametrize("field", CORE_FIELDS)
def test_missing_core_evidence_never_triggers_normal_fast_path(field):
    snapshot = {name: getattr(make_record(), name) for name in CORE_FIELDS}
    snapshot[field] = None
    assert not _normal_evidence_ready(RequestState("INSP-000001", snapshot=snapshot))


@pytest.mark.parametrize("field,value", [("status", "FAILED"), ("result", "NG"),
    ("image_quality_status", "WARNING_LOW_BRIGHTNESS"), ("defect_detection_status", "FAILED"),
    ("final_result", "REINSPECT"), ("final_reason_code", "UNKNOWN_STATE_COMBINATION")])
def test_non_normal_core_evidence_keeps_investigation_path(field, value):
    snapshot = {name: getattr(make_record(), name) for name in CORE_FIELDS}
    snapshot[field] = value
    assert not _normal_evidence_ready(RequestState("INSP-000001", snapshot=snapshot))


@pytest.mark.parametrize("score,threshold", [(None, 34.1442), (32.0, None), (35.0, 34.1442),
    (True, 34.1442), (float("nan"), 34.1442)])
def test_missing_or_inconsistent_model_measurements_do_not_shortcut(score, threshold):
    snapshot = {name: getattr(make_record(), name) for name in CORE_FIELDS}
    snapshot.update(anomaly_score=score, decision_threshold=threshold)
    assert not _normal_evidence_ready(RequestState("INSP-000001", snapshot=snapshot))


@pytest.mark.parametrize("scenario,additional_tool", [("warning", "analyze_image_quality"), ("failed", "get_execution_logs")])
def test_warning_quality_and_failure_log_investigations_remain_available(storage, scenario, additional_tool):
    changes = {"image_quality_status": "WARNING_LOW_BRIGHTNESS", "final_result": "REINSPECT", "final_reason_code": "IMAGE_QUALITY_WARNING"}
    summary = "REINSPECTION_REQUIRED"
    if scenario == "failed":
        changes = {"status": "FAILED", "result": "UNKNOWN", "image_quality_status": "ERROR",
                   "defect_detection_status": "SKIPPED", "final_result": "ERROR", "final_reason_code": "INSPECTION_FAILED"}
        summary = "INSPECTION_FAILED"
        storage.get_logs.return_value = [make_log(event_code="IMAGE_LOAD_FAILED")]
    record = make_record(**changes)
    if scenario == "failed":
        record = error_record()
        storage.get_logs.return_value = error_logs()
    storage.get_inspection.return_value = record
    payload = report_payload(record, summary)
    payload["recommended_checks"] = [{"check_code": "MANUAL_REINSPECTION", "evidence_refs": ["F0005"]}]
    field = "/data/image_quality_status" if scenario == "warning" else "/data/0/event_code"
    payload["observed_facts"].append({"fact_id": "F0007", "evidence_id": "E0002", "source_tool": additional_tool,
        "source_field": field, "observed_value": "WARNING_LOW_BRIGHTNESS" if scenario == "warning" else "IMAGE_LOAD_FAILED",
        "source_event": None if scenario == "warning" else "IMAGE_LOAD_FAILED"})
    if scenario == "warning":
        payload = with_quality_facts(payload, record)
    else:
        payload = with_error_facts(payload, record)
    responses = [call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})),
                 call_response((additional_tool, {"inspection_id": "INSP-000001"})),
                 report_response(payload)]
    service, generator = service_for(storage, responses)
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    assert result.tools_used == ["get_inspection_result", additional_tool, *(["get_inspection_history"] if scenario == "warning" else [])]
    assert [entry.round_number for entry in result.tool_execution_trace] == ([1, 2, 2] if scenario == "warning" else [1, 2])
    if scenario == "warning":
        history = result.tool_execution_trace[-1]
        assert history.origin == "BACKEND_POLICY" and history.executed and history.success
        assert history.evidence_id == "E0003"
    assert generator.await_count == 3
    assert result.observed_facts[-1].evidence_id == "E0002"


def test_fast_path_report_serializes_independently_of_native_function_history(storage):
    first = call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}), signature=bytes(range(256)))
    service, generator = service_for(storage, [first, report_response(report_payload())])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    arguments = generator.call_args_list[1].kwargs
    parameters = types._GenerateContentParameters(**arguments)
    body = sdk_models._GenerateContentParameters_to_mldev(SimpleNamespace(vertexai=False), parameters)
    body = _common.encode_unserializable_types(_common.convert_to_dict(body))
    assert "tools" not in body
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert [content["role"] for content in body["contents"]] == ["user"]
    assert set(body["contents"][0]["parts"][0]) == {"text"}
    envelope = json.loads(body["contents"][0]["parts"][0]["text"])
    assert {entry["evidence_id"] for entry in envelope["catalog"]} == {"E0001"}
    assert first.candidates[0].content.parts[0].thought_signature == bytes(range(256))
    json.dumps(body, allow_nan=False)


def test_normal_fast_path_does_not_bypass_evidence_validation(storage):
    payload = report_payload()
    payload["observed_facts"][0]["observed_value"] = "FAILED"
    service, generator = service_for(storage, normal_responses(payload))
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "EVIDENCE_MISMATCH"
    assert result.observed_facts == []
    assert generator.await_count == 2
    assert result.tool_execution_trace[0].executed and result.tool_execution_trace[0].success


@pytest.mark.parametrize("kind,error", [("model", "GEMINI_TIMEOUT"), ("overall", "AGENT_TIMEOUT")])
def test_final_request_keeps_model_and_overall_deadlines(storage, kind, error):
    service, generator = service_for(storage, [], AgentLimits())

    async def run():
        with ControlledDeadlines() as deadlines:
            async def generate(**kwargs):
                if kwargs["config"].response_mime_type == "application/json":
                    await deadlines.expire(kind)
                return call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}))
            generator.side_effect = generate
            return await service.analyze("INSP-000001")

    result = asyncio.run(run())
    assert result.error_code == error
    assert generator.await_count == 2
    assert result.tools_used == ["get_inspection_result"]
    assert len(result.tool_execution_trace) == 1


def test_fast_path_request_states_and_token_usage_are_isolated(storage):
    first_record = make_record()
    second_record = make_record(inspection_id="INSP-000002")
    storage.get_inspection.side_effect = [first_record, second_record]
    second_payload = report_payload(second_record)
    second_payload["inspection_id"] = "INSP-000002"
    first_final = report_response(report_payload(first_record))
    second_final = report_response(second_payload)
    first_final.usage_metadata = types.GenerateContentResponseUsageMetadata(prompt_token_count=20, candidates_token_count=10, total_token_count=30)
    second_final.usage_metadata = types.GenerateContentResponseUsageMetadata(prompt_token_count=30, candidates_token_count=20, total_token_count=50)
    service, generator = service_for(storage, [call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})), first_final,
        call_response(("get_inspection_result", {"inspection_id": "INSP-000002"})), second_final])

    async def analyze_both():
        return await service.analyze("INSP-000001"), await service.analyze("INSP-000002")

    first, second = asyncio.run(analyze_both())
    assert first.analysis_status == second.analysis_status == "COMPLETED"
    assert generator.await_count == 4
    assert [entry.total_token_count for entry in first.token_usage] == [15, 30]
    assert [entry.total_token_count for entry in second.token_usage] == [15, 50]
    assert [entry.round_number for entry in first.token_usage] == [1, 2]
    assert [entry.round_number for entry in second.token_usage] == [1, 2]
    assert first.tool_execution_trace[0] is not second.tool_execution_trace[0]
    assert first.tool_execution_trace[0].arguments != second.tool_execution_trace[0].arguments
