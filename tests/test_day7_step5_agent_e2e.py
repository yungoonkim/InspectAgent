import asyncio
from copy import deepcopy
import hashlib
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient
from google.genai import _api_client, errors, types
import pytest

from backend.agent.api import AgentRuntime, get_agent_service, get_analysis_storage
from backend.agent.reporting import CORE_FIELDS
from backend.agent.schemas import AgentLimits
from backend.agent.service import AgentService
from backend.agent.tools import InspectionTools
from backend.config import Settings, get_settings
from backend.main import app
from backend.storage import InspectionStorageBase, JsonlInspectionStorage
from tests.agent_error_fixtures import error_logs, error_record
from tests.test_agent_reporting_integration import simple_payload
from tests.test_agent_service import call_response, text_response
from tests.test_agent_tools import make_log, make_record


class FakeGemini:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.closed = False
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self.generate_content), aclose=self.aclose)

    async def generate_content(self, **request):
        self.requests.append(deepcopy(request))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response(**request) if callable(response) else response

    async def aclose(self):
        self.closed = True

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def forbid_google_network(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("REAL_GEMINI_FORBIDDEN"))
    monkeypatch.setattr(_api_client.BaseApiClient, "request", forbidden)
    monkeypatch.setattr(_api_client.BaseApiClient, "async_request", forbidden)
    monkeypatch.setattr("backend.agent.service.genai.Client", forbidden)
    yield
    forbidden.assert_not_called()


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage = JsonlInspectionStorage(tmp_path / "inspections.jsonl", tmp_path / "logs.jsonl")
    settings = Settings(_env_file=None, ENABLE_PATCHCORE=False, GEMINI_API_KEY=None, GEMINI_MODEL="gemini-mock")
    monkeypatch.setattr("backend.main.get_settings", lambda: settings)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_analysis_storage] = lambda: storage
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield SimpleNamespace(storage=storage, settings=settings, client=client, directory=tmp_path)
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def file_state(directory):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.glob("*.jsonl")}


def final_response(**request):
    payload = simple_payload(request)
    packet = json.loads(request["contents"][0].parts[0].text)
    quality = [entry for entry in packet["catalog"] if entry["source_tool"] == "analyze_image_quality"]
    if quality:
        payload["observed_fact_refs"].extend(entry["token"] for entry in quality if entry["token"] not in payload["observed_fact_refs"])
        warning = next(entry for entry in quality if entry["source_field"] == "/data/image_quality_status")
        payload["possible_causes"] = ["ILLUMINATION_CHANGE:" + warning["token"]]
        payload["recommended_checks"] = ["LIGHTING_EXPOSURE_CHECK:" + warning["token"]]
    return text_response(json.dumps(payload))


def install(environment, responses, limits=None):
    fake = FakeGemini(responses)
    service = AgentService(InspectionTools(environment.storage), settings=environment.settings, client=fake,
                           limits=limits or AgentLimits())
    app.dependency_overrides[get_agent_service] = lambda: service
    return fake, service


