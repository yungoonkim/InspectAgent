"""Real operating warning policy with injected SDK mocks and no network access."""

import asyncio
from dataclasses import replace
import json
from unittest.mock import patch

from google.genai import _api_client, errors
import pytest

from backend.agent.api import get_agent_service
from backend.agent.service import AgentService
from backend.main import app
from tests.test_agent_api import file_hashes, harness, prohibit_real_sdk_client
from tests.test_agent_service import call_response, service_for, text_response
from tests.test_agent_warning_policy_experiment import REQUIRED_EVENTS, calls, warning_report, warning_storage


@pytest.fixture(autouse=True)
def no_external_requests():
    with patch("google.genai.Client", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(_api_client.BaseApiClient, "request", side_effect=AssertionError("NETWORK_FORBIDDEN")) as sync_request, \
         patch.object(_api_client.BaseApiClient, "async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")) as async_request:
        yield
        sync_request.assert_not_called()
        async_request.assert_not_called()


def operating_service(storage, responses, required=()):
    template, generator = service_for(storage, responses)
    service = AgentService(template.tools, settings=template.settings, client=template.client, limits=template.limits,
        required_warning_event_codes=required)
    return service, generator


def test_real_service_collects_warning_history_without_a_readiness_request():
    storage = warning_storage()
    service, generator = operating_service(storage, [*calls(), warning_report])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert type(service) is AgentService and result.analysis_status == "COMPLETED"
    assert generator.await_count == 3 and result.tools_used == ["get_inspection_result", "analyze_image_quality"]
    assert [trace.round_number for trace in result.tool_execution_trace] == [1, 2, 2]
    assert all(trace.executed and trace.success for trace in result.tool_execution_trace[:2])
    history = result.tool_execution_trace[-1]
    assert history.origin == "BACKEND_POLICY" and history.executed and not history.success
    assert history.error_code == "DATA_UNAVAILABLE" and history.evidence_id is None
    storage.list_inspections.assert_called_once_with(limit=1000, product_id="PROD-001")
    storage.get_logs.assert_not_called()
    assert set(json.loads(generator.call_args_list[-1].kwargs["contents"][0].parts[0].text)) == {
        "inspection_id", "catalog", "tool_execution_trace",
    }


def test_required_log_contract_is_server_owned_and_reaches_both_model_stages():
    storage = warning_storage()
    service, generator = operating_service(storage, [*calls(True), warning_report], REQUIRED_EVENTS)
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and generator.await_count == 4
    assert "Required warning events: ANALYSIS_COMPLETED, INSPECTION_COMPLETED" in generator.call_args_list[0].kwargs["contents"][0].parts[0].text
    final = generator.call_args_list[-1].kwargs
    assert json.loads(final["contents"][0].parts[0].text)["required_warning_event_codes"] == list(REQUIRED_EVENTS)
    assert final["config"].tools is None and final["config"].tool_config is None
    assert {fact.source_event for fact in result.observed_facts if fact.source_tool == "get_execution_logs"} == set(REQUIRED_EVENTS)
    assert len([fact for fact in result.observed_facts if fact.source_field.endswith("/timestamp")]) == 2


@pytest.mark.parametrize("required", ["ANALYSIS_COMPLETED", None, ("UNSUPPORTED_EVENT",),
    ("ANALYSIS_COMPLETED", "ANALYSIS_COMPLETED"), (12,)])
def test_invalid_server_log_contract_is_rejected_before_any_model_request(required):
    with pytest.raises(ValueError, match="INVALID_WARNING_LOG_POLICY"):
        operating_service(warning_storage(), [], required)


@pytest.mark.parametrize("required", [False, True])
def test_missing_logs_are_optional_only_when_the_contract_allows_it(required):
    storage = warning_storage()
    storage.get_logs.return_value = []
    parallel = call_response(("analyze_image_quality", {"inspection_id": "INSP-000001"}),
        ("get_execution_logs", {"inspection_id": "INSP-000001"}))
    service, generator = operating_service(storage, [calls()[0], parallel, text_response(), warning_report],
        REQUIRED_EVENTS if required else ())
    result = asyncio.run(service.analyze("INSP-000001"))
    assert generator.await_count == 4
    assert result.analysis_status == ("FAILED" if required else "COMPLETED")
    assert result.error_code == ("EVIDENCE_MISMATCH" if required else None)
    assert result.tool_execution_trace[2].error_code == "DATA_UNAVAILABLE"
    assert result.tool_execution_trace[2].executed and not result.tool_execution_trace[2].success
    assert "get_execution_logs" not in result.tools_used


def test_valid_history_completes_warning_fast_path_without_a_readiness_request():
    storage = warning_storage()
    storage.list_inspections.return_value = [storage.get_inspection.return_value]
    parallel = call_response(("analyze_image_quality", {"inspection_id": "INSP-000001"}),
        ("get_inspection_history", {"product_id": "TARGET-PRODUCT"}))
    service, generator = operating_service(storage, [calls()[0], parallel, warning_report])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and generator.await_count == 3
    assert result.tools_used == ["get_inspection_result", "analyze_image_quality", "get_inspection_history"]


