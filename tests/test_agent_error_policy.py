"""Offline required-error evidence and report coverage, with no external transport."""

import asyncio
import copy
import json
from types import SimpleNamespace

from google.genai import _common, models, types
import httpx
import pytest

from backend.agent.error_policy import error_report_scope, error_required_facts, image_load_failure_evidence_ready
from backend.agent.reporting import build_catalog, convert_simple_report
from backend.agent.schemas import AgentLimits, DiagnosisDraft
from backend.agent.service import AgentFailure
from tests.agent_error_fixtures import error_logs, error_record
from tests.test_agent_service import call_response, service_for, text_response
from tests.test_agent_t05_preflight import (
    collect_state, failed_storage, harness, prohibit_external_calls, report_for_catalog, responses_with_logs,
)
from tests.test_agent_tools import make_log, make_record


def draft_for(state):
    catalog = build_catalog(state)
    payload = report_for_catalog([entry.__dict__ for entry in catalog.entries])
    return convert_simple_report(json.dumps(payload), state, catalog)


def verify(service, state, draft):
    return service._verify_report(DiagnosisDraft.model_validate(draft.model_dump()), state, "gemini-mock")


def test_required_error_evidence_is_actual_and_state_is_unchanged(failed_storage):
    service, state = collect_state(failed_storage)
    before = copy.deepcopy((state.evidence, state.trace, state.snapshot))
    required = error_required_facts(state)
    assert len(required) == 17
    assert {entry.observed_value for entry in required if entry.source_field in {
        "/data/anomaly_score", "/data/decision_threshold", "/data/inference_time_ms", "/data/metrics/mean", "/data/metrics/std"}} == {None}
    assert {entry.source_event for entry in required if entry.source_tool == "get_execution_logs"} == {
        "IMAGE_LOAD_FAILED", "INSPECTION_FAILED"}
    result = verify(service, state, draft_for(state))
    assert result.analysis_status == "COMPLETED"
    assert result.inspection_snapshot["result"] == "UNKNOWN" and result.inspection_snapshot["final_result"] == "ERROR"
    assert (state.evidence, state.trace, state.snapshot) == before
    failed_storage.save_inspection.assert_not_called()
    failed_storage.save_logs.assert_not_called()


@pytest.mark.parametrize("field", ["/data/anomaly_score", "/data/decision_threshold", "/data/inference_time_ms",
    "/data/metrics/mean", "/data/metrics/std", "/data/status", "/data/result", "/data/final_result",
    "/data/final_reason_code", "/data/image_quality_status", "/data/defect_detection_status", "/data/1/event_code", "/data/1/stage",
    "/data/1/timestamp", "/data/2/event_code", "/data/2/stage", "/data/2/timestamp"])
def test_each_error_fact_is_mandatory_not_just_natural_language(failed_storage, field):
    service, state = collect_state(failed_storage)
    draft = draft_for(state)
    draft.observed_facts = [fact for fact in draft.observed_facts if fact.source_field != field]
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        verify(service, state, draft)


@pytest.mark.parametrize("field", ["/data/anomaly_score", "/data/decision_threshold", "/data/inference_time_ms",
    "/data/metrics/mean", "/data/metrics/std"])
def test_unmeasured_null_is_never_numeric_zero(failed_storage, field):
    service, state = collect_state(failed_storage)
    draft = draft_for(state)
    fact = next(fact for fact in draft.observed_facts if fact.source_field == field)
    assert fact.observed_value is None
    fact.observed_value = 0
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        verify(service, state, draft)


@pytest.mark.parametrize("mutation", ["missing_trace", "unexecuted", "unsuccessful", "wrong_arguments", "wrong_owner",
    "wrong_evidence", "wrong_stage", "wrong_level", "missing_time", "reversed_time", "metrics_conflict", "snapshot_conflict"])