@pytest.mark.parametrize("scenario,identifier,verdict", [
    ("T01", "INSP-001396", "OK"), ("T03", "INSP-001398", "REINSPECT"),
    ("T06", "INSP-001390", "OK"), ("MOCK_NG", "INSP-001391", "NG"),
    ("ERROR", "INSP-009990", "ERROR"),
])
def test_synthetic_http_function_calling_e2e(environment, scenario, identifier, verdict):
    changes = {"inspection_id": identifier}
    if scenario == "T03":
        changes.update(image_quality_status="WARNING_LOW_BRIGHTNESS", final_result="REINSPECT",
                       final_reason_code="IMAGE_QUALITY_WARNING",
                       metrics={**make_record().metrics, "mean": 60.0,
                                "applied_thresholds": {"low_threshold": 100, "high_threshold": 200}})
    elif scenario == "MOCK_NG":
        changes.update(result="NG", final_result="NG", final_reason_code="MODEL_ANOMALY", anomaly_score=45.0)
    record = error_record(**changes) if scenario == "ERROR" else make_record(**changes)
    environment.storage.save_inspection(record)
    if scenario == "T03":
        environment.storage.save_inspection(make_record(inspection_id="INSP-009989", timestamp="2026-10-14T01:00:00Z"))
    for event in error_logs() if scenario == "ERROR" else [make_log()]:
        environment.storage.save_log(event.model_copy(update={"inspection_id": identifier}))
    calls = [call_response(("get_inspection_result", {"inspection_id": identifier}))]
    if scenario == "T03":
        calls.append(call_response(("analyze_image_quality", {"inspection_id": identifier})))
    elif scenario in {"MOCK_NG", "ERROR"}:
        calls.extend([call_response(("get_execution_logs", {"inspection_id": identifier})), text_response()]
                     if scenario == "MOCK_NG" else [call_response(("get_execution_logs", {"inspection_id": identifier}))])
    fake, service = install(environment, [*calls, final_response])
    before = file_state(environment.directory)
    response = environment.client.post(f"/analyze/{identifier}")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["analysis_status"] == "COMPLETED" and report["final_result"] == verdict
    assert report["inspection_snapshot"]["anomaly_score"] == record.anomaly_score
    assert file_state(environment.directory) == before
    assert report["model_availability"] == "NOT_TESTED"
    traces = {entry["evidence_id"]: entry for entry in report["tool_execution_trace"] if entry["success"]}
    assert all(traces[fact["evidence_id"]]["tool_name"] == fact["source_tool"] for fact in report["observed_facts"])
    assert all(cause["is_hypothesis"] for cause in report["possible_causes"])
    assert "get_inspection_result" in report["tools_used"]
    if scenario == "T03":
        assert "analyze_image_quality" in report["tools_used"]
        assert any(entry["tool_name"] == "get_inspection_history" and entry["origin"] == "BACKEND_POLICY"
                   for entry in report["tool_execution_trace"])
    if scenario == "MOCK_NG":
        assert any("테스트 fixture" in entry for entry in report["limitations"])
    if scenario == "ERROR":
        assert report["inspection_result"] == "UNKNOWN" and report["inspection_snapshot"]["anomaly_score"] is None
    saved = environment.client.get(f"/inspections/{identifier}/agent-report")
    assert saved.status_code == 200 and saved.json()["analysis_id"] == report["analysis_id"]
    assert len(fake.requests) == len(calls) + 1
    final = fake.requests[-1]
    assert final["config"].tools is None and final["config"].response_mime_type == "application/json"
    assert final["config"].http_options.retry_options.attempts == 1
    sent = json.dumps([content.model_dump(mode="json") for content in final["contents"]])
    assert "IMG-BOTTLE" not in sent and record.product_id not in sent


@pytest.mark.parametrize("stage", ["TOOL_ROUND_1", "STRUCTURED_REPORT"])
@pytest.mark.parametrize("status,provider", [(400,"INVALID_ARGUMENT"), (401,"UNAUTHENTICATED"),
    (403,"PERMISSION_DENIED"), (429,"RESOURCE_EXHAUSTED"), (500,"INTERNAL"), (503,"UNAVAILABLE")])
def test_provider_errors_are_safe_and_not_retried(environment, caplog, status, provider, stage):
    environment.storage.save_inspection(make_record())
    exception_type = errors.ClientError if status < 500 else errors.ServerError
    exception = exception_type(status, {"error": {"code": status, "status": provider,
        "message": "PRIVATE_PROMPT_FULL C:\\private\\image.png secret=UNREDACTED_SECRET"}})
    replies = [exception] if stage == "TOOL_ROUND_1" else [
        call_response(("get_inspection_result", {"inspection_id":"INSP-000001"})), exception]
    fake, service = install(environment, replies)
    before = file_state(environment.directory)
    with caplog.at_level(logging.ERROR, logger="backend.agent.service"):
        response = environment.client.post("/analyze/INSP-000001")
    assert response.status_code == 502 and response.json()["detail"]["error_code"] == "GEMINI_REQUEST_FAILED"
    assert len(fake.requests) == len(replies) and file_state(environment.directory) == before
    assert "PRIVATE_PROMPT_FULL" not in caplog.text and "UNREDACTED_SECRET" not in caplog.text
    assert "image.png" not in caplog.text
    for field in ("correlation_id=INSP-000001", f"stage={stage}", "model=gemini-mock",
                  f"http_status={status}", f"provider_code={provider}", "exception_class="):
        assert field in caplog.text


