"""Production per-stage deadlines with fake tools, SDK responses and HTTP transport."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

from google import genai
from google.genai import _api_client, errors, types
import httpx
from pydantic import ValidationError
import pytest

from backend.agent.api import ERROR_STATUS
from backend.agent.schemas import AgentLimits
from backend.agent.service import AgentFailure, AgentService, RequestState
from backend.config import Settings
from tests.test_agent_reporting_integration import simple_payload, simple_response
from tests.test_agent_service import call_response, service_for, text_response
from tests.test_agent_tools import make_record
from tests.agent_error_fixtures import error_logs, error_record
from tests.test_agent_warning_policy_experiment import REQUIRED_EVENTS, calls, warning_report, warning_storage


@pytest.fixture(autouse=True)
def block_live_transports():
    with patch.object(httpx.HTTPTransport, "handle_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(_api_client.BaseApiClient, "_use_aiohttp", return_value=False):
        yield


@pytest.mark.parametrize("value", [0, -1, 31, float("nan"), float("inf"), True, "bad", 1.5])
def test_invalid_final_timeout_rejected_by_settings_and_limits(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, GEMINI_API_KEY=None, AGENT_FINAL_MODEL_TIMEOUT_SECONDS=value)
    with pytest.raises(ValidationError):
        AgentLimits(final_model_timeout_seconds=value)


def test_defaults_and_opt_in_environment(monkeypatch):
    monkeypatch.delenv("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", raising=False)
    assert Settings(_env_file=None, GEMINI_API_KEY=None).AGENT_FINAL_MODEL_TIMEOUT_SECONDS == 15
    monkeypatch.setenv("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", "30")
    settings = Settings(_env_file=None, GEMINI_API_KEY=None)
    service = AgentService(warning_storage(), settings=settings, client=SimpleNamespace())
    assert service.limits.model_timeout_seconds == 15 and service.limits.final_model_timeout_seconds == 30
    assert service.limits.request_timeout_seconds == 60


@pytest.mark.parametrize("final_timeout", [15, 30])
@pytest.mark.parametrize("scenario", ["T01", "T03", "T05", "T06", "T03_required_logs"])
def test_operating_stage_limits_preserve_tools_verdicts_and_grounding(scenario, final_timeout):
    storage = warning_storage()
    required = REQUIRED_EVENTS if scenario == "T03_required_logs" else ()
    responses = [*calls(bool(required)), warning_report]
    if scenario in {"T01", "T06"}:
        storage.get_inspection.return_value = make_record()
        responses = [calls()[0], simple_response]
    elif scenario == "T05":
        storage.get_inspection.return_value = error_record()
        storage.get_logs.return_value = error_logs()
        responses = [calls()[0], call_response(("get_execution_logs", {"inspection_id": "INSP-000001"})), simple_response]
    template, generator = service_for(storage, responses)
    limits = AgentLimits(final_model_timeout_seconds=final_timeout)
    service = AgentService(template.tools, settings=template.settings, client=template.client, limits=limits,
        required_warning_event_codes=required)
    original_wait = asyncio.wait_for
    waits = []

    async def wait(awaitable, timeout):
        waits.append(timeout)
        return await original_wait(awaitable, timeout)

    with patch("backend.agent.service.asyncio.wait_for", wait):
        result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    configs = [entry.kwargs["config"] for entry in generator.call_args_list]
    assert [config.http_options.timeout for config in configs] == [15000] * (len(configs) - 1) + [final_timeout * 1000]
    assert [config.http_options.headers["X-Server-Timeout"] for config in configs] == ["15"] * (len(configs) - 1) + [str(final_timeout)]
    assert final_timeout in waits and all(config.http_options.retry_options.attempts == 1 for config in configs)
    assert limits == service.limits and service.limits.request_timeout_seconds == 60
    assert generator.await_count == {"T01": 2, "T03": 3, "T05": 3, "T06": 2, "T03_required_logs": 4}[scenario]
    assert result.inspection_snapshot["final_result"] == storage.get_inspection.return_value.final_result
    assert result.inspection_snapshot["result"] == storage.get_inspection.return_value.result
    assert result.inspection_snapshot["final_reason_code"] == storage.get_inspection.return_value.final_reason_code
    assert all(fact.evidence_id in {trace.evidence_id for trace in result.tool_execution_trace} for fact in result.observed_facts)
    storage.save_inspection.assert_not_called()


@pytest.mark.parametrize("remaining,expected", [(60, 30), (18, 16), (14.9, 12), (3.9, 1)])
def test_final_request_respects_remaining_budget_and_reserve(remaining, expected):
    service, generator = service_for(warning_storage(), [], AgentLimits(final_model_timeout_seconds=30))
    state = RequestState("INSP-000001", deadline=100 + remaining)
    with patch("backend.agent.service.time.monotonic", return_value=100):
        assert service._request_timeout_seconds(state, True) == expected
    generator.assert_not_called()


@pytest.mark.parametrize("remaining", [2.9, 2, 0, -1, float("nan"), float("inf")])
def test_insufficient_or_invalid_budget_rejected_before_generation(remaining):
    service, generator = service_for(warning_storage(), [], AgentLimits(final_model_timeout_seconds=30))
    state = RequestState("INSP-000001", deadline=100 + remaining)
    contents = [types.Content(role="user", parts=[types.Part.from_text(text="{}")])]
    with patch("backend.agent.service.time.monotonic", return_value=100):
        with pytest.raises(AgentFailure, match="AGENT_TIMEOUT"):
            asyncio.run(service._generate(service.client, "gemini-mock", contents, state, 1, structured=True))
    generator.assert_not_called()


def test_investigation_is_not_extended_or_sent_beyond_remaining_time():
    service, generator = service_for(warning_storage(), [])
    with patch("backend.agent.service.time.monotonic", return_value=100):
        with pytest.raises(AgentFailure, match="AGENT_TIMEOUT"):
            service._request_timeout_seconds(RequestState("INSP-000001", deadline=114), False)


def test_final_sdk_server_504_keeps_safe_http_mapping_and_no_retry():
    failure = errors.ServerError(504, {"error": {"status": "DEADLINE_EXCEEDED", "message": "PRIVATE"}})
    service, generator = service_for(warning_storage(), [*calls(), failure], AgentLimits(final_model_timeout_seconds=30))
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "GEMINI_REQUEST_FAILED" and ERROR_STATUS[result.error_code] == 502
    assert generator.await_count == 3 and len(result.tool_execution_trace) == 3
    history = result.tool_execution_trace[-1]
    assert history.origin == "BACKEND_POLICY" and history.executed and history.error_code == "DATA_UNAVAILABLE"
    assert not history.success and history.evidence_id is None
    assert generator.call_args.kwargs["config"].http_options.timeout == 30000
    assert "PRIVATE" not in result.model_dump_json()


@pytest.mark.parametrize("elapsed,expected,status", [(45.2, 12000, "COMPLETED"), (58.1, None, "FAILED")])
def test_real_analysis_deadline_is_request_local_and_checked_before_final_sdk(elapsed, expected, status):
    service, generator = service_for(warning_storage(), [*calls(), warning_report], AgentLimits(final_model_timeout_seconds=30))
    clock = [100.0]
    original = generator.side_effect
    count = [0]

    async def generate(**kwargs):
        result = await original(**kwargs)
        count[0] += 1
        if count[0] == 2:
            clock[0] = 100 + elapsed
        return result

    generator.side_effect = generate
    with patch("backend.agent.service.time.monotonic", side_effect=lambda: clock[0]):
        result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == status
    if expected is None:
        assert result.error_code == "AGENT_TIMEOUT" and generator.await_count == 2
    else:
        assert generator.call_args.kwargs["config"].http_options.timeout == expected
    assert service.limits.final_model_timeout_seconds == 30 and service.limits.request_timeout_seconds == 60


def test_real_sdk_shared_client_overrides_stale_header_and_preserves_other_headers():
    observed = []

    def respond(request):
        body = json.loads(request.content)
        observed.append((request.headers["X-Server-Timeout"], request.extensions["timeout"]["read"]))
        assert request.headers["X-Custom-Fixture"] == "retained"
        assert request.headers["Authorization"] == "Bearer offline-fixture"
        if body.get("generationConfig", {}).get("responseMimeType") == "application/json":
            payload = simple_payload({"contents": [types.Content.model_validate(content) for content in body["contents"]]})
            parts = [{"text": json.dumps(payload)}]
        else:
            parts = [{"functionCall": {"name": "get_inspection_result", "args": {"inspection_id": "INSP-000001"}, "id": "offline-call"}}]
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}]})

    client = genai.Client(api_key="offline-placeholder", vertexai=False, http_options=types.HttpOptions(
        api_version="v1beta", timeout=15000, retry_options=types.HttpRetryOptions(attempts=1),
        headers={"X-Server-Timeout": "15", "X-Custom-Fixture": "retained", "Authorization": "Bearer offline-fixture"},
        async_client_args={"transport": httpx.MockTransport(respond)}))
    storage = warning_storage()
    storage.get_inspection.return_value = make_record()
    template, generator = service_for(storage, [])

    async def run():
        try:
            for seconds in (30, 15):
                service = AgentService(template.tools, settings=template.settings, client=client,
                    limits=AgentLimits(final_model_timeout_seconds=seconds))
                assert (await service.analyze("INSP-000001")).analysis_status == "COMPLETED"
        finally:
            await client.aio.aclose()

    try:
        asyncio.run(run())
    finally:
        client.close()
    assert observed == [("15", 15), ("30", 30), ("15", 15), ("15", 15)]
    assert client._api_client._http_options.headers["X-Server-Timeout"] == "15"
