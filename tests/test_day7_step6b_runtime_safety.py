"""Offline runtime, cross-process admission and request-budget regression tests."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from google.genai import _api_client, types
import httpx
import pytest

from backend.agent.api import AgentRuntime, get_agent_service, get_analysis_storage, router
from backend.agent.errors import AgentFailure
from backend.agent.runtime_safety import AnalysisAdmission, EXPECTED, verify_configuration
from backend.agent.schemas import AgentLimits
from backend.agent.service import AgentService, RequestState
from backend.agent.tools import InspectionTools
from backend.config import Settings, get_settings
from backend.storage import JsonlInspectionStorage
from tests.test_agent_service import call_response, text_response
from tests.test_agent_tools import make_record, make_log
from tests.test_agent_reporting_integration import simple_response
from tests.test_day7_step5_agent_e2e import FakeGemini, final_response


@pytest.fixture(autouse=True)
def forbid_real_sdk(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("REAL_GEMINI_FORBIDDEN"))
    monkeypatch.setattr(_api_client.BaseApiClient, "request", forbidden)
    monkeypatch.setattr(_api_client.BaseApiClient, "async_request", forbidden)
    monkeypatch.setattr("backend.agent.api.genai.Client", forbidden)
    yield
    forbidden.assert_not_called()


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None, ENABLE_PATCHCORE=False, GEMINI_API_KEY="OFFLINE_SYNTHETIC_NOT_A_KEY",
        OUTPUT_DIR=str(tmp_path / "output"),
        GEMINI_MODEL="gemini-3.8-flash", AGENT_MAX_TOOL_ROUNDS=4, AGENT_MAX_TOOL_CALLS=8,
        AGENT_MAX_REPEAT_CALLS=2, AGENT_REQUEST_TIMEOUT_SECONDS=60, AGENT_MODEL_TIMEOUT_SECONDS=15,
        AGENT_FINAL_MODEL_TIMEOUT_SECONDS=15, AGENT_TOOL_TIMEOUT_SECONDS=3, AGENT_MAX_PAYLOAD_BYTES=65536)
    storage = JsonlInspectionStorage(tmp_path / "inspections.jsonl", tmp_path / "logs.jsonl")
    storage.save_inspection(make_record())
    storage.save_log(make_log())
    fake = FakeGemini([call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})), final_response])
    runtime = AgentRuntime()
    runtime.admission = AnalysisAdmission(tmp_path / "analysis.lock")
    runtime._client = fake
    runtime._configuration = (settings.GEMINI_API_KEY, settings.AGENT_MODEL_TIMEOUT_SECONDS)
    app = FastAPI()
    app.include_router(router)
    app.state.agent_runtime = runtime
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_analysis_storage] = lambda: storage
    yield SimpleNamespace(app=app, settings=settings, storage=storage, fake=fake, runtime=runtime, directory=tmp_path)


def client_for(harness, peer="127.0.0.1", host="127.0.0.1"):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=harness.app, client=(peer, 12345)), base_url=f"http://{host}")


def test_effective_configuration_is_read_only_and_secret_free(harness):
    async def scenario():
        async with client_for(harness) as client:
            response = await client.get("/agent/runtime-safety")
            assert response.status_code == 200
            body = response.json()
            assert body["effective"] == EXPECTED and body["configuration_matches"]
            assert body["credentials_configured"] is True
            assert body["worker_count"] == "UNKNOWN"
            assert "OS_FILE_LOCK" in body["protection"]
            assert harness.settings.GEMINI_API_KEY not in response.text
            assert "runtime-safety" not in (await client.get("/openapi.json")).text
            assert harness.fake.requests == []
            assert not harness.runtime.admission.path.exists()
    asyncio.run(scenario())


@pytest.mark.parametrize("final_timeout", [15, 30])
def test_final_timeout_opt_in_preserves_runtime_policy_and_report(harness, final_timeout):
    harness.settings.AGENT_FINAL_MODEL_TIMEOUT_SECONDS = final_timeout
    before = {path.name: path.read_bytes() for path in harness.directory.glob("*.jsonl")}

    async def scenario():
        async with client_for(harness) as client:
            diagnostic = (await client.get("/agent/runtime-safety")).json()
            expected = {**EXPECTED, "final_model_timeout_seconds": final_timeout}
            assert diagnostic["configuration_matches"]
            assert diagnostic["effective"] == diagnostic["expected"] == expected
            assert harness.fake.requests == []
            response = await client.post("/analyze/INSP-000001")
            assert response.status_code == 200
            assert response.json()["final_result"] == "OK"
        configs = [request["config"] for request in harness.fake.requests]
        assert len(configs) == 2
        assert [config.http_options.timeout for config in configs] == [15000, final_timeout * 1000]
        assert [config.http_options.headers["X-Server-Timeout"] for config in configs] == ["15", str(final_timeout)]
        assert all(config.http_options.retry_options.attempts == 1 for config in configs)
        assert all(config.max_output_tokens == 4096 and config.thinking_config is None for config in configs)
        assert configs[-1].response_mime_type == "application/json"
        assert configs[-1].tools is None

    asyncio.run(scenario())
    assert {path.name: path.read_bytes() for path in harness.directory.glob("*.jsonl")} == before
    report = json.loads((harness.directory / "output/agent_reports/INSP-000001.json").read_text(encoding="utf-8"))
    assert report["provenance"] == "FAKE_TEST"


def test_final_timeout_must_match_configured_opt_in(harness):
    harness.settings.AGENT_FINAL_MODEL_TIMEOUT_SECONDS = 30
    with pytest.raises(AgentFailure, match="AGENT_RUNTIME_CONFIG_MISMATCH"):
        verify_configuration(harness.settings, AgentLimits(final_model_timeout_seconds=15))
    harness.fake.requests.clear()
    verify_configuration(harness.settings, AgentLimits(final_model_timeout_seconds=30))
    assert harness.fake.requests == []


@pytest.mark.parametrize("peer,host", [("198.51.100.1", "127.0.0.1"), ("127.0.0.1", "example.com")])
def test_diagnostics_are_local_only(harness, peer, host):
    async def scenario():
        async with client_for(harness, peer, host) as client:
            assert (await client.get("/agent/runtime-safety")).status_code == 404
    asyncio.run(scenario())


@pytest.mark.parametrize("field,value", [("GEMINI_MODEL", "gemini-unapproved"), ("AGENT_MAX_TOOL_ROUNDS", 5),
    ("AGENT_MAX_TOOL_CALLS", 9), ("AGENT_REQUEST_TIMEOUT_SECONDS", 61), ("AGENT_MODEL_TIMEOUT_SECONDS", 16),
    ("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", 16), ("AGENT_TOOL_TIMEOUT_SECONDS", 4)])
def test_configuration_mismatch_rejects_before_provider(harness, field, value):
    setattr(harness.settings, field, value)
    async def scenario():
        async with client_for(harness) as client:
            response = await client.post("/analyze/INSP-000001")
            assert response.status_code == 503
            assert response.json()["detail"]["error_code"] == "AGENT_RUNTIME_CONFIG_MISMATCH"
            assert not (await client.get("/agent/runtime-safety")).json()["configuration_matches"]
            assert harness.fake.requests == []
        with harness.runtime.admission.acquire():
            pass
    asyncio.run(scenario())


@pytest.mark.parametrize("name,value", [("API_VERSION", "v1"), ("SDK_ATTEMPTS", 2),
    ("PROVIDER_REQUEST_LIMIT", 7), ("version", lambda name: "unexpected")])
def test_sdk_policy_mismatch_fails_closed(harness, monkeypatch, name, value):
    monkeypatch.setattr(f"backend.agent.runtime_safety.{name}", value)
    with pytest.raises(AgentFailure, match="AGENT_RUNTIME_CONFIG_MISMATCH"):
        verify_configuration(harness.settings, AgentLimits())
    assert harness.fake.requests == []


def test_concurrent_http_requests_have_one_owner_and_get_remains_available(harness):
    before = {path.name: path.read_bytes() for path in harness.directory.glob("*.jsonl")}
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        original = harness.fake.aio.models.generate_content
        async def gated(**request):
            if not harness.fake.requests:
                entered.set()
                await release.wait()
            return await original(**request)
        harness.fake.aio.models.generate_content = gated
        async with client_for(harness) as client:
            first = asyncio.create_task(client.post("/analyze/INSP-000001"))
            try:
                await asyncio.wait_for(entered.wait(), 3)
                rejected = await client.post("/analyze/INSP-000001")
                assert rejected.status_code == 409
                assert rejected.json()["detail"]["error_code"] == "AGENT_BUSY"
                assert harness.fake.requests == []
                assert (await client.get("/agent/runtime-safety")).status_code == 200
            finally:
                release.set()
            response = await first
            assert response.status_code == 200, response.text
            assert response.json()["final_result"] == "OK"
            assert len(harness.fake.requests) == 2
            assert all(request["config"].http_options.retry_options.attempts == 1 for request in harness.fake.requests)
        with harness.runtime.admission.acquire():
            pass
    asyncio.run(scenario())
    assert {path.name: path.read_bytes() for path in harness.directory.glob("*.jsonl")} == before
    report = json.loads((harness.directory / "output/agent_reports/INSP-000001.json").read_text(encoding="utf-8"))
    assert report["provenance"] == "FAKE_TEST"


@pytest.mark.parametrize("failure,status", [(RuntimeError("PRIVATE"), 502), (TimeoutError(), 504)])
def test_provider_failure_releases_admission_without_retry(harness, failure, status):
    harness.fake.responses = iter([failure])
    async def scenario():
        async with client_for(harness) as client:
            response = await client.post("/analyze/INSP-000001")
            assert response.status_code == status
            assert "PRIVATE" not in response.text
            assert len(harness.fake.requests) == 1
            harness.fake.responses = iter([call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})), final_response])
            assert (await client.post("/analyze/INSP-000001")).status_code == 200
            assert len(harness.fake.requests) == 3
    asyncio.run(scenario())


def test_cancelled_request_releases_admission(harness):
    async def scenario():
        entered = asyncio.Event()
        async def waiting(**request):
            entered.set()
            await asyncio.Future()
        harness.fake.aio.models.generate_content = waiting
        async with client_for(harness) as client:
            pending = asyncio.create_task(client.post("/analyze/INSP-000001"))
            await asyncio.wait_for(entered.wait(), 3)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        with harness.runtime.admission.acquire():
            pass
    asyncio.run(scenario())


def test_distinct_runtime_instances_and_threads_share_os_lock(tmp_path):
    owner = AnalysisAdmission(tmp_path / "shared.lock")
    competitor = AnalysisAdmission(tmp_path / "shared.lock")
    def attempt():
        with pytest.raises(AgentFailure, match="AGENT_BUSY"):
            with competitor.acquire():
                pytest.fail("Second owner admitted")
    with ThreadPoolExecutor(max_workers=1) as executor:
        with owner.acquire():
            executor.submit(attempt).result(timeout=3)
    with competitor.acquire():
        pass


def test_another_process_cannot_acquire_and_can_acquire_after_release(tmp_path):
    owner = AnalysisAdmission(tmp_path / "process.lock")
    source_root = str(Path(__file__).resolve().parents[1])
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from backend.agent.runtime_safety import AnalysisAdmission; "
        "from backend.agent.errors import AgentFailure\n"
        "try:\n"
        "    with AnalysisAdmission(sys.argv[2]).acquire(): print('ACQUIRED')\n"
        "except AgentFailure as failure: print(failure.code)\n"
    )
    def probe():
        result = subprocess.run([sys.executable, "-B", "-c", code, source_root, str(owner.path)],
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()
    with owner.acquire():
        assert probe() == "AGENT_BUSY"
    assert probe() == "ACQUIRED"


def test_total_deadline_releases_admission(harness):
    service = AgentService(None, settings=harness.settings, client=harness.fake,
                           limits=AgentLimits(request_timeout_seconds=0.03))
    async def waiting(client, model, state):
        await asyncio.Future()
    service._run = waiting
    harness.app.dependency_overrides[get_agent_service] = lambda: service
    async def scenario():
        async with client_for(harness) as client:
            response = await client.post("/analyze/INSP-000001")
            assert response.status_code == 504
            assert response.json()["detail"]["error_code"] == "AGENT_TIMEOUT"
        with harness.runtime.admission.acquire():
            pass
        assert harness.fake.requests == []
    asyncio.run(scenario())


def test_admission_io_failure_fails_closed(tmp_path):
    with pytest.raises(AgentFailure, match="AGENT_ADMISSION_UNAVAILABLE"):
        with AnalysisAdmission(tmp_path / "missing" / "analysis.lock").acquire():
            pytest.fail("Unavailable lock admitted")


def test_six_provider_calls_then_seventh_blocked_and_next_request_independent(harness, caplog):
    service = AgentService(None, settings=harness.settings, client=harness.fake)
    harness.fake.responses = iter([text_response()] * 7)
    contents = [types.Content(role="user", parts=[types.Part.from_text(text="Synthetic offline input")])]
    async def scenario():
        state = RequestState("INSP-000001")
        for round_number in range(1, 7):
            await service._generate(harness.fake, harness.settings.GEMINI_MODEL, contents, state, round_number,
                                    structured=round_number == 6)
        with pytest.raises(AgentFailure, match="PROVIDER_REQUEST_LIMIT"):
            await service._generate(harness.fake, harness.settings.GEMINI_MODEL, contents, state, 7)
        assert state.provider_calls == 6 and len(harness.fake.requests) == 6
        next_state = RequestState("INSP-000002")
        await service._generate(harness.fake, harness.settings.GEMINI_MODEL, contents, next_state, 1)
        assert next_state.provider_calls == 1 and state.provider_calls == 6
        assert len(harness.fake.requests) == 7
    with caplog.at_level(logging.INFO, logger="backend.agent.service"):
        asyncio.run(scenario())
    assert "provider_request_number=6" in caplog.text
    assert "Synthetic offline input" not in caplog.text


@pytest.mark.parametrize("round_limit,expected_status,expected_error", [
    (4, "COMPLETED", None), (5, "FAILED", "PROVIDER_REQUEST_LIMIT"),
])
def test_multiround_loop_including_structured_report_respects_hard_cap(harness, round_limit, expected_status, expected_error):
    calls = [
        ("get_inspection_result", {"inspection_id": "INSP-000001"}),
        ("get_execution_logs", {"inspection_id": "INSP-000001"}),
        ("analyze_image_quality", {"inspection_id": "INSP-000001"}),
        ("get_inspection_history", {"product_id": "TARGET-PRODUCT", "limit": 5}),
        ("get_inspection_result", {"inspection_id": "INSP-000001"}),
    ]
    harness.fake.responses = iter([call_response(call) for call in calls[:round_limit]] + [text_response(), simple_response])
    service = AgentService(InspectionTools(harness.storage),
                           settings=harness.settings, client=harness.fake, limits=AgentLimits(max_tool_rounds=round_limit))
    service._investigation_ready = lambda state: False
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == expected_status and result.error_code == expected_error
    assert len(harness.fake.requests) == 6
    if expected_status == "COMPLETED":
        assert result.inspection_snapshot["final_result"] == "OK"
        assert harness.fake.requests[-1]["config"].response_mime_type == "application/json"
    assert harness.storage.get_inspection("INSP-000001").final_result == "OK"