@pytest.mark.parametrize("field", ["mean", "std", "min", "max", "threshold_status", "low_threshold", "high_threshold"])
def test_operating_http_rejects_missing_final_brightness_facts(harness, field):
    record = warning_storage().get_inspection.return_value
    if field in {"low_threshold", "high_threshold"}:
        record.metrics["applied_thresholds"] = {"low_threshold": 100.0, "high_threshold": 160.0}
    harness.storage.save_inspection(record)

    def incomplete(**kwargs):
        payload = json.loads(warning_report(**kwargs).candidates[0].content.parts[0].text)
        packet = json.loads(kwargs["contents"][0].parts[0].text)
        removed = {entry["token"] for entry in packet["catalog"] if entry["source_tool"] == "analyze_image_quality"
            and entry["source_field"].endswith("/" + field)}
        payload["observed_fact_refs"] = [token for token in payload["observed_fact_refs"] if token not in removed]
        return text_response(json.dumps(payload))

    service, generator = operating_service(harness.storage, [*calls(), incomplete])
    app.dependency_overrides[get_agent_service] = lambda: service
    before = file_hashes(harness)
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 502 and response.json()["detail"]["error_code"] == "EVIDENCE_MISMATCH"
    assert generator.await_count == 3 and file_hashes(harness) == before


@pytest.mark.parametrize("mutation", ["unknown_token", "pointer", "cause", "check", "verdict", "inspection_id"])
def test_bad_warning_claims_are_never_repaired_or_used_to_change_the_verdict(harness, mutation):
    harness.storage.save_inspection(warning_storage().get_inspection.return_value)

    def invalid(**kwargs):
        payload = json.loads(warning_report(**kwargs).candidates[0].content.parts[0].text)
        if mutation in {"unknown_token", "pointer"}:
            payload["observed_fact_refs"][0] = "E9999" if mutation == "unknown_token" else "/data/missing"
        elif mutation == "cause":
            payload["possible_causes"] = ["MODEL_AVAILABILITY:" + payload["observed_fact_refs"][0]]
        elif mutation == "check":
            payload["recommended_checks"] = ["CONTINUE_MONITORING:" + payload["observed_fact_refs"][0]]
        elif mutation == "verdict":
            payload["overall_summary"] = "NORMAL_MODEL_RESULT"
        else:
            payload["inspection_id"] = "INSP-000002"
        return text_response(json.dumps(payload))

    service, generator = operating_service(harness.storage, [*calls(), invalid])
    app.dependency_overrides[get_agent_service] = lambda: service
    before = file_hashes(harness)
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 502
    assert response.json()["detail"]["error_code"] == ("RESPONSE_SCHEMA_INVALID" if mutation == "inspection_id" else "EVIDENCE_MISMATCH")
    assert generator.await_count == 3 and file_hashes(harness) == before


@pytest.mark.parametrize("field", ["stage", "timestamp"])
def test_required_event_facts_need_both_stage_and_time_from_real_log_entries(field):
    def incomplete(**kwargs):
        payload = json.loads(warning_report(**kwargs).candidates[0].content.parts[0].text)
        packet = json.loads(kwargs["contents"][0].parts[0].text)
        removed = {entry["token"] for entry in packet["catalog"] if entry["source_tool"] == "get_execution_logs"
            and entry["source_field"].endswith("/" + field)}
        payload["observed_fact_refs"] = [token for token in payload["observed_fact_refs"] if token not in removed]
        return text_response(json.dumps(payload))

    service, generator = operating_service(warning_storage(), [*calls(True), incomplete], REQUIRED_EVENTS)
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "EVIDENCE_MISMATCH" and generator.await_count == 4


def test_required_event_chronology_cannot_be_inferred_from_array_order():
    storage = warning_storage()
    storage.get_logs.return_value[0].timestamp = "2026-10-15T01:00:01Z"
    service, generator = operating_service(storage, [*calls(True), text_response(), warning_report], REQUIRED_EVENTS)
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "EVIDENCE_MISMATCH" and generator.await_count == 5


@pytest.mark.parametrize("field,value", [("source_field", "/data/unrecorded"), ("evidence_id", "E9999")])
def test_forged_warning_catalog_is_rejected_before_report_acceptance(field, value):
    from backend.agent.reporting import build_catalog

    def forged(state, **kwargs):
        catalog = build_catalog(state, **kwargs)
        entry = replace(catalog.entries[-1], **{field: value})
        return replace(catalog, entries=(*catalog.entries[:-1], entry))

    service, generator = operating_service(warning_storage(), [*calls(), warning_report])
    with patch("backend.agent.service.build_catalog", side_effect=forged):
        result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "EVIDENCE_MISMATCH" and generator.await_count == 3


def test_operating_warning_final_server_504_retains_safe_http_error(harness):
    harness.storage.save_inspection(warning_storage().get_inspection.return_value)
    failure = errors.ServerError(504, {"error": {"status": "DEADLINE_EXCEEDED", "message": "PRIVATE"}})
    service, generator = operating_service(harness.storage, [*calls(), failure])
    app.dependency_overrides[get_agent_service] = lambda: service
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 502 and response.json()["detail"]["error_code"] == "GEMINI_REQUEST_FAILED"
    assert generator.await_count == 3 and "PRIVATE" not in response.text
    assert generator.call_args_list[-1].kwargs["config"].response_mime_type == "application/json"


def test_historical_experiment_is_only_a_compatibility_import():
    from backend.agent import investigation
    from scripts import agent_warning_policy_experiment as experimental
    assert experimental.warning_evidence_ready is investigation.warning_evidence_ready
    assert experimental.warning_report_covered is investigation.warning_report_covered
