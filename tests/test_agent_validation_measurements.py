"""Offline measurement tests; HTTP transmissions use only MockTransport."""

import asyncio
import json
import time
from unittest.mock import patch

from google.genai import _api_client, errors
import httpx
import pytest

from backend.agent.service import AgentService, _normal_evidence_ready
from scripts.agent_validation_measurements import record_investigation_stop, summarize_measurements
from tests.test_agent_reporting_integration import simple_response
from tests.test_agent_service import call_response, service_for, text_response
from tests.test_agent_t05_preflight import collect_state, failed_storage
from tests.test_agent_tools import make_record
from tests.agent_error_fixtures import error_logs, error_record
from tests.test_agent_warning_policy_experiment import REQUIRED_EVENTS, calls, warning_report, warning_storage


@pytest.fixture(autouse=True)
def block_external_network():
    with patch("google.genai.Client", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(_api_client.BaseApiClient, "request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(_api_client.BaseApiClient, "async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")):
        yield


def measure(scenario, required=(), fail_final=False):
    storage = warning_storage()
    responses = [*calls(bool(required)), warning_report]
    if scenario in {"T01", "T06"}:
        storage.get_inspection.return_value = make_record()
        responses = [calls()[0], simple_response]
    elif scenario == "T05":
        storage.get_inspection.return_value = error_record()
        storage.get_logs.return_value = error_logs()
        responses = [calls()[0], call_response(("get_execution_logs", {"inspection_id": "INSP-000001"})),
            simple_response]
    if fail_final:
        responses[-1] = errors.ServerError(504, {"error": {"status": "DEADLINE_EXCEEDED", "message": "PRIVATE"}})
    service, generator = service_for(storage, responses)
    service.required_warning_event_codes = required
    report = {"sdk_requests": [], "http_transmissions": [], "python_tools": []}
    original = AgentService._investigation_ready

    def ready(instance, state):
        return record_investigation_stop(report, instance, state, original, _normal_evidence_ready)

    async def generate(**kwargs):
        entry = {"sequence": len(report["sdk_requests"]) + 1, "success": False,
            "stage": "STRUCTURED_OUTPUT" if kwargs["config"].response_mime_type else "FUNCTION_CALLING"}
        report["sdk_requests"].append(entry)
        started = time.perf_counter()
        status = 504 if fail_final and entry["stage"] == "STRUCTURED_OUTPUT" else 200
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status))) as client:
            response = await client.post("https://mock.invalid/generate")
        report["http_transmissions"].append({"stage": entry["stage"], "status": response.status_code})
        try:
            result = await generator(**kwargs)
            entry["success"] = True
            if result.usage_metadata:
                entry["tokens"] = result.usage_metadata.model_dump()
            return result
        finally:
            entry["elapsed_ms"] = (time.perf_counter() - started) * 1000

    service.client.aio.models.generate_content = generate
    with patch.object(AgentService, "_investigation_ready", ready):
        result = asyncio.run(service.analyze("INSP-000001"))
    report["tool_execution_trace"] = [entry.model_dump() for entry in result.tool_execution_trace]
    summarize_measurements(report)
    return report, result, generator, storage


@pytest.mark.parametrize("scenario,required,requests,executions,policy", [
    ("T01", (), 2, 1, "NORMAL"), ("T06", (), 2, 1, "NORMAL"),
    ("T03", (), 3, 2, "WARNING"), ("T03", REQUIRED_EVENTS, 4, 3, "WARNING"),
    ("T05", (), 3, 2, "IMAGE_LOAD_FAILURE"),
])
def test_real_policy_measurements_keep_http_and_tools_distinct(scenario, required, requests, executions, policy):
    report, result, generator, storage = measure(scenario, required)
    assert result.analysis_status == "COMPLETED"
    assert report["actual_http_requests"] == report["sdk_request_count"] == generator.await_count == requests
    assert report["agent_tool_executions"] == executions
    assert report["trace_rounds"] == list(range(1, executions + 1))
    assert report["early_exit_checks"][-1]["policy"] == policy
    if scenario == "T05":
        assert report["early_exit_checks"][-1]["ready"] is True
        assert result.inspection_snapshot["status"] == "FAILED"
        assert result.inspection_snapshot["final_result"] == "ERROR"
    assert report["http_transmissions"][-1] == {"stage": "STRUCTURED_OUTPUT", "status": 200}
    final = generator.call_args_list[-1].kwargs
    assert final["config"].tools is None and final["config"].tool_config is None
    assert len(final["contents"]) == 1 and final["contents"][0].role == "user"
    if policy != "CONTINUE":
        assert report["early_exit_checks"][-1]["evidence_ids"] == [f"E{index:04d}" for index in range(1, executions + 1)]
    if scenario == "T03" and not required:
        storage.get_logs.assert_not_called()
    assert all(entry["elapsed_ms"] >= 0 for entry in report["sdk_requests"])
    assert {fact.evidence_id for fact in result.observed_facts} <= {entry.evidence_id for entry in result.tool_execution_trace}
    json.dumps(report)


