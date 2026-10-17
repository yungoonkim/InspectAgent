"""Prepared-round timeout contracts and offline SDK propagation, never live Gemini."""

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

from google import genai
from google.genai import _api_client, models, types
import httpx
import pytest

from backend.agent.schemas import AgentLimits
from backend.agent.service import AgentService, RequestState
from backend.agent.tools import InspectionTools
from backend.config import Settings
from backend.storage import InspectionStorageBase
from scripts.agent_validation_measurements import (
    attempt_paths, model_request_context, prepare_attempt, request_budget_measurements,
    sdk_timeout_measurements, transport_timeout_measurements, validate_attempt_timeout, wait_deadline_context,
)
from tests.test_agent_error_measurements import manual_runner
from tests.test_agent_t05_preflight import failed_storage


@pytest.fixture(autouse=True)
def deny_external_transport(monkeypatch):
    monkeypatch.delenv("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", raising=False)
    with patch.object(httpx.HTTPTransport, "handle_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(_api_client.BaseApiClient, "_use_aiohttp", return_value=False):
        yield


@pytest.mark.parametrize("seconds", [15, 30])
def test_prepared_configuration_matches_process_without_any_execution(tmp_path, seconds):
    manifest = prepare_attempt(tmp_path, "t05_round", "INSP-000001", scenario="T05", final_timeout=seconds)
    actual = validate_attempt_timeout(tmp_path, "t05_round", "INSP-000001",
        configured_timeout=seconds, process_timeout=str(seconds))
    assert actual == manifest and actual["state"] == "READY" and actual["approval_required"]
    assert actual["analysis_attempts"] == actual["gemini_http_requests"] == 0
    assert not attempt_paths(tmp_path, "t05_round")["lock"].exists()
    assert not attempt_paths(tmp_path, "t05_round")["result"].exists()


@pytest.mark.parametrize("prepared,selected", [(15, 30), (30, 15)])
def test_round_and_process_cannot_be_mixed(tmp_path, prepared, selected):
    prepare_attempt(tmp_path, "t05_round", "INSP-000001", scenario="T05", final_timeout=prepared)
    with pytest.raises(ValueError, match="ATTEMPT_PROCESS_TIMEOUT_MISMATCH"):
        validate_attempt_timeout(tmp_path, "t05_round", "INSP-000001", configured_timeout=selected, process_timeout=str(selected))


@pytest.mark.parametrize("value", [None, True, False, 0, -1, 16, 31, 30.0, "30"])
def test_invalid_settings_are_rejected(tmp_path, value):
    with pytest.raises(ValueError, match="INVALID_ATTEMPT_TIMEOUT"):
        validate_attempt_timeout(tmp_path, "t05_round", "INSP-000001", configured_timeout=value)


@pytest.mark.parametrize("value", ["", "0", "31", "30.0", " 30", "030", "nan", True])
def test_invalid_process_environment_is_rejected(tmp_path, value):
    with pytest.raises(ValueError, match="INVALID_PROCESS_TIMEOUT"):
        validate_attempt_timeout(tmp_path, "t05_round", "INSP-000001", configured_timeout=30, process_timeout=value)


def test_thirty_seconds_requires_explicit_process_selection_not_only_settings(tmp_path):
    prepare_attempt(tmp_path, "t05_round", "INSP-000001", scenario="T05", final_timeout=30)
    with pytest.raises(ValueError, match="PROCESS_SETTINGS_TIMEOUT_MISMATCH"):
        validate_attempt_timeout(tmp_path, "t05_round", "INSP-000001", configured_timeout=30)


def test_default_remains_fifteen_and_environment_is_not_mutated(tmp_path, monkeypatch):
    prepare_attempt(tmp_path, "t05_round", "INSP-000001", scenario="T05", final_timeout=15)
    validate_attempt_timeout(tmp_path, "t05_round", "INSP-000001", configured_timeout=15)
    assert Settings(_env_file=None, GEMINI_API_KEY=None).AGENT_FINAL_MODEL_TIMEOUT_SECONDS == 15
    monkeypatch.setenv("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", "30")
    assert Settings(_env_file=None, GEMINI_API_KEY=None).AGENT_FINAL_MODEL_TIMEOUT_SECONDS == 30
    monkeypatch.delenv("AGENT_FINAL_MODEL_TIMEOUT_SECONDS")
    assert Settings(_env_file=None, GEMINI_API_KEY=None).AGENT_FINAL_MODEL_TIMEOUT_SECONDS == 15


def test_missing_approved_preparation_is_blocked(tmp_path):
    with pytest.raises(ValueError, match="READY_CONFIGURATION_MISSING"):
        validate_attempt_timeout(tmp_path, "t05_round", "INSP-000001", configured_timeout=15)


def test_unreadable_preparation_is_safely_blocked(tmp_path):
    prepare_attempt(tmp_path, "t05_round", "INSP-000001", scenario="T05", final_timeout=15)
    with patch("pathlib.Path.read_text", side_effect=PermissionError("PRIVATE_ERROR")):
        with pytest.raises(ValueError, match="INVALID_READY_MANIFEST"):
            validate_attempt_timeout(tmp_path, "t05_round", "INSP-000001", configured_timeout=15)


@pytest.mark.parametrize("mutation", ["id", "target", "state", "approval", "model", "overall", "reserve", "investigation", "extra"])
def test_prepared_configuration_contract_is_exact(tmp_path, mutation):
    prepare_attempt(tmp_path, "t05_round", "INSP-000001", scenario="T05", final_timeout=30)
    path = attempt_paths(tmp_path, "t05_round")["ready"]
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if mutation in {"overall", "reserve", "investigation"}:
        manifest["timeouts_seconds"][mutation] = 120
    else:
        field, value = {"id": ("attempt_id", "different_round"), "target": ("inspection_id", "INSP-000002"),
            "state": ("state", "COMPLETED"), "approval": ("approval_required", False),
            "model": ("model", "different-model"), "extra": ("unexpected", True)}[mutation]
        manifest[field] = value
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="INVALID_READY_MANIFEST"):
        validate_attempt_timeout(tmp_path, "t05_round", "INSP-000001", configured_timeout=30, process_timeout="30")