@pytest.mark.parametrize("exception,expected,status", [
    (TimeoutError(), "GEMINI_TIMEOUT", 504),
    (ConnectionError("PRIVATE_PROMPT_FULL"), "GEMINI_REQUEST_FAILED", 502),
    (RuntimeError("PRIVATE_PROMPT_FULL"), "GEMINI_REQUEST_FAILED", 502),
])
def test_transport_and_sdk_failures(environment, caplog, exception, expected, status):
    environment.storage.save_inspection(make_record())
    fake, service = install(environment, [exception])
    response = environment.client.post("/analyze/INSP-000001")
    assert response.status_code == status and response.json()["detail"]["error_code"] == expected
    assert len(fake.requests) == 1
    assert "PRIVATE_PROMPT_FULL" not in caplog.text and "PRIVATE_PROMPT_FULL" not in response.text


@pytest.mark.parametrize("name,arguments,expected", [
    ("delete_all", {"inspection_id":"INSP-000001"}, "TOOL_NOT_ALLOWED"),
    ("get_inspection_result", {"inspection_id":"INSP-000002"}, "INSPECTION_SCOPE_MISMATCH"),
    ("get_inspection_result", {"inspection_id":True}, "TOOL_ARGUMENT_INVALID"),
    ("get_inspection_result", {"inspection_id":"INSP-000001", "path":"forbidden"}, "TOOL_ARGUMENT_INVALID"),
    ("get_inspection_result", {}, "TOOL_ARGUMENT_INVALID"),
])
def test_hostile_calls_are_rejected_before_tool_execution(environment, name, arguments, expected):
    environment.storage.save_inspection(make_record())
    fake, service = install(environment, [call_response((name, arguments))])
    service.tools = Mock(spec=InspectionTools)
    response = environment.client.post("/analyze/INSP-000001")
    assert response.status_code == 502 and response.json()["detail"]["error_code"] == expected
    assert not service.tools.mock_calls and len(fake.requests) == 1


@pytest.mark.parametrize("mutation,expected", [("empty","MODEL_RESPONSE_INVALID"),
    ("max_tokens","MODEL_RESPONSE_INCOMPLETE"), ("malformed","FINAL_JSON_INVALID"),
    ("evidence","EVIDENCE_MISMATCH"), ("pointer","EVIDENCE_MISMATCH"),
    ("value","RESPONSE_SCHEMA_INVALID"), ("verdict","EVIDENCE_MISMATCH")])
def test_invalid_provider_output_never_changes_inspection(environment, mutation, expected):
    environment.storage.save_inspection(make_record())
    def final(**request):
        payload = simple_payload(request)
        if mutation == "malformed":
            return text_response("{")
        if mutation in {"evidence", "pointer"}:
            payload["observed_fact_refs"][0] = "E9999" if mutation == "evidence" else "/data/forged"
        elif mutation == "value":
            payload["observed_value"] = 999
        elif mutation == "verdict":
            payload["overall_summary"] = "PRODUCT_ANOMALY"
        return text_response(json.dumps(payload))
    responses = [call_response(("get_inspection_result", {"inspection_id":"INSP-000001"})), final]
    if mutation == "empty":
        responses = [types.GenerateContentResponse(candidates=[])]
    elif mutation == "max_tokens":
        responses = [text_response("partial", finish=types.FinishReason.MAX_TOKENS)]
    fake, service = install(environment, responses)
    before = file_state(environment.directory)
    response = environment.client.post("/analyze/INSP-000001")
    assert response.status_code == 502 and response.json()["detail"]["error_code"] == expected
    assert file_state(environment.directory) == before
    assert len(fake.requests) == len(responses)


