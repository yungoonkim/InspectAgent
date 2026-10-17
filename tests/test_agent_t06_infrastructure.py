"""T06 preparation and single-run controls in isolated temporary storage only."""

import importlib.util
import json
import logging
from pathlib import Path
from unittest.mock import Mock, patch
import warnings

from google.genai import _api_client, types
import httpx
import pytest

from backend.agent import api
from backend.agent.service import AgentService, CORE_FIELDS
from backend.config import Settings, get_settings
from backend.storage import JsonlInspectionStorage
from scripts.agent_validation_measurements import (
    attempt_paths, plan_attempt, prepare_attempt, validate_attempt_timeout,
)
from tests.test_agent_tools import make_record


TARGET = "INSP-001406"
ATTEMPT = "t06_operational_mock_1"
FINAL30_ATTEMPT = "t06_operational_groundtruth_isolated_final30_1"


@pytest.fixture(autouse=True)
def deny_external_transport(monkeypatch):
    monkeypatch.delenv("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", raising=False)
    with patch.object(httpx.HTTPTransport, "handle_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(_api_client.BaseApiClient, "_use_aiohttp", return_value=False):
        yield


@pytest.mark.parametrize("attempt,seconds,process", [(ATTEMPT, 15, None), (ATTEMPT, 15, "15"), (FINAL30_ATTEMPT, 30, "30")])
def test_t06_plan_and_process_contract_are_explicit(tmp_path, attempt, seconds, process):
    manifest = plan_attempt(tmp_path, attempt, TARGET, scenario="T06", final_timeout=seconds)
    assert manifest["state"] == "READY" and manifest["inspection_id"] == TARGET
    assert manifest["timeouts_seconds"] == dict(investigation=15, final_ceiling=seconds, overall=60, reserve=2)
    assert list(tmp_path.iterdir()) == []
    prepare_attempt(tmp_path, attempt, TARGET, scenario="T06", final_timeout=seconds)
    assert validate_attempt_timeout(tmp_path, attempt, TARGET, scenario="T06", configured_timeout=seconds,
                                    process_timeout=process) == manifest


@pytest.mark.parametrize("scenario,attempt,target,timeout", [
    ("T06", ATTEMPT, "INSP-001405", 15), ("T06", ATTEMPT, "INSP-000001", 15),
    ("T05", "t05_operational_mock_1", TARGET, 15), ("T03", "t03_mock", TARGET, 30),
    ("T05", ATTEMPT, "INSP-001405", 15), ("T06", "t05_round", TARGET, 15),
    ("T06", "t06_operational_mock_0", TARGET, 15), ("T06", ATTEMPT, TARGET, 30),
    ("T06", FINAL30_ATTEMPT, TARGET, 15), ("T06", FINAL30_ATTEMPT + "0", TARGET, 30),
    ("T06", "t06_operational_groundtruth_isolated_1", TARGET, 30),
    ("T06", FINAL30_ATTEMPT, "INSP-001405", 30),
    ("T03", FINAL30_ATTEMPT, TARGET, 30), ("T05", FINAL30_ATTEMPT, "INSP-001405", 30),
])
def test_scenario_target_round_and_timeout_cannot_be_mixed(tmp_path, scenario, attempt, target, timeout):
    with pytest.raises(ValueError, match="INVALID_ATTEMPT_SETTINGS"):
        prepare_attempt(tmp_path, attempt, target, scenario=scenario, final_timeout=timeout)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("artifact", ["ready", "lock", "result"])
@pytest.mark.parametrize("attempt,seconds", [(ATTEMPT, 15), (FINAL30_ATTEMPT, 30)])
def test_t06_existing_artifact_blocks_preparation_without_overwrite(tmp_path, artifact, attempt, seconds):
    path = attempt_paths(tmp_path, attempt)[artifact]
    path.write_bytes(b"PRESERVE")
    with pytest.raises(ValueError, match="ATTEMPT_COLLISION"):
        prepare_attempt(tmp_path, attempt, TARGET, scenario="T06", final_timeout=seconds)
    assert path.read_bytes() == b"PRESERVE"


@pytest.mark.parametrize("scenario,target,seconds", [("T03", "INSP-001398", 30), ("T05", "INSP-001405", 15), ("T05", "INSP-001405", 30)])
def test_legacy_scenarios_keep_timeout_contract(tmp_path, scenario, target, seconds):
    prepare_attempt(tmp_path, "legacy_round", target, scenario=scenario, final_timeout=seconds)
    manifest = validate_attempt_timeout(tmp_path, "legacy_round", target, scenario=scenario,
        configured_timeout=seconds, process_timeout=str(seconds))
    assert manifest["scenario"] == scenario and manifest["timeouts_seconds"]["final_ceiling"] == seconds
    ready = attempt_paths(tmp_path, "legacy_round")["ready"]
    original = ready.read_bytes()
    with patch("google.genai.Client", side_effect=AssertionError("NETWORK_FORBIDDEN")) as constructor, \
         pytest.raises(ValueError, match="^INVALID_ATTEMPT_SETTINGS$"):
        validate_attempt_timeout(tmp_path, "legacy_round", target, scenario="T06",
            configured_timeout=seconds, process_timeout=str(seconds))
    constructor.assert_not_called()
    assert ready.read_bytes() == original
    assert not attempt_paths(tmp_path, "legacy_round")["lock"].exists()
    assert not attempt_paths(tmp_path, "legacy_round")["result"].exists()


@pytest.mark.parametrize("field,value", [("scenario", "T05"), ("scenario", "T03"),
    ("inspection_id", "INSP-001405"), ("attempt_id", "t05_round"), ("state", "COMPLETED"),
    ("approval_required", False), ("model", "different-model"), ("schema_version", 2)])
@pytest.mark.parametrize("attempt,seconds", [(ATTEMPT, 15), (FINAL30_ATTEMPT, 30)])
def test_valid_t06_settings_reject_modified_ready_as_manifest_error(tmp_path, field, value, attempt, seconds):
    prepare_attempt(tmp_path, attempt, TARGET, scenario="T06", final_timeout=seconds)
    paths = attempt_paths(tmp_path, attempt)
    manifest = json.loads(paths["ready"].read_text(encoding="utf-8"))
    manifest[field] = value
    paths["ready"].write_text(json.dumps(manifest), encoding="utf-8")
    original = paths["ready"].read_bytes()
    with pytest.raises(ValueError, match="^INVALID_READY_MANIFEST$"):
        validate_attempt_timeout(tmp_path, attempt, TARGET, scenario="T06", configured_timeout=seconds, process_timeout=str(seconds))
    assert paths["ready"].read_bytes() == original
    assert not paths["lock"].exists() and not paths["result"].exists()


def test_final30_requires_explicit_selection_and_preserves_default(tmp_path):
    assert plan_attempt(tmp_path, ATTEMPT, TARGET, scenario="T06", final_timeout=15)["timeouts_seconds"]["final_ceiling"] == 15
    assert Settings(_env_file=None, GEMINI_API_KEY=None).AGENT_FINAL_MODEL_TIMEOUT_SECONDS == 15
    for attempt in (ATTEMPT, FINAL30_ATTEMPT):
        with pytest.raises(ValueError, match="^INVALID_ATTEMPT_SETTINGS$"):
            prepare_attempt(tmp_path, attempt, TARGET, scenario="T06")
    for scenario, target in (("T03", "INSP-001398"), ("T05", "INSP-001405"), ("T06", TARGET)):
        with pytest.raises(ValueError, match="^INVALID_ATTEMPT_SETTINGS$"):
            prepare_attempt(tmp_path, "invalid_round", target, scenario=scenario, final_timeout=None)
    assert not list(tmp_path.iterdir())


def test_final30_environment_does_not_leak_to_default_context(monkeypatch):
    with monkeypatch.context() as child:
        child.setenv("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", "30")
        assert Settings(_env_file=None, GEMINI_API_KEY=None).AGENT_FINAL_MODEL_TIMEOUT_SECONDS == 30
    assert Settings(_env_file=None, GEMINI_API_KEY=None).AGENT_FINAL_MODEL_TIMEOUT_SECONDS == 15


@pytest.mark.parametrize("attempt,seconds", [(ATTEMPT, 15), (FINAL30_ATTEMPT, 30)])
@pytest.mark.parametrize("mutation", ["process", "ready_timeout", "other_round"])
def test_final30_distinguishes_process_mismatch_from_ready_tampering(tmp_path, attempt, seconds, mutation):
    prepare_attempt(tmp_path, attempt, TARGET, scenario="T06", final_timeout=seconds)
    paths = attempt_paths(tmp_path, attempt)
    manifest = json.loads(paths["ready"].read_text(encoding="utf-8"))
    selected = seconds
    if mutation == "process":
        selected = 45 - seconds
        expected = "ATTEMPT_PROCESS_TIMEOUT_MISMATCH"
    else:
        if mutation == "ready_timeout":
            manifest["timeouts_seconds"]["final_ceiling"] = 45 - seconds
        else:
            manifest = plan_attempt(tmp_path, FINAL30_ATTEMPT if seconds == 15 else ATTEMPT, TARGET,
                                    scenario="T06", final_timeout=45 - seconds)
        paths["ready"].write_text(json.dumps(manifest), encoding="utf-8")
        expected = "INVALID_READY_MANIFEST"
    original = paths["ready"].read_bytes()
    with pytest.raises(ValueError, match=f"^{expected}$"):
        validate_attempt_timeout(tmp_path, attempt, TARGET, scenario="T06", configured_timeout=selected,
                                 process_timeout=str(selected))
    assert paths["ready"].read_bytes() == original
    assert not paths["lock"].exists() and not paths["result"].exists()


@pytest.mark.parametrize("attempt,seconds", [("t06_operational_groundtruth_isolated_1", 15), (FINAL30_ATTEMPT, 30)])
@pytest.mark.parametrize("artifact", ["lock", "result"])
def test_final30_and_consumed_default_round_cannot_be_reused(tmp_path, attempt, seconds, artifact):
    prepare_attempt(tmp_path, attempt, TARGET, scenario="T06", final_timeout=seconds)
    paths = attempt_paths(tmp_path, attempt)
    paths[artifact].write_bytes(b"PRESERVE")
    original = {name: path.read_bytes() for name, path in paths.items() if path.exists()}
    with pytest.raises(ValueError, match="^ATTEMPT_ALREADY_USED$"):
        validate_attempt_timeout(tmp_path, attempt, TARGET, scenario="T06", configured_timeout=seconds, process_timeout=str(seconds))
    assert original == {name: path.read_bytes() for name, path in paths.items() if path.exists()}


@pytest.mark.parametrize("configured,process,expected", [(30, None, "PROCESS_SETTINGS_TIMEOUT_MISMATCH"),
    (15, "30", "PROCESS_SETTINGS_TIMEOUT_MISMATCH"), (15, "invalid", "INVALID_PROCESS_TIMEOUT"),
    (0, None, "INVALID_ATTEMPT_TIMEOUT")])
def test_process_errors_do_not_become_manifest_errors(tmp_path, configured, process, expected):
    prepare_attempt(tmp_path, ATTEMPT, TARGET, scenario="T06", final_timeout=15)
    paths = attempt_paths(tmp_path, ATTEMPT)
    original = paths["ready"].read_bytes()
    with pytest.raises(ValueError, match=f"^{expected}$"):
        validate_attempt_timeout(tmp_path, ATTEMPT, TARGET, scenario="T06",
            configured_timeout=configured, process_timeout=process)
    assert paths["ready"].read_bytes() == original
    assert not paths["lock"].exists() and not paths["result"].exists()


@pytest.fixture
def manual_runner(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "data/outputs/manual_validation/run_t06_simple_e2e_once.py"
    previous_logging = logging.root.manager.disable
    previous_warnings = list(warnings.filters)
    try:
        with patch("google.genai.Client", side_effect=AssertionError("IMPORT_MUST_NOT_CONNECT")) as client:
            spec = importlib.util.spec_from_file_location("offline_t06_controls", source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        client.assert_not_called()
        runner = module.runner
        storage = JsonlInspectionStorage(tmp_path / "data/inspections.jsonl", tmp_path / "data/inspection_logs.jsonl")
        storage.save_inspection(make_record(inspection_id=TARGET))
        for name in ("patchcore_bottle.ckpt", "model_metadata.json"):
            path = tmp_path / "models/patchcore" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"PROTECTED_FIXTURE")
        settings = Settings(_env_file=None, GEMINI_API_KEY="OFFLINE_KEY", GEMINI_MODEL="gemini-3.8-flash",
            AGENT_FINAL_MODEL_TIMEOUT_SECONDS=15, INSPECTIONS_FILE=str(tmp_path / "data/inspections.jsonl"),
            INSPECTION_LOGS_FILE=str(tmp_path / "data/inspection_logs.jsonl"))
        output = tmp_path / "manual"
        output.mkdir()
        for name, value in {"ROOT": tmp_path, "OUTPUT": output, "ATTEMPT": ATTEMPT, "SETTINGS": settings}.items():
            monkeypatch.setattr(runner, name, value)
        monkeypatch.setattr(runner.controls, "ROOT", tmp_path)
        monkeypatch.setattr(runner.controls, "SETTINGS", settings)
        monkeypatch.setattr(runner, "PROTECTED", set(tmp_path / path for path in runner.controls.hashes()))
        monkeypatch.setattr(runner, "get_inspection_storage", lambda: storage)
        monkeypatch.setattr(api, "get_inspection_storage", lambda: storage)
        monkeypatch.setattr(runner.sys, "addaudithook", Mock())
        original_execute = runner.execute

        async def execute():
            with patch.dict(runner.app.dependency_overrides, {get_settings: lambda: settings}):
                await original_execute()

        monkeypatch.setattr(runner, "execute", execute)
        yield module, storage
    finally:
        logging.disable(previous_logging)
        warnings.filters[:] = previous_warnings


def test_prepare_and_offline_modes_do_not_analyze_or_claim_validation(manual_runner, monkeypatch):
    module, storage = manual_runner
    runner = module.runner
    with patch.object(AgentService, "analyze", side_effect=AssertionError("ANALYSIS_FORBIDDEN")) as analyze:
        manifest = module.prepare()
        monkeypatch.setattr(runner.sys, "argv", ["runner", "--attempt-id", ATTEMPT, "--offline-only"])
        module.main()
    analyze.assert_not_called()
    assert manifest["scenario"] == "T06"
    assert runner.REPORT["offline_preflight"] == "PASS"
    assert runner.REPORT["analysis_attempts"] == runner.REPORT["api_post_count"] == 0
    assert runner.REPORT["evidence_verification"] == runner.REPORT["pydantic_validation"] == "NOT TESTED"
    assert runner.REPORT["sdk_requests"] == runner.REPORT["http_transmissions"] == []
    assert "OFFLINE_KEY" not in json.dumps(manifest) + json.dumps(runner.REPORT)
    assert set(path.name for path in runner.OUTPUT.iterdir()) == {ATTEMPT + "_ready.json"}


@pytest.mark.parametrize("field,value", [("status", "FAILED"), ("result", "NG"), ("final_result", "ERROR"),
    ("final_reason_code", "INSPECTION_FAILED"), ("image_quality_status", "ERROR"),
    ("defect_detection_status", "SKIPPED"), ("anomaly_score", None)])
def test_preparation_checks_stored_normal_state_before_creating_ready(manual_runner, field, value):
    module, storage = manual_runner
    record = storage.get_inspection(TARGET).model_copy(update={field: value})
    with patch.object(storage, "get_inspection", return_value=record), pytest.raises(RuntimeError, match="T06_PREFLIGHT_BLOCKED"):
        module.prepare()
    assert not list(module.runner.OUTPUT.iterdir())


@pytest.mark.parametrize("problem", ["missing_ready", "process30", "settings30", "wrong_target", "missing_key", "used_lock", "used_result"])
def test_preflight_blocks_before_analysis(manual_runner, monkeypatch, problem):
    module, storage = manual_runner
    runner = module.runner
    if problem != "missing_ready":
        module.prepare()
    if problem == "process30":
        monkeypatch.setenv("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", "30")
    elif problem == "settings30":
        runner.SETTINGS.AGENT_FINAL_MODEL_TIMEOUT_SECONDS = 30
    elif problem == "wrong_target":
        runner.TARGET = "INSP-001405"
    elif problem == "missing_key":
        runner.SETTINGS.GEMINI_API_KEY = None
    elif problem.startswith("used_"):
        attempt_paths(runner.OUTPUT, ATTEMPT)[problem.removeprefix("used_")].write_bytes(b"PRESERVE")
    monkeypatch.setattr(runner.sys, "argv", ["runner", "--attempt-id", ATTEMPT, "--approved-single-analysis"])
    with patch.object(AgentService, "analyze", side_effect=AssertionError("ANALYSIS_FORBIDDEN")) as analyze, \
         pytest.raises(RuntimeError, match="T06_PREFLIGHT_BLOCKED"):
        module.main()
    analyze.assert_not_called()
    assert runner.REPORT["offline_preflight"] == "BLOCKED" and runner.REPORT["analysis_attempts"] == 0


@pytest.mark.parametrize("arguments", [[], ["--attempt-id", ATTEMPT], ["--prepare-only"],
    ["--attempt-id", ATTEMPT, "--offline-only", "--approved-single-analysis"]])
def test_cli_never_defaults_to_execution(manual_runner, monkeypatch, arguments):
    module, storage = manual_runner
    monkeypatch.setattr(module.runner.sys, "argv", ["runner", *arguments])
    with patch.object(module.runner, "main") as main, pytest.raises(SystemExit):
        module.main()
    main.assert_not_called()
    assert not list(module.runner.OUTPUT.iterdir())


def test_final30_cli_preparation_and_offline_check_never_analyze(manual_runner, monkeypatch):
    module, storage = manual_runner
    runner = module.runner
    runner.SETTINGS.AGENT_FINAL_MODEL_TIMEOUT_SECONDS = 30
    monkeypatch.setenv("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", "30")
    parent_environment = dict(runner.os.environ)
    with patch.object(AgentService, "analyze", side_effect=AssertionError("ANALYSIS_FORBIDDEN")) as analyze:
        monkeypatch.setattr(runner.sys, "argv", ["runner", "--attempt-id", FINAL30_ATTEMPT,
            "--prepare-only", "--prepare-final-timeout", "30"])
        module.main()
        monkeypatch.setattr(runner.sys, "argv", ["runner", "--attempt-id", FINAL30_ATTEMPT, "--offline-only"])
        module.main()
    analyze.assert_not_called()
    assert dict(runner.os.environ) == parent_environment
    assert runner.REPORT["offline_preflight"] == "PASS"
    assert runner.REPORT["final_timeout_ceiling_seconds"] == 30
    assert runner.REPORT["actual_final_timeout_seconds"] == "NOT TESTED"
    assert runner.REPORT["evidence_verification"] == runner.REPORT["pydantic_validation"] == "NOT TESTED"
    assert runner.REPORT["analysis_attempts"] == runner.REPORT["api_post_count"] == 0
    assert runner.REPORT["http_transmissions"] == []
    assert set(path.name for path in runner.OUTPUT.iterdir()) == {FINAL30_ATTEMPT + "_ready.json"}


@pytest.mark.parametrize("problem", ["missing_selection", "missing_environment", "wrong_settings"])
def test_final30_preparation_requires_agreed_explicit_settings(manual_runner, monkeypatch, problem):
    module, storage = manual_runner
    module.runner.ATTEMPT = FINAL30_ATTEMPT
    module.runner.SETTINGS.AGENT_FINAL_MODEL_TIMEOUT_SECONDS = 15 if problem == "wrong_settings" else 30
    if problem != "missing_environment":
        monkeypatch.setenv("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", "30")
    with pytest.raises(RuntimeError, match="^T06_PREFLIGHT_BLOCKED$"):
        module.prepare(**({} if problem == "missing_selection" else {"final_timeout": 30}))
    assert not list(module.runner.OUTPUT.iterdir())
    assert module.runner.REPORT["analysis_attempts"] == 0


@pytest.mark.parametrize("mode", ["--offline-only", "--approved-single-analysis"])
def test_final30_cli_cannot_override_existing_execution_profile(manual_runner, monkeypatch, mode):
    module, storage = manual_runner
    monkeypatch.setattr(module.runner.sys, "argv", ["runner", "--attempt-id", FINAL30_ATTEMPT,
        mode, "--prepare-final-timeout", "30"])
    with patch.object(module.runner, "main") as main, pytest.raises(SystemExit):
        module.main()
    main.assert_not_called()
    assert not list(module.runner.OUTPUT.iterdir())


@pytest.mark.parametrize("failure_stage", [None, "FUNCTION_CALLING", "STRUCTURED_OUTPUT"])
@pytest.mark.parametrize("attempt,seconds", [(ATTEMPT, 15), (FINAL30_ATTEMPT, 30)])
def test_full_manual_runner_uses_real_sdk_mock_transport_and_blocks_second_run(manual_runner, monkeypatch, failure_stage, attempt, seconds):
    module, storage = manual_runner
    runner = module.runner
    runner.ATTEMPT = attempt
    runner.SETTINGS.AGENT_FINAL_MODEL_TIMEOUT_SECONDS = seconds
    monkeypatch.setenv("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", str(seconds))
    module.prepare(final_timeout=seconds)
    before = runner.controls.hashes()
    packets = []

    def respond(request):
        wire = json.loads(request.content)
        packets.append(wire)
        runner.controls.assert_safe(wire)
        structured = wire.get("generationConfig", {}).get("responseMimeType") == "application/json"
        if failure_stage == ("STRUCTURED_OUTPUT" if structured else "FUNCTION_CALLING"):
            return httpx.Response(504, json={"error": {"code": 504, "status": "DEADLINE_EXCEEDED", "message": "PRIVATE_FAILURE"}})
        if not structured:
            parts = [{"functionCall": {"name": "get_inspection_result", "args": {"inspection_id": TARGET}, "id": "result-call"}}]
        else:
            catalog = json.loads(wire["contents"][0]["parts"][0]["text"])["catalog"]
            core = {name: next(entry["token"] for entry in catalog if entry["source_field"] == f"/data/{name}") for name in CORE_FIELDS}
            payload = {"overall_summary": "NORMAL_MODEL_RESULT", "observed_fact_refs": list(core.values()), "possible_causes": [],
                "recommended_checks": ["CONTINUE_MONITORING:" + core["final_result"]], "limitations": []}
            parts = [{"text": json.dumps(payload)}]
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15}})

    from google import genai
    original_client = genai.Client

    def client_factory(**kwargs):
        options = kwargs["http_options"]
        assert options.retry_options.attempts == 1 and options.timeout == 15000
        return original_client(api_key="OFFLINE_KEY", vertexai=False, http_options=types.HttpOptions(api_version="v1beta",
            timeout=15000, retry_options=types.HttpRetryOptions(attempts=1), async_client_args={"transport": httpx.MockTransport(respond)}))

    monkeypatch.setattr(runner, "client_factory", client_factory)
    monkeypatch.setattr(runner.sys, "argv", ["runner", "--attempt-id", attempt, "--approved-single-analysis"])
    module.main()
    report = runner.REPORT
    assert report["analysis_attempts"] == report["api_post_count"] == 1
    assert len(packets) == (1 if failure_stage == "FUNCTION_CALLING" else 2)
    assert report["automatic_retries"] is False
    assert report["timeout_propagation_valid"] is True
    expected = [15] if failure_stage == "FUNCTION_CALLING" else [15, seconds]
    assert [entry["sdk_timeout_ms"] for entry in report["sdk_requests"]] == [value * 1000 for value in expected]
    assert all(entry["sdk_retry_attempts"] == 1 for entry in report["sdk_requests"])
    assert [entry["local_wait_timeout_seconds"] for entry in report["http_transmissions"]] == expected
    assert [entry["server_timeout_seconds"] for entry in report["http_transmissions"]] == expected
    assert [entry["transport_timeout_seconds"]["read"] for entry in report["http_transmissions"]] == expected
    assert all(entry["agent_limit_seconds"] == 60 for entry in report["http_transmissions"])
    if failure_stage is None:
        assert report["result"] == "PASS" and report["fastapi_http_status"] == 200
        assert report["analysis_status"] == "COMPLETED" and report["agent_tool_executions"] == 1
        assert report["verified_fact_count"] == 6 and report["verdict_unchanged"]
        assert report["early_exit_checks"][-1]["policy"] == "NORMAL"
        assert report["pydantic_validation"] == report["evidence_verification"] == "PASS"
    else:
        assert report["result"] == "FAIL" and report["fastapi_http_status"] == 502
        assert report["failure_stage"] == failure_stage
        assert report["evidence_verification"] == "NOT TESTED"
    paths = attempt_paths(runner.OUTPUT, attempt)
    saved = paths["result"].read_bytes()
    assert b"OFFLINE_KEY" not in saved and b"PRIVATE_FAILURE" not in saved
    assert before == runner.controls.hashes()
    monkeypatch.setattr(runner.sys, "argv", ["runner", "--attempt-id", attempt, "--approved-single-analysis"])
    with pytest.raises(RuntimeError, match="T06_PREFLIGHT_BLOCKED"):
        module.main()
    assert paths["result"].read_bytes() == saved and len(packets) == report["actual_http_requests"]
