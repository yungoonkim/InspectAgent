"""Day 7 Step 1: Error Observability and Safe Provider Error Verification.

Verifies that:
1. Normal Mock Gemini responses produce valid AnalysisResponse (HTTP 200)
2. HTTP 400 Bad Request logs safe diagnostics and returns safe HTTP 502
3. HTTP 401/403 Auth failures log safe diagnostics and return safe HTTP 502
4. HTTP 404 Model Not Found logs safe diagnostics and returns safe HTTP 502
5. HTTP 429 Rate Limit logs safe diagnostics and returns safe HTTP 502
6. TimeoutError logs timeout warning and returns safe HTTP 504 (GEMINI_TIMEOUT)
7. Generic SDK exception logs exception class and returns safe HTTP 502
8. Sensitive tokens/keys are redacted from logs and never present in HTTP response
9. Stored report endpoints (/inspections/{id}/agent-report) retrieve cached reports without calling Gemini
10. Live Gemini API calls remain strictly ZERO throughout all tests.
"""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from google.genai import errors, types
import pytest

from backend.agent.api import get_agent_service, get_analysis_storage
from backend.agent.report_store import AgentReportStore, get_agent_report_store
from backend.agent.schemas import AnalysisResponse
from backend.agent.service import (
    _extract_provider_error_code,
    _extract_status_code,
    _sanitize_error_message,
)
from backend.config import Settings
from backend.main import app
from backend.storage import JsonlInspectionStorage
from tests.test_agent_service import normal_responses, service_for
from tests.test_agent_tools import make_log, make_record


def _synthetic_google_key():
    return "AIzaSy" + ("A" * 33)


@pytest.fixture(autouse=True)
def forbid_live_gemini():
    with patch("backend.agent.service.genai.Client", side_effect=AssertionError("Live Gemini forbidden")):
        with patch("backend.agent.api.genai.Client", side_effect=AssertionError("Live Gemini forbidden")):
            yield


@pytest.fixture
def harness(tmp_path, monkeypatch):
    inspections_path = tmp_path / "inspections.jsonl"
    logs_path = tmp_path / "logs.jsonl"
    storage = JsonlInspectionStorage(inspections_path, logs_path)
    record = storage.save_inspection(make_record())
    storage.save_log(make_log())

    settings = Settings(
        _env_file=None,
        ENABLE_PATCHCORE=False,
        GEMINI_API_KEY=None,
        GEMINI_MODEL="gemini-3.8-flash",
        INSPECTIONS_FILE=str(inspections_path),
        INSPECTION_LOGS_FILE=str(logs_path),
    )

    original_overrides = dict(app.dependency_overrides)
    report_store = AgentReportStore(tmp_path / "agent_reports")
    for identifier in ("INSP-001396", "INSP-001398"):
        report_store.save({"inspection_id": identifier, "analysis_status": "COMPLETED",
                           "provenance": "RECORDED_TEST_FIXTURE"})
    app.dependency_overrides[get_agent_report_store] = lambda: report_store
    app.dependency_overrides[get_analysis_storage] = lambda: storage
    monkeypatch.setattr("backend.main.get_settings", lambda: settings)

    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            storage=storage,
            settings=settings,
            record=record,
            tmp_path=tmp_path,
        )

    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


def test_helper_sanitization_and_status_extraction():
    # Sensitive credential redaction
    synthetic_key = _synthetic_google_key()
    raw_message = f"Error at https://api.google.com?key={synthetic_key} with Bearer secret_token_xyz"
    sanitized = _sanitize_error_message(raw_message)
    prefix_sanitized = _sanitize_error_message(f"Credential {synthetic_key}")
    assert "AIzaSy" not in sanitized
    assert "AIzaSy" not in prefix_sanitized
    assert "secret_token" not in sanitized
    assert "[REDACTED]" in sanitized

    # Status code extraction
    api_err = errors.ClientError(404, {"error": {"code": 404, "status": "NOT_FOUND"}})
    assert _extract_status_code(api_err) == 404
    assert _extract_provider_error_code(api_err) == "NOT_FOUND"

    # Generic exception without code
    generic = RuntimeError("simple failure")
    assert _extract_status_code(generic) is None
    assert _extract_provider_error_code(generic) is None


def test_normal_response_mock_flow(harness):
    service, generator = service_for(harness.storage, normal_responses())
    app.dependency_overrides[get_agent_service] = lambda: service

    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 200
    data = response.json()
    AnalysisResponse.model_validate(data)
    assert data["analysis_status"] == "COMPLETED"
    assert data["inspection_id"] == "INSP-000001"
    assert data["model_name"] == "gemini-mock"
    assert data["error_code"] is None