def test_image_load_stop_collection_and_final_validation_are_distinct():
    from scripts.agent_validation_measurements import error_policy_measurements
    report, result, generator, storage = measure("T05")
    service, state = collect_state(storage)
    measured = error_policy_measurements(state, phase="INVESTIGATION")
    assert report["early_exit_checks"][-1]["policy"] == "IMAGE_LOAD_FAILURE"
    assert result.inspection_snapshot["image_quality_status"] == "ERROR"
    assert measured["policy_applicable"] is True
    assert measured["required_evidence_collected"] is True and measured["required_fact_count"] == 17
    assert measured["report_validation_passed"] == "NOT TESTED"
    assert service._investigation_ready(state) and generator.await_count == 3


@pytest.mark.parametrize("scenario", ["T03", "T05"])
def test_final_504_is_not_misreported_as_another_investigation_request(scenario):
    report, result, generator, storage = measure(scenario, fail_final=True)
    assert result.error_code == "GEMINI_REQUEST_FAILED"
    assert report["actual_http_requests"] == generator.await_count == 3
    assert report["agent_tool_executions"] == 2
    assert report["failure_stage"] == "STRUCTURED_OUTPUT" and report["failed_sdk_request"] == 3
    assert report["known_tokens"]["total_token_count"] == 30
    assert not report["usage_complete"]
    assert "PRIVATE" not in json.dumps(report)
    storage.save_inspection.assert_not_called()


@pytest.mark.parametrize("case", ["missing_tool", "failed_tool", "missing_event", "missing_fact", "wrong_id", "wrong_evidence", "inference", "extra_requirement"])
def test_incomplete_error_policy_is_not_measured_as_image_load_exit(failed_storage, case):
    service, state = collect_state(failed_storage, with_logs=case != "missing_tool")
    if case == "failed_tool":
        state.trace[-1].success = False
    elif case == "missing_event":
        state.evidence["E0002"][1]["data"].pop(1)
    elif case == "missing_fact":
        state.snapshot.pop("inference_time_ms")
    elif case == "wrong_id":
        state.trace[-1].arguments = {"inspection_id": "INSP-000002"}
    elif case == "wrong_evidence":
        state.evidence["E0002"][1]["metadata"]["evidence_id"] = "E9999"
    elif case == "inference":
        event = state.evidence["E0002"][1]["data"][1]
        event.update(event_code="INFERENCE_FAILED", stage="inference")
        state.snapshot.update(defect_detection_status="FAILED", image_quality_status="NORMAL")
    elif case == "extra_requirement":
        service.required_warning_event_codes = REQUIRED_EVENTS
    report = {}
    ready = record_investigation_stop(report, service, state, AgentService._investigation_ready, _normal_evidence_ready)
    assert ready is False
    assert report["early_exit_checks"][-1]["policy"] == "CONTINUE"
    assert "sdk_requests" not in report


@pytest.mark.parametrize("unavailable", [False, True])
def test_unverified_early_exit_is_unknown_not_assumed_warning_or_error(failed_storage, unavailable):
    service, state = collect_state(failed_storage, with_logs=unavailable)
    report = {}
    with patch("backend.agent.error_policy.image_load_failure_evidence_ready",
        side_effect=RuntimeError("PRIVATE") if unavailable else None, return_value=False):
        ready = record_investigation_stop(report, service, state, lambda instance, state: True, _normal_evidence_ready)
    assert ready is True
    assert report["early_exit_checks"][-1]["policy"] == "UNKNOWN"
    assert "PRIVATE" not in json.dumps(report)


def test_t05_successful_mock_report_is_separate_from_collected_evidence():
    report, result, generator, storage = measure("T05")
    assert report["early_exit_checks"][-1]["policy"] == "IMAGE_LOAD_FAILURE"
    assert generator.await_count == 3
    assert report["sdk_requests"][-1]["stage"] == "STRUCTURED_OUTPUT"
    assert report["sdk_requests"][-1]["success"] is True
    assert result.analysis_status == "COMPLETED" and len(result.observed_facts) == 17
    assert all(fact.evidence_id in {trace.evidence_id for trace in result.tool_execution_trace} for fact in result.observed_facts)


def test_failed_response_does_not_claim_stored_verdict_was_changed():
    report = {"stored_verdict": {"result": "OK"}, "protected_files_unchanged": True}
    summarize_measurements(report)
    assert report["verdict_unchanged"] is None and report["stored_data_unchanged"] is True


@pytest.mark.parametrize("returned,expected", [({"result": "OK"}, True), ({"result": "NG"}, False)])
def test_returned_verdict_comparison(returned, expected):
    report = {"stored_verdict": {"result": "OK"}, "returned_verdict": returned}
    summarize_measurements(report)
    assert report["verdict_unchanged"] is expected


def test_counts_and_usage_are_request_local_and_partial_usage_is_explicit():
    first, result, generator, storage = measure("T03")
    second, result, generator, storage = measure("T01")
    assert first["actual_http_requests"] == 3 and second["actual_http_requests"] == 2
    assert first["known_tokens"]["total_token_count"] == 30
    assert second["known_tokens"]["total_token_count"] == 15
    assert not first["usage_complete"] and not second["usage_complete"]


def test_preflight_python_calls_and_agent_trace_are_separate_counters():
    report = {"python_tools": [{"name": "get_inspection_result"}] * 3,
        "tool_execution_trace": [{"executed": True, "round_number": 1}, {"executed": True, "round_number": 2}]}
    summarize_measurements(report)
    assert report["python_tool_invocations"] == 3 and report["agent_tool_executions"] == 2
