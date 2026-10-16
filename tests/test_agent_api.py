"""HTTP integration with injected Agent services and offline SDK responses."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import quote

import cv2
from fastapi.testclient import TestClient
import numpy as np
import pytest
from google.genai import errors

from backend.agent.api import ERROR_STATUS, get_agent_service, get_analysis_storage
from backend.agent.schemas import AgentLimits, AnalysisResponse, DiagnosisResult
from backend.config import Settings, get_settings
from backend.inspection import ImageRegistry
from backend.main import app
from backend.storage import JsonlInspectionStorage, StorageError
from tests.test_agent_tools import make_log, make_record
from tests.agent_error_fixtures import error_logs, error_record, with_error_facts
from tests.test_agent_service import report_response, call_response, normal_responses, report_payload, service_for, text_response, with_quality_facts


@pytest.fixture(autouse=True)
def prohibit_real_sdk_client():
    with patch("backend.agent.api.genai.Client", side_effect=AssertionError("Live Gemini forbidden in HTTP tests")) as constructor:
        yield constructor


@pytest.fixture
def harness(tmp_path, monkeypatch):
    storage = JsonlInspectionStorage(tmp_path / "inspections.jsonl", tmp_path / "logs.jsonl")
    record = storage.save_inspection(make_record())
    storage.save_log(make_log())
    settings = Settings(_env_file=None, ENABLE_PATCHCORE=False, GEMINI_API_KEY=None,
                        GEMINI_MODEL="gemini-mock", INSPECTIONS_FILE=str(tmp_path / "inspections.jsonl"),
                        INSPECTION_LOGS_FILE=str(tmp_path / "logs.jsonl"))
    service, generator = service_for(storage, normal_responses())
    valid_result = asyncio.run(service.analyze("INSP-000001"))
    agent = SimpleNamespace(analyze=AsyncMock(return_value=valid_result))
    original_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_analysis_storage] = lambda: storage
    app.dependency_overrides[get_agent_service] = lambda: agent
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr("backend.main.get_settings", lambda: settings)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, storage=storage, agent=agent, result=valid_result,
                              settings=settings, tmp_path=tmp_path, record=record)
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


def file_hashes(harness):
    return tuple(sha256(path.read_bytes()).hexdigest() for path in
                 (harness.tmp_path / "inspections.jsonl", harness.tmp_path / "logs.jsonl"))


def test_normal_analysis_http_contract_trace_and_jsonl_immutability(harness):
    before = file_hashes(harness)
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 200
    body = response.json()
    AnalysisResponse.model_validate(body)
    assert body["analysis_status"] == "COMPLETED"
    assert body["inspection_result"] == "OK"
    assert body["final_result"] == "OK"
    assert body["final_reason_code"] == "ALL_CHECKS_PASSED"
    assert body["analysis_id"].startswith("ANALYSIS-")
    assert body["timestamp"].endswith("+00:00")
    assert body["model_name"] == "gemini-mock"
    assert body["tools_used"] == ["get_inspection_result"]
    trace = body["tool_execution_trace"][0]
    assert trace["executed"] is True and trace["success"] is True
    assert trace["evidence_id"] == body["observed_facts"][0]["evidence_id"]
    harness.agent.analyze.assert_awaited_once_with("INSP-000001")
    assert file_hashes(harness) == before
    json.dumps(body, allow_nan=False)


@pytest.mark.parametrize("scenario", ["warning", "failed"])
def test_warning_and_failed_inspection_records_are_analyzable(harness, scenario):
    changes = ({"image_quality_status": "WARNING_LOW_BRIGHTNESS", "final_result": "REINSPECT",
                "final_reason_code": "IMAGE_QUALITY_WARNING", "metrics": {**make_record().metrics, "mean": 81.24}} if scenario == "warning" else
               {"status": "FAILED", "result": "UNKNOWN", "image_quality_status": "ERROR",
                "defect_detection_status": "SKIPPED", "final_result": "ERROR", "final_reason_code": "INSPECTION_FAILED",
                "anomaly_score": None})
    record = harness.storage.save_inspection(make_record(**changes))
    if scenario == "failed":
        record = harness.storage.save_inspection(error_record())
        harness.storage.save_logs(error_logs())
    summary = "REINSPECTION_REQUIRED" if scenario == "warning" else "INSPECTION_FAILED"
    payload = report_payload(record, summary)
    payload["recommended_checks"] = [{"check_code": "MANUAL_REINSPECTION", "evidence_refs": ["F0005"]}]
    responses = normal_responses(payload, continue_investigation=True)
    if scenario == "failed":
        payload = with_error_facts(payload, record, harness.storage.get_logs("INSP-000001"))
        responses = [call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})),
            call_response(("get_execution_logs", {"inspection_id": "INSP-000001"})), report_response(payload)]
    if scenario == "warning":
        payload = with_quality_facts(payload, record)
        responses = [call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})),
            call_response(("analyze_image_quality", {"inspection_id": "INSP-000001"})), report_response(payload)]
    service, generator = service_for(harness.storage, responses)
    app.dependency_overrides[get_agent_service] = lambda: service
    before = file_hashes(harness)
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 200
    assert response.json()["inspection_result"] == record.result
    assert response.json()["final_result"] == record.final_result
    assert response.json()["inspection_snapshot"]["status"] == record.status
    assert file_hashes(harness) == before


def test_missing_record_does_not_prepare_or_invoke_agent(harness):
    factory = Mock(return_value=harness.agent)
    app.dependency_overrides[get_agent_service] = factory
    response = harness.client.post("/analyze/INSP-999999")
    assert response.status_code == 404
    assert response.json() == {"detail": {"analysis_status": "FAILED", "error_code": "NOT_FOUND"}}
    factory.assert_not_called()
    harness.agent.analyze.assert_not_awaited()


@pytest.mark.parametrize("identifier", ["BAD", "INSP-1", "INSP-" + "1" * 100, "INSP-000001\n", "INSP-000001\x00", "..\\..\\private", "C:\\secret"])
def test_invalid_identifier_is_safely_rejected(harness, identifier):
    response = harness.client.post("/analyze/" + quote(identifier, safe=""))
    assert response.status_code == 422
    assert response.json() == {"detail": {"analysis_status": "FAILED", "error_code": "INVALID_ARGUMENT"}}
    harness.agent.analyze.assert_not_awaited()
    assert identifier not in response.text


def test_encoded_slash_traversal_does_not_match_analysis_route(harness):
    response = harness.client.post("/analyze/..%2F..%2Fapp%2Fsecret")
    assert response.status_code in (404, 422)
    assert "secret" not in response.text
    harness.agent.analyze.assert_not_awaited()


def test_missing_key_only_disables_analysis_and_keeps_existing_endpoints(harness, monkeypatch, prohibit_real_sdk_client):
    app.dependency_overrides.pop(get_agent_service)
    model = Mock(side_effect=AssertionError("PatchCore must not run"))
    monkeypatch.setattr("backend.main.get_patchcore_inferencer", model)
    registry = ImageRegistry()
    image_path = harness.tmp_path / "neutral.png"
    cv2.imwrite(str(image_path), np.full((10, 10, 3), 130, dtype=np.uint8))
    registry.register_image("IMG-BOTTLE-0001", image_path)
    monkeypatch.setattr("backend.main.get_image_registry", lambda settings: registry)
    monkeypatch.setattr("backend.main.get_inspection_storage", lambda: harness.storage)
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "MISSING_API_KEY"
    assert harness.client.get("/health").json() == {"status": "ok"}
    assert harness.client.get("/inspections/images").status_code == 200
    response = harness.client.post("/inspections", json={"product_id": "PROD-NEW", "image_id": "IMG-BOTTLE-0001"})
    assert response.status_code == 201
    assert response.json()["status"] == "COMPLETED"
    assert harness.client.get("/docs").status_code == 200
    model.assert_not_called()
    prohibit_real_sdk_client.assert_not_called()


@pytest.mark.parametrize("code,status", list(ERROR_STATUS.items()))
def test_agent_error_codes_map_to_safe_http_status(harness, code, status):
    harness.agent.analyze.return_value = DiagnosisResult(inspection_id="INSP-000001", analysis_status="FAILED",
                                                       error_code=code, model_name="/app/secret")
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == status
    assert response.json() == {"detail": {"analysis_status": "FAILED", "error_code": code}}
    assert "/app/" not in response.text


@pytest.mark.parametrize("failure,status,code", [(TimeoutError(), 504, "AGENT_TIMEOUT"),
                                               (RuntimeError("Traceback /app/key API_KEY broken_large"), 500, "AGENT_INTERNAL_ERROR")])
def test_unexpected_agent_exceptions_never_expose_details(harness, failure, status, code):
    harness.agent.analyze.side_effect = failure
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == status
    assert response.json()["detail"]["error_code"] == code
    assert "Traceback" not in response.text and "/app" not in response.text


def test_storage_lookup_failure_prevents_agent_call(harness):
    with patch.object(harness.storage, "get_inspection", side_effect=StorageError("C:\\private /app/key")):
        response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "STORAGE_ERROR"
    harness.agent.analyze.assert_not_awaited()


def test_storage_factory_failure_is_safe_and_id_validation_happens_first(harness):
    app.dependency_overrides.pop(get_analysis_storage)
    with patch("backend.agent.api.get_inspection_storage", side_effect=StorageError("Traceback /app/private")) as factory:
        assert harness.client.post("/analyze/BAD").status_code == 422
        factory.assert_not_called()
        response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "STORAGE_ERROR"


def test_bad_response_schema_is_not_http_success(harness):
    harness.agent.analyze.return_value = {"analysis_status": "COMPLETED", "secret": "/app/key"}
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 502
    assert response.json()["detail"]["error_code"] == "RESPONSE_SCHEMA_INVALID"
    assert "secret" not in response.text


@pytest.mark.parametrize("mutation", ["snapshot", "summary", "target", "error"])
def test_stored_verdict_is_authoritative_and_contradictions_are_rejected(harness, mutation):
    result = harness.result.model_copy(deep=True)
    if mutation == "snapshot":
        result.inspection_snapshot["result"] = "NG"
    elif mutation == "summary":
        result.overall_summary = "Gemini says NG /app/key"
    elif mutation == "target":
        result.inspection_id = "INSP-000002"
    else:
        result.error_code = "EVIDENCE_MISMATCH"
    harness.agent.analyze.return_value = result
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 502
    assert response.json()["detail"]["error_code"] == "EVIDENCE_MISMATCH"


def test_unknown_agent_error_is_normalized(harness):
    harness.agent.analyze.return_value = DiagnosisResult(inspection_id="INSP-000001", analysis_status="FAILED",
                                                       error_code="Traceback /app/key", model_name=None)
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 500
    assert response.json()["detail"]["error_code"] == "AGENT_INTERNAL_ERROR"


def test_real_agent_with_mock_sdk_verifies_evidence_over_http(harness):
    payload = report_payload()
    payload["observed_facts"][0]["observed_value"] = "FAILED"
    service, generator = service_for(harness.storage, normal_responses(payload))
    app.dependency_overrides[get_agent_service] = lambda: service
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 502
    assert response.json()["detail"]["error_code"] == "EVIDENCE_MISMATCH"
    assert generator.call_count == 2


def test_no_function_call_never_claims_tool_success_over_http(harness):
    service, generator = service_for(harness.storage, [text_response("I used all tools.")])
    app.dependency_overrides[get_agent_service] = lambda: service
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 502
    assert response.json()["detail"]["error_code"] == "INSUFFICIENT_EVIDENCE"
    assert "tool_execution_trace" not in response.json()["detail"]


def test_sensitive_original_data_is_not_exposed_in_success_response(harness):
    malicious = "Traceback C:\\private /app/key API_KEY broken_large contamination"
    harness.storage.save_inspection(make_record(image_id="IMG-BOTTLE-INJ-0001", product_id="PROD-T03",
                                               metrics={"mean": 81.24, "injection_factor": 0.6, "ground_truth": "NG", "secret": malicious}))
    harness.storage.save_log(make_log(message=malicious, metrics={"actual_label": "NG"}))
    responses = [call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}),
                               ("get_execution_logs", {"inspection_id": "INSP-000001"})),
                 report_response(report_payload())]
    service, generator = service_for(harness.storage, responses)
    app.dependency_overrides[get_agent_service] = lambda: service
    before = file_hashes(harness)
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 200
    for marker in ("injection_factor", "ground_truth", "actual_label", "IMG-BOTTLE-INJ", "PROD-T03", "broken_large", "API_KEY", "Traceback", "/app/", "C:\\"):
        assert marker not in response.text
    assert response.json()["inspection_result"] == "OK"
    assert response.json()["final_result"] == "OK"
    assert response.json()["tools_used"] == ["get_inspection_result", "get_execution_logs"]
    assert file_hashes(harness) == before


def test_legacy_missing_fields_are_returned_as_null(harness):
    legacy = {"inspection_id": "INSP-000002", "product_id": "PROD-OLD", "image_id": "IMG-BOTTLE-0002",
              "image_quality_status": "NORMAL", "metrics": {}}
    record = harness.storage.save_inspection(legacy)
    payload = report_payload(record, "INSUFFICIENT_DATA")
    payload["inspection_id"] = "INSP-000002"
    payload["recommended_checks"] = [{"check_code": "MODEL_SERVICE_CHECK", "evidence_refs": ["F0002"]}]
    service, generator = service_for(harness.storage, [call_response(("get_inspection_result", {"inspection_id": "INSP-000002"})),
                                                     text_response(), report_response(payload)])
    app.dependency_overrides[get_agent_service] = lambda: service
    response = harness.client.post("/analyze/INSP-000002")
    assert response.status_code == 200
    assert response.json()["inspection_result"] == "UNKNOWN"
    assert response.json()["final_result"] is None
    assert response.json()["final_reason_code"] is None


def test_sequential_requests_have_independent_ids_and_real_traces(harness):
    responses = normal_responses() + [call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}),
                                                   ("get_execution_logs", {"inspection_id": "INSP-000001"})),
                                     report_response(report_payload())]
    service, generator = service_for(harness.storage, responses)
    app.dependency_overrides[get_agent_service] = lambda: service
    first = harness.client.post("/analyze/INSP-000001").json()
    second = harness.client.post("/analyze/INSP-000001").json()
    assert first["analysis_id"] != second["analysis_id"]
    assert len(first["tool_execution_trace"]) == 1
    assert len(second["tool_execution_trace"]) == 2
    assert first["tool_execution_trace"][0]["sequence"] == second["tool_execution_trace"][0]["sequence"] == 1


def test_lazy_sdk_client_reused_and_closed_without_live_requests(harness, prohibit_real_sdk_client):
    app.dependency_overrides.pop(get_agent_service)
    harness.settings.GEMINI_API_KEY = "mock-not-real-key"
    fake_service, generator = service_for(harness.storage, normal_responses() + normal_responses())
    fake_client = fake_service.client
    fake_client.aio.aclose = AsyncMock()
    fake_client.close = Mock()
    prohibit_real_sdk_client.side_effect = None
    prohibit_real_sdk_client.return_value = fake_client
    assert harness.client.get("/health").status_code == 200
    prohibit_real_sdk_client.assert_not_called()
    first = harness.client.post("/analyze/INSP-000001")
    second = harness.client.post("/analyze/INSP-000001")
    assert first.status_code == second.status_code == 200
    prohibit_real_sdk_client.assert_called_once()
    assert first.json()["analysis_id"] != second.json()["analysis_id"]
    assert "mock-not-real-key" not in first.text
    harness.client.portal.call(app.state.agent_runtime.aclose)
    fake_client.aio.aclose.assert_awaited_once()
    fake_client.close.assert_called_once()


def test_openapi_and_docs_register_analysis_contract(harness):
    schema = harness.client.get("/openapi.json").json()
    operation = schema["paths"]["/analyze/{inspection_id}"]["post"]
    assert set(operation["responses"]) == {"200", "404", "422", "500", "502", "503", "504"}
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/AnalysisResponse")
    assert operation["responses"]["503"]["content"]["application/json"]["schema"]["$ref"].endswith("/AnalysisErrorResponse")
    parameter = operation["parameters"][0]
    assert parameter["name"] == "inspection_id" and parameter["in"] == "path"
    assert "Existing server-managed" in parameter["description"]
    assert harness.client.get("/docs").status_code == 200
    assert "/inspections" in schema["paths"] and "/health" in schema["paths"]


def test_analysis_does_not_run_vision_or_inspection_workflow(harness):
    with patch("backend.main.execute_inspection_workflow", side_effect=AssertionError("Must not inspect")) as workflow, \
         patch("backend.main.get_patchcore_inferencer", side_effect=AssertionError("Must not infer")) as inference, \
         patch("cv2.imread", side_effect=AssertionError("Must not reload image")) as loader:
        assert harness.client.post("/analyze/INSP-000001").status_code == 200
    workflow.assert_not_called()
    inference.assert_not_called()
    loader.assert_not_called()


def test_concurrent_requests_share_client_but_not_state(harness, prohibit_real_sdk_client):
    app.dependency_overrides.pop(get_agent_service)
    second_record = harness.storage.save_inspection(make_record(inspection_id="INSP-000002"))
    harness.settings.GEMINI_API_KEY = "mock-not-real-key"
    fake_service, generator = service_for(harness.storage, [])
    fake_client = fake_service.client
    fake_client.aio.aclose = AsyncMock()
    fake_client.close = Mock()

    async def generate(**kwargs):
        await asyncio.sleep(0.01)
        target = re.search(r"INSP-[0-9]{6}", kwargs["contents"][0].parts[0].text).group()
        if kwargs["config"].response_mime_type == "application/json":
            payload = report_payload(harness.record if target == "INSP-000001" else second_record)
            payload["inspection_id"] = target
            return report_response(payload)(**kwargs)
        if len(kwargs["contents"]) == 1:
            return call_response(("get_inspection_result", {"inspection_id": target}))
        return text_response()

    generator.side_effect = generate
    prohibit_real_sdk_client.side_effect = None
    prohibit_real_sdk_client.return_value = fake_client
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda target: harness.client.post(f"/analyze/{target}"), ["INSP-000001", "INSP-000002"]))
    assert all(response.status_code == 200 for response in responses)
    for response, target in zip(responses, ["INSP-000001", "INSP-000002"]):
        body = response.json()
        assert body["inspection_id"] == target
        assert len(body["tool_execution_trace"]) == 1
        assert body["tool_execution_trace"][0]["arguments"] == {"inspection_id": target}
        assert body["tool_execution_trace"][0]["sequence"] == 1
        assert body["observed_facts"][0]["evidence_id"] == "E0001"
    assert responses[0].json()["analysis_id"] != responses[1].json()["analysis_id"]
    prohibit_real_sdk_client.assert_called_once()


@pytest.mark.parametrize("exception,status,code", [(RuntimeError("Traceback /app/key"), 502, "GEMINI_REQUEST_FAILED"),
                                                  (TimeoutError(), 504, "GEMINI_TIMEOUT")])
def test_real_service_mock_sdk_errors_have_safe_http_mapping(harness, exception, status, code):
    service, generator = service_for(harness.storage, [exception])
    app.dependency_overrides[get_agent_service] = lambda: service
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == status
    assert response.json()["detail"]["error_code"] == code


def test_real_service_overall_deadline_over_http(harness):
    service, generator = service_for(harness.storage, [], AgentLimits(request_timeout_seconds=0.005))

    async def slow_generate(**kwargs):
        await asyncio.sleep(0.05)
        return text_response()

    generator.side_effect = slow_generate
    app.dependency_overrides[get_agent_service] = lambda: service
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 504
    assert response.json()["detail"]["error_code"] == "AGENT_TIMEOUT"


def test_second_request_client_error_returns_safe_502_without_retry(harness):
    failure = errors.ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                               "message": "Sensitive offline transport error"}})
    service, generator = service_for(harness.storage, [
        call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})), failure,
    ])
    app.dependency_overrides[get_agent_service] = lambda: service
    before = file_hashes(harness)
    with patch.object(harness.storage, "get_inspection", wraps=harness.storage.get_inspection) as lookup:
        response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 502
    assert response.json() == {"detail": {"analysis_status": "FAILED", "error_code": "GEMINI_REQUEST_FAILED"}}
    assert lookup.call_count == 2
    assert generator.await_count == 2
    assert generator.call_args_list[1].kwargs["contents"][-1].role == "user"
    assert len(generator.call_args_list[1].kwargs["contents"]) == 1
    assert set(generator.call_args_list[1].kwargs["contents"][0].parts[0].model_dump(exclude_none=True)) == {"text"}
    assert generator.call_args_list[1].kwargs["config"].response_schema is None
    assert generator.call_args_list[1].kwargs["config"].response_json_schema is not None
    assert "Sensitive" not in response.text
    assert file_hashes(harness) == before


def test_storage_error_during_actual_agent_tool_execution(harness):
    service, generator = service_for(harness.storage, normal_responses())
    app.dependency_overrides[get_agent_service] = lambda: service
    with patch.object(harness.storage, "get_inspection", side_effect=[harness.record, StorageError("/app/private")]):
        response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "STORAGE_ERROR"
    assert generator.call_count == 1


def test_startup_with_configured_key_keeps_patchcore_lifespan_without_gemini(monkeypatch, prohibit_real_sdk_client):
    settings = Settings(_env_file=None, ENABLE_PATCHCORE=True, GEMINI_API_KEY="mock-not-real-key")
    model_loader = Mock(return_value=None)
    monkeypatch.setattr("backend.main.get_settings", lambda: settings)
    monkeypatch.setattr("backend.main.get_patchcore_inferencer", model_loader)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert app.state.agent_runtime._client is None
        prohibit_real_sdk_client.assert_not_called()
    model_loader.assert_called_once()