@pytest.mark.parametrize("artifact", ["lock", "result"])
def test_existing_execution_artifacts_are_preserved_and_block_reuse(tmp_path, artifact):
    prepare_attempt(tmp_path, "t05_round", "INSP-000001", scenario="T05", final_timeout=30)
    path = attempt_paths(tmp_path, "t05_round")[artifact]
    path.write_bytes(b"PRESERVE")
    with pytest.raises(ValueError, match="ATTEMPT_ALREADY_USED"):
        validate_attempt_timeout(tmp_path, "t05_round", "INSP-000001", configured_timeout=30, process_timeout="30")
    assert path.read_bytes() == b"PRESERVE"


def test_new_thirty_second_round_never_relabels_original_fifteen(tmp_path):
    prepare_attempt(tmp_path, "t05_original", "INSP-000001", scenario="T05", final_timeout=15)
    original = attempt_paths(tmp_path, "t05_original")["ready"]
    before = original.read_bytes()
    prepare_attempt(tmp_path, "t05_final30", "INSP-000001", scenario="T05", final_timeout=30)
    validate_attempt_timeout(tmp_path, "t05_final30", "INSP-000001", configured_timeout=30, process_timeout="30")
    assert original.read_bytes() == before
    with pytest.raises(ValueError, match="ATTEMPT_COLLISION"):
        prepare_attempt(tmp_path, "t05_original", "INSP-000001", scenario="T05", final_timeout=30)


def prepare_thirty(module, monkeypatch):
    module.runner.ATTEMPT = "t05_final30_mock"
    module.prepare(final_timeout=30)
    module.runner.SETTINGS.AGENT_FINAL_MODEL_TIMEOUT_SECONDS = 30
    monkeypatch.setenv("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", "30")


def test_manual_preflight_supports_explicit_thirty_second_round(manual_runner, monkeypatch):
    module, storage = manual_runner
    old = attempt_paths(module.runner.OUTPUT, module.runner.ATTEMPT)["ready"]
    before = old.read_bytes()
    prepare_thirty(module, monkeypatch)
    with patch.object(AgentService, "analyze", side_effect=AssertionError("ANALYSIS_FORBIDDEN")) as analyze:
        module.offline_preflight()
    analyze.assert_not_called()
    assert module.runner.REPORT["final_timeout_ceiling_seconds"] == 30
    assert module.runner.REPORT["actual_final_timeout_seconds"] == "NOT TESTED"
    assert module.runner.REPORT["error_policy"]["required_fact_count"] == 17
    assert module.runner.REPORT["error_policy"]["report_validation_passed"] == "NOT TESTED"
    assert old.read_bytes() == before
    assert module.runner.REPORT["http_transmissions"] == []


def test_thirty_environment_does_not_automatically_switch_legacy_round(manual_runner, monkeypatch):
    module, storage = manual_runner
    module.runner.SETTINGS.AGENT_FINAL_MODEL_TIMEOUT_SECONDS = 30
    monkeypatch.setenv("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", "30")
    with pytest.raises(RuntimeError, match="ATTEMPT_CONFIGURATION_BLOCKED"):
        module.offline_preflight()
    assert module.runner.REPORT["preflight_error_code"] == "ATTEMPT_PROCESS_TIMEOUT_MISMATCH"
    assert module.runner.REPORT["offline_preflight"] == "BLOCKED"