def test_error_investigation_rejects_invalid_provenance_and_events(failed_storage, mutation):
    service, state = collect_state(failed_storage)
    if mutation == "missing_trace":
        state.trace.pop()
    elif mutation in {"unexecuted", "unsuccessful", "wrong_arguments"}:
        trace = state.trace[-1]
        if mutation == "unexecuted":
            trace.executed = False
        elif mutation == "unsuccessful":
            trace.success = False
        else:
            trace.arguments["inspection_id"] = "INSP-000002"
    elif mutation == "wrong_owner":
        state.evidence["E0001"][1]["data"]["inspection_id"] = "INSP-000002"
    elif mutation == "wrong_evidence":
        state.evidence["E0002"][1]["metadata"]["evidence_id"] = "E9999"
    elif mutation == "snapshot_conflict":
        state.snapshot = {**state.snapshot, "anomaly_score": 1}
    else:
        event = state.evidence["E0002"][1]["data"][1]
        if mutation == "wrong_stage":
            event["stage"] = "inference"
        elif mutation == "wrong_level":
            event["level"] = "INFO"
        elif mutation == "missing_time":
            event["timestamp"] = None
        elif mutation == "reversed_time":
            event["timestamp"] = "2026-10-15T00:00:00+00:00"
        else:
            event["metrics"]["final_result"] = "OK"
    with pytest.raises(AgentFailure):
        error_required_facts(state)
    assert not image_load_failure_evidence_ready(state)


@pytest.mark.parametrize("logs", [[], [make_log()], [make_log(event_code="IMAGE_LOAD_FAILED", stage="load", level="ERROR")]])
def test_missing_workflow_failure_event_cannot_complete(failed_storage, logs):
    failed_storage.get_logs.return_value = logs
    service, generator = service_for(failed_storage, responses_with_logs(continue_investigation=True))
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "FAILED" and result.error_code == "INSUFFICIENT_EVIDENCE"
    assert generator.await_count == 3
    assert all(not entry.kwargs["config"].response_mime_type for entry in generator.call_args_list)


def test_other_inspections_logs_do_not_supply_error_evidence(failed_storage):
    failed_storage.get_logs.return_value = [log.model_copy(update={"inspection_id": "INSP-000002"}) for log in error_logs()]
    service, generator = service_for(failed_storage, responses_with_logs(continue_investigation=True))
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "INSUFFICIENT_EVIDENCE" and generator.await_count == 3
    assert result.tools_used == ["get_inspection_result"]


@pytest.mark.parametrize("failure", ["exception", "not_found"])
def test_logs_failure_never_reaches_final_generation(failed_storage, failure):
    if failure == "exception":
        failed_storage.get_logs.side_effect = RuntimeError("PRIVATE_ERROR_MESSAGE")
    else:
        failed_storage.get_inspection.side_effect = [failed_storage.get_inspection.return_value, None]
    service, generator = service_for(failed_storage, responses_with_logs())
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == ("STORAGE_ERROR" if failure == "exception" else "NOT_FOUND")
    assert generator.await_count == 2 and "PRIVATE_ERROR_MESSAGE" not in result.model_dump_json()


@pytest.mark.parametrize("kind", ["cause", "check"])
@pytest.mark.parametrize("reference", ["/data/result", "/data/defect_detection_status"])
def test_unknown_and_skipped_do_not_imply_model_failure(failed_storage, kind, reference):
    service, state = collect_state(failed_storage)
    draft = draft_for(state)
    identifier = next(fact.fact_id for fact in draft.observed_facts if fact.source_field == reference)
    payload = draft.model_dump()
    if kind == "cause":
        payload["possible_causes"] = [{"cause_code": "MODEL_AVAILABILITY", "evidence_refs": [identifier]}]
    else:
        payload["recommended_checks"] = [{"check_code": "MODEL_SERVICE_CHECK", "evidence_refs": [identifier]}]
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        verify(service, state, DiagnosisDraft.model_validate(payload))


def test_real_inference_failure_event_can_support_model_hypothesis(failed_storage):
    failed_storage.get_inspection.return_value = error_record(defect_detection_status="FAILED", image_quality_status="NORMAL",
        decision_threshold=34.1442, metrics={"mean": 125, "std": 50})
    failed_storage.get_logs.return_value = [make_log(event_code="INFERENCE_FAILED", stage="inference", level="ERROR", metrics={}),
        error_logs()[-1]]
    service, state = collect_state(failed_storage)
    draft = draft_for(state)
    identifier = next(fact.fact_id for fact in draft.observed_facts if fact.source_event == "INFERENCE_FAILED"
        and fact.source_field.endswith("/event_code"))
    payload = draft.model_dump()
    payload["possible_causes"] = [{"cause_code": "MODEL_AVAILABILITY", "evidence_refs": [identifier]}]
    payload["recommended_checks"] = [{"check_code": "MODEL_SERVICE_CHECK", "evidence_refs": [identifier]}]
    result = verify(service, state, DiagnosisDraft.model_validate(payload))
    assert result.analysis_status == "COMPLETED" and result.possible_causes[0].is_hypothesis
    assert not any(fact.source_event == "IMAGE_LOAD_FAILED" for fact in result.observed_facts)


