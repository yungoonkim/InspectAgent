"""Final JSON size experiments and timeout handling, never Gemini server tests."""

import asyncio
import json
from unittest.mock import patch

from google.genai import _api_client, errors
from google.genai import types
import httpx
import pytest

from backend.agent.api import ERROR_STATUS
from backend.agent.reporting import build_catalog, verify_simple_report
from backend.agent.service import AgentFailure
from backend.agent.service import _report_contents
from scripts.agent_final_request_experiment import compact_contents, reconstruct_final_request, request_metrics
from tests.test_agent_reporting_integration import simple_response
from tests.test_agent_service import service_for
from tests.test_agent_tools import make_record
from tests.test_agent_warning_policy_experiment import calls, warning_report, warning_storage
from tests.agent_deadline_control import ControlledDeadlines


@pytest.fixture(autouse=True)
def no_network():
    with patch("google.genai.Client", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(_api_client.BaseApiClient, "request", side_effect=AssertionError("NETWORK_FORBIDDEN")) as sync_request, \
         patch.object(_api_client.BaseApiClient, "async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")) as async_request, \
         patch.object(httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")):
        yield
        sync_request.assert_not_called()
        async_request.assert_not_called()


def reconstruct(warning=True):
    storage = warning_storage()
    if not warning:
        storage.get_inspection.return_value = make_record()
    service, generator = service_for(storage, [])
    names = ("get_inspection_result", "analyze_image_quality") if warning else ("get_inspection_result",)
    request, state = asyncio.run(reconstruct_final_request(service, "INSP-000001", names))
    generator.assert_not_called()
    return service, request, state


def test_warning_input_increases_but_schema_prompt_and_limits_are_identical():
    normal, normal_request, normal_state = reconstruct(False)
    warning, warning_request, warning_state = reconstruct(True)
    left, right = request_metrics(normal_request), request_metrics(warning_request)
    assert left["schema_sha256"] == right["schema_sha256"]
    assert normal_request["config"].system_instruction == warning_request["config"].system_instruction
    assert right["catalog_entries"] > left["catalog_entries"]
    assert right["serialized_request_bytes"] > left["serialized_request_bytes"]
    assert (left["evidence_count"], right["evidence_count"]) == (1, 2)
    for metric in (left, right):
        assert metric["max_output_tokens"] == 4096 and not metric["thinking_explicit"]
        assert metric["http_timeout_ms"] == 15000 and metric["retry_attempts"] == 1
        assert metric["roles"] == ["user"] and not metric["tools_present"] and not metric["tool_config_present"]
        assert metric["server_acceptance"] == "NOT TESTED"


@pytest.mark.parametrize("warning", [False, True])
def test_whitespace_candidate_keeps_every_fact_token_and_trace(warning):
    service, request, state = reconstruct(warning)
    original = request["contents"][0].parts[0].text
    compact = compact_contents(request["contents"])
    assert json.loads(original) == json.loads(compact[0].parts[0].text)
    assert request["contents"][0].parts[0].text == original
    assert len(compact[0].parts[0].text) < len(original)
    request["contents"] = compact
    response = warning_report(**request) if warning else simple_response(**request)
    raw = response.candidates[0].content.parts[0].text
    result = verify_simple_report(raw, service, state, build_catalog(state))
    assert result.analysis_status == "COMPLETED"


@pytest.mark.parametrize("field", ["mean", "std", "min", "max", "threshold_status"])
def test_compaction_does_not_repair_missing_mandatory_warning_facts(field):
    service, request, state = reconstruct()
    request["contents"] = compact_contents(request["contents"])
    payload = json.loads(warning_report(**request).candidates[0].content.parts[0].text)
    omitted = {entry.token for entry in build_catalog(state).entries
        if entry.source_tool == "analyze_image_quality" and entry.source_field.endswith("/" + field)}
    payload["observed_fact_refs"] = [token for token in payload["observed_fact_refs"] if token not in omitted]
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        verify_simple_report(json.dumps(payload), service, state, build_catalog(state))


def test_missing_historical_thresholds_are_preserved_not_inferred():
    service, request, state = reconstruct()
    assert state.evidence["E0002"][1]["data"]["threshold_status"] == "NOT_RECORDED"
    assert state.evidence["E0002"][1]["data"]["brightness_thresholds"] is None
    payload = warning_report(**request).candidates[0].content.parts[0].text
    result = verify_simple_report(payload, service, state, build_catalog(state))
    assert any(fact.source_field == "/data/threshold_status" and fact.observed_value == "NOT_RECORDED"
        for fact in result.observed_facts)


def test_sdk_timeout_also_populates_server_deadline_header_without_network():
    service, request, state = reconstruct()
    measured = request_metrics(request)
    assert measured["httpx_timeout_seconds"] == 15
    assert measured["sdk_default_server_timeout_header"] == "15"
    existing = {"X-Server-Timeout": "9"}
    _api_client.populate_server_timeout_header(existing, 15)
    assert existing["X-Server-Timeout"] == "9"


def test_extra_log_evidence_grows_request_without_bypassing_final_validation():
    service, request, state = reconstruct()
    before = request_metrics(request)
    asyncio.run(service._execute(types.FunctionCall(name="get_execution_logs", args={"inspection_id": state.inspection_id}), state, 3))
    request["contents"] = _report_contents(state)
    after = request_metrics(request)
    assert after["catalog_entries"] > before["catalog_entries"]
    assert after["evidence_count"] == 3 and after["serialized_request_bytes"] > before["serialized_request_bytes"]
    response = warning_report(**request).candidates[0].content.parts[0].text
    assert verify_simple_report(response, service, state, build_catalog(state)).analysis_status == "COMPLETED"


def test_compact_candidate_rejects_forged_evidence_and_keeps_snapshot():
    service, request, state = reconstruct()
    snapshot = dict(state.snapshot)
    request["contents"] = compact_contents(request["contents"])
    payload = json.loads(warning_report(**request).candidates[0].content.parts[0].text)
    payload["observed_fact_refs"].append("K9999")
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        verify_simple_report(json.dumps(payload), service, state, build_catalog(state))
    assert state.snapshot == snapshot


@pytest.mark.parametrize("fault", ["server_504", "local_model_timeout", "overall_timeout"])
def test_server_deadline_and_local_deadlines_have_distinct_safe_errors(fault):
    failure = errors.ServerError(504, {"error": {"status": "DEADLINE_EXCEEDED", "message": "PRIVATE"}})
    service, generator = service_for(warning_storage(), [*calls(), failure])
    requested = []

    async def run():
        with ControlledDeadlines() as deadlines:
            async def generate(**kwargs):
                requested.append(kwargs)
                if fault != "server_504" and kwargs["config"].response_mime_type == "application/json":
                    await deadlines.expire("overall" if fault == "overall_timeout" else "model")
                return await generator(**kwargs)
            service.client.aio.models.generate_content = generate
            return await service.analyze("INSP-000001")

    result = asyncio.run(run())
    code = {"server_504": "GEMINI_REQUEST_FAILED", "local_model_timeout": "GEMINI_TIMEOUT",
        "overall_timeout": "AGENT_TIMEOUT"}[fault]
    assert result.error_code == code and result.analysis_status == "FAILED"
    assert ERROR_STATUS[code] == (502 if fault == "server_504" else 504)
    assert len(result.tool_execution_trace) == 2 and len(requested) == 3
    assert "PRIVATE" not in result.model_dump_json()