def test_cli_selects_round_explicitly_without_executing_analysis(manual_runner, monkeypatch):
    module, storage = manual_runner
    prepare_thirty(module, monkeypatch)
    selected = module.runner.ATTEMPT
    module.runner.ATTEMPT = "t05_operational_error1"
    monkeypatch.setattr(module.runner.sys, "argv", ["runner", "--attempt-id", selected, "--offline-only"])
    with patch.object(module.runner, "main", side_effect=module.offline_preflight) as main:
        module.main()
    main.assert_called_once_with()
    assert module.runner.ATTEMPT == selected and module.runner.sys.argv == ["runner", "--offline-only"]
    assert module.runner.REPORT["analysis_attempts"] == 0


def test_cli_does_not_accept_preparation_override_in_execution_mode(manual_runner, monkeypatch):
    module, storage = manual_runner
    monkeypatch.setattr(module.runner.sys, "argv", ["runner", "--prepare-final-timeout", "30", "--offline-only"])
    with patch.object(module.runner, "main") as main, pytest.raises(SystemExit):
        module.main()
    main.assert_not_called()


@pytest.mark.parametrize("scenario,attempt,target", [("T05", "t05_final30", "INSP-000001"),
    ("T06", "t06_operational_groundtruth_isolated_final30_1", "INSP-001406")])
def test_selected_manifest_drives_real_sdk_mock_transport_timeouts(tmp_path, scenario, attempt, target):
    prepare_attempt(tmp_path, attempt, target, scenario=scenario, final_timeout=30)
    manifest = validate_attempt_timeout(tmp_path, attempt, target, scenario=scenario, configured_timeout=30, process_timeout="30")
    transmissions, requests = [], []
    original_send = httpx.AsyncClient.send
    original_generate = models.AsyncModels.generate_content
    original_wait = asyncio.wait_for

    def respond(request):
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": "{}"}]}, "finishReason": "STOP"}]})

    async def observe_send(instance, request, **kwargs):
        transmissions.append({**transport_timeout_measurements(request, requests[-1]["sdk_timeout_ms"]),
            **request_budget_measurements()})
        return await original_send(instance, request, **kwargs)

    async def observe_generate(instance, **kwargs):
        requests.append(sdk_timeout_measurements(kwargs["config"]))
        return await original_generate(instance, **kwargs)

    async def observe_wait(awaitable, timeout):
        with wait_deadline_context(timeout):
            return await original_wait(awaitable, timeout)

    client = genai.Client(api_key="PRIVATE_FAKE_KEY", vertexai=False, http_options=types.HttpOptions(
        api_version="v1beta", timeout=15000, headers={"X-Server-Timeout": "15"},
        retry_options=types.HttpRetryOptions(attempts=1), async_client_args={"transport": httpx.MockTransport(respond)}))
    service = AgentService(InspectionTools(Mock(spec=InspectionStorageBase)),
        settings=SimpleNamespace(GEMINI_MODEL="gemini-3.8-flash"), client=client,
        limits=AgentLimits(final_model_timeout_seconds=manifest["timeouts_seconds"]["final_ceiling"]))
    state = RequestState(target, deadline=time.monotonic() + 60)
    contents = [types.Content(role="user", parts=[types.Part.from_text(text="Offline synthetic input")])]

    async def run():
        try:
            for index, structured in enumerate((False, True, False), 1):
                with model_request_context(service, state):
                    await service._generate(client, service.settings.GEMINI_MODEL, contents, state, index, structured=structured)
        finally:
            await client.aio.aclose()

    try:
        with patch.object(httpx.AsyncClient, "send", observe_send), patch.object(models.AsyncModels, "generate_content", observe_generate), \
             patch("backend.agent.service.asyncio.wait_for", observe_wait):
            asyncio.run(run())
    finally:
        client.close()
    assert [entry["sdk_timeout_ms"] for entry in requests] == [15000, 30000, 15000]
    assert [entry["server_timeout_seconds"] for entry in transmissions] == [15, 30, 15]
    assert [entry["transport_timeout_seconds"]["read"] for entry in transmissions] == [15, 30, 15]
    assert [entry["local_wait_timeout_seconds"] for entry in transmissions] == [15, 30, 15]
    assert all(entry["agent_limit_seconds"] == 60 and entry["remaining_agent_budget_seconds"] <= 60 for entry in transmissions)
    assert transmissions[1]["request_deadline_monotonic"] <= state.deadline - 2
    assert all(entry["sdk_retry_attempts"] == 1 for entry in requests)
    assert all(entry["server_timeout_conflict"] is False and entry["transport_timeout_conflict"] is False for entry in transmissions)
    assert "PRIVATE_" not in json.dumps({"requests": requests, "transmissions": transmissions})