@pytest.mark.parametrize("constraint,expected", [("repeat","TOOL_REPEAT_LIMIT"),
    ("calls","TOOL_CALL_LIMIT"), ("rounds","TOOL_ROUND_LIMIT")])
def test_limits_bound_multi_call_execution(environment, constraint, expected):
    environment.storage.save_inspection(make_record())
    calls = [("get_execution_logs", {"inspection_id":"INSP-000001"})] * 3
    limits = AgentLimits(max_tool_calls=1) if constraint == "calls" else AgentLimits(max_tool_rounds=1) if constraint == "rounds" else AgentLimits()
    replies = [call_response(*calls)] if constraint != "rounds" else [call_response(calls[0]), call_response(calls[0])]
    fake, service = install(environment, replies, limits)
    response = environment.client.post("/analyze/INSP-000001")
    assert response.status_code == 502 and response.json()["detail"]["error_code"] == expected
    assert len(fake.requests) <= 2


def test_concurrent_requests_keep_catalogs_and_evidence_separate():
    storage = Mock(spec=InspectionStorageBase)
    records = {identifier: make_record(inspection_id=identifier, anomaly_score=score)
               for identifier, score in [("INSP-000001", 11.0), ("INSP-000002", 22.0)]}
    storage.get_inspection.side_effect = records.get
    async def generate(**request):
        await asyncio.sleep(0)
        if request["config"].response_mime_type:
            return final_response(**request)
        identifier = next(identifier for identifier in records if identifier in request["contents"][0].parts[0].text)
        return call_response(("get_inspection_result", {"inspection_id":identifier}))
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    service = AgentService(InspectionTools(storage), client=client,
                           settings=SimpleNamespace(GEMINI_MODEL="gemini-mock"), limits=AgentLimits())
    async def run():
        return await asyncio.gather(*(service.analyze(identifier) for identifier in records))
    results = asyncio.run(run())
    assert [result.inspection_snapshot["anomaly_score"] for result in results] == [11.0, 22.0]
    assert all(result.analysis_status == "COMPLETED" for result in results)
    assert all({fact.evidence_id for fact in result.observed_facts} == {"E0001"} for result in results)
    storage.save_inspection.assert_not_called()


def test_real_runtime_lifecycle_uses_only_a_fake_constructor(environment, monkeypatch):
    fake = FakeGemini([])
    constructor = Mock(return_value=fake)
    monkeypatch.setattr("backend.agent.api.genai.Client", constructor)
    settings = environment.settings.model_copy(update={"GEMINI_API_KEY":"OFFLINE_SYNTHETIC_NOT_A_KEY"})
    async def run():
        runtime = AgentRuntime()
        first = await runtime.service(InspectionTools(environment.storage), settings)
        second = await runtime.service(InspectionTools(environment.storage), settings)
        assert first.client is second.client is fake
        await runtime.aclose()
    asyncio.run(run())
    assert constructor.call_count == 1 and fake.closed
    options = constructor.call_args.kwargs["http_options"]
    assert options.api_version == "v1beta" and options.retry_options.attempts == 1


def test_owned_fake_client_closes_even_when_async_cleanup_fails(environment, monkeypatch):
    fake = FakeGemini([RuntimeError("PRIVATE_PROMPT_FULL")])
    fake.aio.aclose = AsyncMock(side_effect=RuntimeError("cleanup failure"))
    fake.close = Mock()
    monkeypatch.setattr("backend.agent.service.genai.Client", Mock(return_value=fake))
    settings = environment.settings.model_copy(update={"GEMINI_API_KEY":"OFFLINE_SYNTHETIC_NOT_A_KEY"})
    service = AgentService(InspectionTools(environment.storage), settings=settings, limits=AgentLimits())
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "GEMINI_REQUEST_FAILED"
    assert len(fake.requests) == 1
    fake.close.assert_called_once()