def test_generic_failure_is_not_invented_as_load_failure(failed_storage):
    failed_storage.get_logs.return_value = [error_logs()[-1]]
    service, state = collect_state(failed_storage)
    draft = draft_for(state)
    assert verify(service, state, draft).analysis_status == "COMPLETED"
    identifiers = [fact.fact_id for fact in draft.observed_facts if fact.source_field in {"/data/status", "/data/image_quality_status"}]
    payload = draft.model_dump()
    payload["possible_causes"] = [{"cause_code": "IMAGE_ACQUISITION", "evidence_refs": identifiers}]
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        verify(service, state, DiagnosisDraft.model_validate(payload))


@pytest.mark.parametrize("record", [make_record(), make_record(image_quality_status="WARNING_LOW_BRIGHTNESS",
    final_result="REINSPECT", final_reason_code="IMAGE_QUALITY_WARNING"), make_record(defect_detection_status="FAILED",
    result="UNKNOWN", final_result="REINSPECT", final_reason_code="DEFECT_DETECTION_UNAVAILABLE")])
def test_error_scope_does_not_replace_normal_warning_or_inference_policies(failed_storage, record):
    failed_storage.get_inspection.return_value = record
    service, state = collect_state(failed_storage, with_logs=False)
    assert not error_report_scope(state)


def test_fake_transport_observes_protocol_and_separate_final_generation(failed_storage):
    service, generator = service_for(failed_storage, responses_with_logs())
    transmissions = []

    def transport(request):
        body = json.loads(request.content)
        transmissions.append({"roles": [content["role"] for content in body["contents"]],
            "structured": "responseJsonSchema" in body["generationConfig"], "tools": "tools" in body})
        return httpx.Response(200, json={"offline": True})

    async def generate(**kwargs):
        parameters = types._GenerateContentParameters(**kwargs)
        wire = _common.encode_unserializable_types(_common.convert_to_dict(
            models._GenerateContentParameters_to_mldev(SimpleNamespace(vertexai=False), parameters)))
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            await client.post("https://mock.invalid/generate", json=wire)
        return await generator(**kwargs)

    service.client.aio.models.generate_content = generate
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and len(transmissions) == 3
    assert transmissions[1]["roles"] == ["user", "model", "user"]
    assert transmissions[-1] == {"roles": ["user"], "structured": True, "tools": False}
    assert len(result.tool_execution_trace) == 2 and len(result.observed_facts) == 17
    assert all(entry.kwargs["config"].http_options.retry_options.attempts == 1 for entry in generator.call_args_list)


@pytest.mark.parametrize("limits,expected,requests,executions", [
    (AgentLimits(max_tool_calls=1), "TOOL_CALL_LIMIT", 2, 1),
    (AgentLimits(max_tool_rounds=1), "TOOL_ROUND_LIMIT", 2, 1),
])
def test_error_policy_does_not_expand_existing_call_limits(failed_storage, limits, expected, requests, executions):
    service, generator = service_for(failed_storage, responses_with_logs(), limits=limits)
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == expected and generator.await_count == requests
    assert sum(entry.executed for entry in result.tool_execution_trace) == executions


def test_http_rejects_error_completion_without_logs_and_preserves_stored_failure(harness):
    from backend.agent.api import get_agent_service
    from backend.main import app

    harness.storage.save_inspection(error_record())
    service, generator = service_for(harness.storage, [
        call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})), text_response()])
    app.dependency_overrides[get_agent_service] = lambda: service
    before = harness.storage.get_inspection("INSP-000001").model_dump()
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 502
    assert response.json() == {"detail": {"analysis_status": "FAILED", "error_code": "INSUFFICIENT_EVIDENCE"}}
    assert generator.await_count == 2
    assert harness.storage.get_inspection("INSP-000001").model_dump() == before