@pytest.mark.parametrize(
    "status_code,status_str,msg_prefix",
    [
        (400, "INVALID_ARGUMENT", "Invalid schema or function calling arguments"),
        (401, "UNAUTHENTICATED", "API key invalid or expired"),
        (403, "PERMISSION_DENIED", "Access to model gemini-3.8-flash denied"),
        (404, "NOT_FOUND", "models/gemini-3.8-flash is not found"),
        (429, "RESOURCE_EXHAUSTED", "Rate limit quota exceeded"),
    ],
)
def test_provider_http_errors_safely_logged_and_mapped_to_502(
    harness, caplog, status_code, status_str, msg_prefix
):
    fake_secret = _synthetic_google_key()
    failure = errors.ClientError(
        status_code,
        {"error": {"code": status_code, "status": status_str, "message": f"{msg_prefix}: key={fake_secret}"}},
    )
    service, generator = service_for(harness.storage, [failure])
    app.dependency_overrides[get_agent_service] = lambda: service

    with caplog.at_level(logging.ERROR, logger="backend.agent.service"):
        response = harness.client.post("/analyze/INSP-000001")

    # Safe HTTP contract: 502 with GEMINI_REQUEST_FAILED
    assert response.status_code == 502
    assert response.json() == {
        "detail": {"analysis_status": "FAILED", "error_code": "GEMINI_REQUEST_FAILED"}
    }
    # Secret must never appear in response
    assert fake_secret not in response.text

    # Log record verification: must capture all 6 required items safely
    assert any(
        "Gemini generate_content failed" in record.message
        and f"http_status={status_code}" in record.message
        and f"provider_code={status_str}" in record.message
        and "correlation_id=INSP-000001" in record.message
        and "model=gemini-mock" in record.message
        and "stage=TOOL_ROUND_1" in record.message
        and fake_secret not in record.message
        for record in caplog.records
    )


def test_timeout_error_safely_logged_and_mapped_to_504(harness, caplog):
    service, generator = service_for(harness.storage, [TimeoutError()])
    app.dependency_overrides[get_agent_service] = lambda: service

    with caplog.at_level(logging.WARNING, logger="backend.agent.service"):
        response = harness.client.post("/analyze/INSP-000001")

    assert response.status_code == 504
    assert response.json() == {
        "detail": {"analysis_status": "FAILED", "error_code": "GEMINI_TIMEOUT"}
    }
    assert any(
        "Gemini generate_content timeout" in record.message
        and "correlation_id=INSP-000001" in record.message
        for record in caplog.records
    )


def test_generic_sdk_exception_safely_logged(harness, caplog):
    sensitive_token = "Bearer confidential_bearer_token_xyz"
    service, generator = service_for(
        harness.storage, [RuntimeError(f"Connection reset: {sensitive_token}")]
    )
    app.dependency_overrides[get_agent_service] = lambda: service

    with caplog.at_level(logging.ERROR, logger="backend.agent.service"):
        response = harness.client.post("/analyze/INSP-000001")

    assert response.status_code == 502
    assert response.json() == {
        "detail": {"analysis_status": "FAILED", "error_code": "GEMINI_REQUEST_FAILED"}
    }
    assert sensitive_token not in response.text
    assert any(
        "exception_class=RuntimeError" in record.message
        and "confidential_bearer" not in record.message
        for record in caplog.records
    )


def test_stored_reports_retrieved_without_calling_gemini(harness):
    """GET /inspections/{id}/agent-report reads static cached reports with 0 Gemini calls."""
    # INSP-001396: existing stored report
    resp_1396 = harness.client.get("/inspections/INSP-001396/agent-report")
    assert resp_1396.status_code == 200
    report_1396 = resp_1396.json()
    assert report_1396["inspection_id"] == "INSP-001396"
    assert report_1396["analysis_status"] == "COMPLETED"

    # INSP-001398: existing stored report
    resp_1398 = harness.client.get("/inspections/INSP-001398/agent-report")
    assert resp_1398.status_code == 200
    report_1398 = resp_1398.json()
    assert report_1398["inspection_id"] == "INSP-001398"
    assert report_1398["analysis_status"] == "COMPLETED"

    # INSP-001442: newly created inspection (no pre-cached report)
    resp_1442 = harness.client.get("/inspections/INSP-001442/agent-report")
    assert resp_1442.status_code == 404
    assert resp_1442.json()["detail"]["error_code"] == "NO_STORED_REPORT"
