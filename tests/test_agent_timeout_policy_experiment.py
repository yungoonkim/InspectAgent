"""SDK MockTransport and request-local policy experiments without live traffic."""

import asyncio
from unittest.mock import patch

from google import genai
from google.genai import _api_client, types
import httpx
import pytest

from backend.agent.errors import AgentFailure
from backend.agent.reporting import simple_output_schema
from scripts.agent_timeout_policy_experiment import ExperimentalTimeoutAgent, TimeoutPolicy
from tests.test_agent_reporting_integration import simple_response
from tests.test_agent_service import call_response, service_for, text_response
from tests.test_agent_tools import make_record
from tests.agent_error_fixtures import error_logs, error_record
from tests.test_agent_warning_policy_experiment import calls, warning_report, warning_storage


@pytest.fixture(autouse=True)
def block_real_transports():
    with patch.object(httpx.HTTPTransport, "handle_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(_api_client.BaseApiClient, "_use_aiohttp", return_value=False):
        yield


@pytest.mark.parametrize("mode,expected", [("A", 15), ("B", 30), ("C", 30)])
def test_policy_nominal_limits_and_remaining_budget(mode, expected):
    policy = TimeoutPolicy(mode)
    assert policy.select(False, 5) == 15 and policy.select(True, 5) == expected
    assert policy.overall_seconds == 60
    if mode == "C":
        assert policy.select(True, 45.2) == 12
    else:
        with pytest.raises(AgentFailure, match="AGENT_TIMEOUT"):
            policy.select(True, 50)


@pytest.mark.parametrize("elapsed", [58, 59, 60, 100])
def test_exhausted_budget_blocks_request(elapsed):
    with pytest.raises(AgentFailure, match="AGENT_TIMEOUT"):
        TimeoutPolicy("C").select(True, elapsed)


@pytest.mark.parametrize("elapsed", [-1, float("nan"), float("inf"), True])
def test_invalid_clock_values_rejected(elapsed):
    with pytest.raises(ValueError, match="INVALID_ELAPSED_TIME"):
        TimeoutPolicy("C").select(True, elapsed)


@pytest.mark.parametrize("structured,elapsed,expected", [(False, 0, 15), (True, 0, 30), (True, 40.8, 17)])
def test_fractional_remaining_budget_does_not_exceed_server_header_rounding(structured, elapsed, expected):
    seconds = TimeoutPolicy("C").select(structured, elapsed)
    headers = {}
    _api_client.populate_server_timeout_header(headers, seconds)
    assert seconds == expected and int(headers["X-Server-Timeout"]) <= 60 - elapsed - 2


@pytest.mark.parametrize("asynchronous", [False, True])
def test_actual_sdk_request_pipeline_overrides_default_without_client_recreation(asynchronous):
    observed = []

    def respond(request):
        observed.append({"server_timeout": request.headers.get("X-Server-Timeout"),
            "timeouts": request.extensions["timeout"]})
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": "{}"}]},
            "finishReason": "STOP"}]})

    transport = httpx.MockTransport(respond)
    client = genai.Client(api_key="offline-placeholder", vertexai=False, http_options=types.HttpOptions(
        api_version="v1beta", timeout=15000, retry_options=types.HttpRetryOptions(attempts=1),
        client_args={"transport": transport}, async_client_args={"transport": transport}))

    def config(seconds):
        return types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=simple_output_schema(),
            http_options=types.HttpOptions(timeout=seconds * 1000, retry_options=types.HttpRetryOptions(attempts=1)))

    async def run():
        try:
            for seconds in (15, 30, 15):
                await client.aio.models.generate_content(model="gemini-3.8-flash", contents="Harmless offline fixture.", config=config(seconds))
        finally:
            await client.aio.aclose()

    try:
        if asynchronous:
            asyncio.run(run())
        else:
            for seconds in (15, 30, 15):
                client.models.generate_content(model="gemini-3.8-flash", contents="Harmless offline fixture.", config=config(seconds))
    finally:
        client.close()
    assert [entry["server_timeout"] for entry in observed] == ["15", "30", "15"]
    assert [entry["timeouts"]["read"] for entry in observed] == [15, 30, 15]
    assert client._api_client._http_options.timeout == 15000
    assert client._api_client._http_options.retry_options.attempts == 1


def test_explicit_server_header_is_not_overridden_by_larger_request_timeout():
    base = types.HttpOptions(timeout=15000, headers={"X-Server-Timeout": "15"})
    request = _api_client.patch_http_options(base, types.HttpOptions(timeout=30000))
    _api_client.populate_server_timeout_header(request.headers, _api_client.get_timeout_in_seconds(request.timeout))
    assert request.timeout == 30000 and request.headers["X-Server-Timeout"] == "15"
    assert base.timeout == 15000


@pytest.mark.parametrize("mode", ["A", "B", "C"])
@pytest.mark.parametrize("scenario", ["T01", "T03", "T05", "T06"])
def test_experimental_policy_keeps_real_tool_and_report_validation(mode, scenario):
    storage = warning_storage()
    responses = [*calls(), warning_report]
    if scenario in {"T01", "T06"}:
        storage.get_inspection.return_value = make_record()
        responses = [calls()[0], simple_response]
    elif scenario == "T05":
        storage.get_inspection.return_value = error_record()
        storage.get_logs.return_value = error_logs()
        responses = [calls()[0], call_response(("get_execution_logs", {"inspection_id": "INSP-000001"})), simple_response]
    template, generator = service_for(storage, responses)
    service = ExperimentalTimeoutAgent(template.tools, settings=template.settings, client=template.client,
        limits=template.limits, policy=TimeoutPolicy(mode), clock=lambda: 0)
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    assert generator.await_count == {"T01": 2, "T03": 3, "T05": 3, "T06": 2}[scenario]
    assert all(entry["seconds"] == 15 for entry in service.timeout_decisions[:-1])
    assert service.timeout_decisions[-1]["seconds"] == (15 if mode == "A" else 30)
    assert [call.kwargs["config"].http_options.timeout for call in generator.call_args_list] == [
        entry["seconds"] * 1000 for entry in service.timeout_decisions]
    assert service.limits == template.limits and service.limits.request_timeout_seconds == 60
    assert all(call.kwargs["config"].http_options.retry_options.attempts == 1 for call in generator.call_args_list)
    assert all(fact.evidence_id in {entry.evidence_id for entry in result.tool_execution_trace} for fact in result.observed_facts)
    storage.save_inspection.assert_not_called()


def test_budget_exhaustion_stops_before_final_model_call():
    template, generator = service_for(warning_storage(), calls())
    elapsed = iter((0, 0, 0, 59))
    service = ExperimentalTimeoutAgent(template.tools, settings=template.settings, client=template.client,
        limits=template.limits, policy=TimeoutPolicy("C"), clock=lambda: next(elapsed))
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "AGENT_TIMEOUT" and generator.await_count == 2


def test_remaining_budget_drives_final_sdk_timeout_without_changing_overall_limit():
    template, generator = service_for(warning_storage(), [*calls(), warning_report])
    elapsed = iter((0, 0, 0, 45.2))
    service = ExperimentalTimeoutAgent(template.tools, settings=template.settings, client=template.client,
        limits=template.limits, policy=TimeoutPolicy("C"), clock=lambda: next(elapsed))
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    assert generator.call_args_list[-1].kwargs["config"].http_options.timeout == 12000
    assert service.limits.request_timeout_seconds == 60
