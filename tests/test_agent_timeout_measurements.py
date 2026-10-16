"""Safe manual timeout observers exercised with the real SDK and MockTransport."""

import asyncio
import json
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import patch

from google import genai
from google.genai import _api_client, errors, types
import httpx
import pytest

from scripts.agent_validation_measurements import (
    MODEL_REQUEST, WAIT_DEADLINE, NOT_OBSERVABLE, attempt_paths, model_request_context,
    plan_attempt, prepare_attempt, request_budget_measurements, sdk_timeout_measurements,
    transport_timeout_measurements, validate_ready_attempt, wait_deadline_context,
)


@pytest.fixture(autouse=True)
def no_external_transport():
    with patch.object(httpx.HTTPTransport, "handle_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(_api_client.BaseApiClient, "_use_aiohttp", return_value=False):
        yield


@pytest.mark.parametrize("failure", [False, True])
def test_real_sdk_boundary_records_15_30_15_and_final_504_without_secrets(failure):
    sdk_entries, transmissions = [], []
    original_send = httpx.AsyncClient.send

    def response(request):
        assert request.headers["Authorization"] == "Bearer PRIVATE_AUTH"
        assert request.headers["X-Fixture"] == "PRIVATE_CUSTOM"
        status = 504 if failure and len(transmissions) == 2 else 200
        if status == 504:
            return httpx.Response(status, json={"error": {"code": 504, "status": "DEADLINE_EXCEEDED", "message": "PRIVATE_ERROR"}})
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": "{}"}]}, "finishReason": "STOP"}]})

    async def observe_send(instance, request, **kwargs):
        entry = {"stage": sdk_entries[-1]["stage"], "sequence": len(transmissions) + 1,
            **transport_timeout_measurements(request, sdk_entries[-1]["sdk_timeout_ms"]),
            **request_budget_measurements()}
        transmissions.append(entry)
        result = await original_send(instance, request, **kwargs)
        entry["status"] = result.status_code
        return result

    client = genai.Client(api_key="PRIVATE_FAKE_KEY", vertexai=False, http_options=types.HttpOptions(
        api_version="v1beta", timeout=15000, retry_options=types.HttpRetryOptions(attempts=1),
        headers={"X-Server-Timeout": "15", "Authorization": "Bearer PRIVATE_AUTH", "X-Fixture": "PRIVATE_CUSTOM"},
        async_client_args={"transport": httpx.MockTransport(response)}))
    service = SimpleNamespace(limits=SimpleNamespace(request_timeout_seconds=60))
    state = SimpleNamespace(deadline=time.monotonic() + 60, snapshot={"private": "PRIVATE_SNAPSHOT"})

    async def run():
        try:
            for seconds in (15, 30, 15):
                config = types.GenerateContentConfig(http_options=types.HttpOptions(timeout=seconds * 1000,
                    retry_options=types.HttpRetryOptions(attempts=1), headers={"X-Server-Timeout": str(seconds)}))
                stage = "STRUCTURED_OUTPUT" if seconds == 30 else "FUNCTION_CALLING"
                if seconds == 30:
                    config.response_mime_type = "application/json"
                    config.response_json_schema = {"type": "object", "properties": {"summary": {"type": "string"}}}
                with model_request_context(service, state), wait_deadline_context(seconds):
                    entry = {"stage": stage, **sdk_timeout_measurements(config)}
                    sdk_entries.append(entry)
                    try:
                        await asyncio.wait_for(client.aio.models.generate_content(model="gemini-3.8-flash",
                            contents="PRIVATE_SYNTHETIC_PROMPT", config=config), seconds)
                    except errors.ServerError:
                        entry["failure_stage"] = stage
                        break
        finally:
            await client.aio.aclose()

    try:
        with patch.object(httpx.AsyncClient, "send", observe_send):
            asyncio.run(run())
    finally:
        client.close()
    expected = [15, 30] if failure else [15, 30, 15]
    assert [entry["sdk_timeout_ms"] for entry in sdk_entries] == [seconds * 1000 for seconds in expected]
    assert [entry["server_timeout_seconds"] for entry in transmissions] == expected
    assert [entry["transport_timeout_seconds"]["read"] for entry in transmissions] == expected
    assert [entry["local_wait_timeout_seconds"] for entry in transmissions] == expected
    assert all(entry["server_timeout_conflict"] is False and entry["transport_timeout_conflict"] is False for entry in transmissions)
    assert all(entry["agent_limit_seconds"] == 60 and 0 < entry["remaining_agent_budget_seconds"] <= 60 for entry in transmissions)
    assert all(entry["request_deadline_monotonic"] <= entry["agent_deadline_monotonic"] - 2 for entry in transmissions)
    assert all(entry["sdk_retry_attempts"] == 1 for entry in sdk_entries)
    assert transmissions[-1]["status"] == (504 if failure else 200)
    assert "PRIVATE_" not in json.dumps({"sdk": sdk_entries, "http": transmissions})
    assert MODEL_REQUEST.get() is None and WAIT_DEADLINE.get() is None


@pytest.mark.parametrize("extension", [None, {}, {"private": "PRIVATE_SECRET"}])
def test_unobservable_transport_is_not_invented(extension):
    request = httpx.Request("POST", "https://mock.invalid", extensions={} if extension is None else {"timeout": extension})
    measured = transport_timeout_measurements(request, 30000)
    assert measured["transport_timeout_seconds"] == NOT_OBSERVABLE
    assert measured["server_timeout_seconds"] == NOT_OBSERVABLE
    assert "PRIVATE_" not in json.dumps(measured)


@pytest.mark.parametrize("header", ["PRIVATE_SECRET", "15,30", "999999999999999999999", "nan"])
def test_arbitrary_server_header_text_is_never_recorded(header):
    request = httpx.Request("POST", "https://mock.invalid", headers={"X-Server-Timeout": header,
        "Authorization": "PRIVATE_AUTH", "Cookie": "PRIVATE_COOKIE"})
    measured = transport_timeout_measurements(request, 30000)
    assert measured["server_timeout_seconds"] == NOT_OBSERVABLE
    assert "PRIVATE_" not in json.dumps(measured)


def test_stale_server_header_is_detected_without_modifying_request():
    request = httpx.Request("POST", "https://mock.invalid", headers={"X-Server-Timeout": "15"},
        extensions={"timeout": {"connect": 30, "read": 30, "write": 30, "pool": 30}})
    before = list(request.headers.raw)
    measured = transport_timeout_measurements(request, 30000)
    assert measured["server_timeout_conflict"] is True and measured["transport_timeout_conflict"] is False
    assert request.headers.raw == before


def test_context_does_not_capture_settings_or_snapshot_and_resets_on_error():
    service = SimpleNamespace(limits=SimpleNamespace(request_timeout_seconds=60), settings="PRIVATE_SETTINGS")
    state = SimpleNamespace(deadline=time.monotonic() + 60, snapshot="PRIVATE_SNAPSHOT")
    config = types.GenerateContentConfig(http_options=types.HttpOptions(timeout=30000,
        headers={"Authorization": "PRIVATE_AUTH"}, retry_options=types.HttpRetryOptions(attempts=1)))
    with pytest.raises(RuntimeError):
        with model_request_context(service, state), wait_deadline_context(30):
            assert "PRIVATE_" not in json.dumps(sdk_timeout_measurements(config))
            raise RuntimeError("CONTROLLED_FAILURE")
    assert request_budget_measurements()["agent_limit_seconds"] == NOT_OBSERVABLE
    assert sdk_timeout_measurements(SimpleNamespace())["sdk_timeout_ms"] == NOT_OBSERVABLE


@pytest.mark.parametrize("suffix", ["ready", "lock", "result"])
def test_preparation_cannot_reuse_any_existing_artifact(tmp_path, suffix):
    paths = attempt_paths(tmp_path, "old_attempt")
    paths[suffix].write_text("OLD_ARTIFACT", encoding="utf-8")
    with pytest.raises(ValueError, match="ATTEMPT_COLLISION"):
        prepare_attempt(tmp_path, "old_attempt", "INSP-001398")
    assert paths[suffix].read_text(encoding="utf-8") == "OLD_ARTIFACT"


def test_preparation_is_ready_only_and_preserves_old_locked_round(tmp_path):
    old = attempt_paths(tmp_path, "old_attempt")
    old["lock"].write_text("OLD_LOCK", encoding="utf-8")
    old["result"].write_text("OLD_RESULT", encoding="utf-8")
    with patch("google.genai.Client", side_effect=AssertionError("NETWORK_FORBIDDEN")) as constructor:
        manifest = prepare_attempt(tmp_path, "new_attempt", "INSP-001398")
        validate_ready_attempt(tmp_path, "new_attempt", "INSP-001398")
    constructor.assert_not_called()
    paths = attempt_paths(tmp_path, "new_attempt")
    assert manifest["state"] == "READY" and manifest["analysis_attempts"] == manifest["gemini_http_requests"] == 0
    assert not paths["lock"].exists() and not paths["result"].exists()
    assert old["lock"].read_text(encoding="utf-8") == "OLD_LOCK"
    assert old["result"].read_text(encoding="utf-8") == "OLD_RESULT"
    with pytest.raises(ValueError, match="ATTEMPT_COLLISION"):
        prepare_attempt(tmp_path, "new_attempt", "INSP-001398")


@pytest.mark.parametrize("artifact", ["lock", "result"])
def test_ready_manifest_does_not_bypass_execution_artifacts(tmp_path, artifact):
    prepare_attempt(tmp_path, "new_attempt", "INSP-001398")
    attempt_paths(tmp_path, "new_attempt")[artifact].write_text("USED", encoding="utf-8")
    with pytest.raises(ValueError, match="ATTEMPT_ALREADY_USED"):
        validate_ready_attempt(tmp_path, "new_attempt", "INSP-001398")


@pytest.mark.parametrize("identifier", ["../escape", "C:/private", "bad\n", "a" * 65])
def test_attempt_id_does_not_accept_paths_or_control_characters(tmp_path, identifier):
    with pytest.raises(ValueError, match="INVALID_ATTEMPT_ID"):
        plan_attempt(tmp_path, identifier, "INSP-001398")
