"""New synthetic Grab -> stored map -> new Fake Agent report -> Fake Vision."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

import backend.main as main
from backend.agent.api import get_agent_service, get_analysis_storage
from backend.agent.report_store import AgentReportStore, ReportStoreError, get_agent_report_store
from backend.agent.service import AgentService, PRODUCT_ALIAS
from backend.agent.tools import InspectionTools
from backend.config import Settings, get_settings
from backend.vision_review import VisionReviewService
from tests.test_grab_inspection import harness
from tests.test_reinspection_workflow import first_warning
from tests.test_day7_step5_agent_e2e import FakeGemini, final_response
from tests.test_agent_service import call_response, text_response
from tests.test_vision_review import FakeVisionClient


@pytest.fixture(autouse=True)
def no_live_client(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("LIVE SDK forbidden"))
    monkeypatch.setattr("backend.agent.api.genai.Client", forbidden)
    yield
    forbidden.assert_not_called()


@pytest.fixture
def connection(harness, monkeypatch):
    harness.fake.score = 40.1631
    record = first_warning(harness)
    identifier = record["inspection_id"]
    fake = FakeGemini([
        call_response(("get_inspection_result", {"inspection_id": identifier})),
        call_response(("analyze_image_quality", {"inspection_id": identifier})),
        call_response(("get_execution_logs", {"inspection_id": identifier})),
        call_response(("get_inspection_history", {"product_id": PRODUCT_ALIAS, "limit": 5})),
        text_response(),
        final_response,
    ])
    settings = Settings(_env_file=None, ENABLE_PATCHCORE=False, GEMINI_API_KEY=None,
                        GEMINI_MODEL="gemini-mock", OUTPUT_DIR=str(harness.directory))
    service = AgentService(InspectionTools(harness.storage), settings=settings, client=fake)
    store = AgentReportStore(harness.directory / "agent_reports")
    previous = dict(main.app.dependency_overrides)
    main.app.dependency_overrides[get_analysis_storage] = lambda: harness.storage
    main.app.dependency_overrides[get_agent_service] = lambda: service
    main.app.dependency_overrides[get_settings] = lambda: settings
    main.app.dependency_overrides[get_agent_report_store] = lambda: store
    vision = FakeVisionClient()
    monkeypatch.setattr(main.app.state, "vision_review_service",
        VisionReviewService(harness.directory / "vision", fake_client=vision, allow_fake=True), raising=False)
    yield SimpleNamespace(h=harness, identifier=identifier, record=record, fake=fake, store=store, vision=vision)
    main.app.dependency_overrides.clear()
    main.app.dependency_overrides.update(previous)


def test_new_crop_map_logs_new_agent_report_and_vision_share_inspection(connection):
    runtime = connection
    identifier = runtime.identifier
    immutable = {str(path): path.read_bytes() for folder in (runtime.h.directory / "inputs", runtime.h.directory / "maps")
                 for path in folder.iterdir() if path.is_file()}
    immutable.update({str(path): path.read_bytes() for path in runtime.h.directory.glob("*.jsonl")})
    group = runtime.h.runtime.reinspections.root / "state.json"
    immutable[str(group)] = group.read_bytes()
    client = runtime.h.client
    assert client.get(f"/inspections/{identifier}/agent-report").status_code == 404
    assert not runtime.fake.requests
    result = client.post(f"/analyze/{identifier}")
    assert result.status_code == 200, result.text
    report = result.json()
    assert report["final_result"] == "REINSPECT" and report["inspection_result"] == "NG"
    assert report["provenance"] == "FAKE_TEST"
    assert report["analysis_status"] == "COMPLETED" and report["analysis_id"].startswith("ANALYSIS-")
    assert report["observed_facts"] and all(entry["executed"] for entry in report["tool_execution_trace"])
    saved = client.get(f"/inspections/{identifier}/agent-report")
    assert saved.status_code == 200 and saved.json() == report
    count = len(runtime.fake.requests)
    assert count >= 2
    assert client.post(f"/analyze/{identifier}").status_code == 409
    assert len(runtime.fake.requests) == count
    reviewed = client.post(f"/inspections/{identifier}/vision-review", json={"request_id": uuid4().hex,"confirm_external_transmission":True})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["review"]["inspection_id"] == identifier
    assert reviewed.json()["review"]["image_sha256"] == runtime.record["metrics"]["input_provenance"]["crop_sha256"]
    assert len(runtime.vision.calls) == 1 and len(runtime.h.fake.images) == 1
    assert all(Path(path).read_bytes() == value for path, value in immutable.items())


def test_report_save_failure_is_not_http_success(connection, monkeypatch):
    def fail(report):
        raise ReportStoreError("AGENT_REPORT_STORAGE_FAILED")
    monkeypatch.setattr(connection.store, "save", fail)
    result = connection.h.client.post(f"/analyze/{connection.identifier}")
    assert result.status_code == 503, result.text
    assert result.json()["detail"]["error_code"] == "AGENT_REPORT_STORAGE_FAILED"
    assert not connection.store.path(connection.identifier).exists()
    assert connection.h.storage.get_inspection(connection.identifier).final_result == "REINSPECT"


def test_atomic_report_publication_never_overwrites_existing(tmp_path, monkeypatch):
    store = AgentReportStore(tmp_path / "reports")
    report = {"inspection_id": "INSP-900001", "analysis_id": "new"}
    store.save(report)
    before = store.path(report["inspection_id"]).read_bytes()
    with pytest.raises(ReportStoreError, match="AGENT_REPORT_EXISTS"):
        store.save({**report, "analysis_id": "replacement"})
    assert store.path(report["inspection_id"]).read_bytes() == before
    def fail_link(*arguments):
        raise OSError("PRIVATE_PATH_NOT_EXPOSED")
    monkeypatch.setattr("backend.agent.report_store.os.link", fail_link)
    with pytest.raises(ReportStoreError, match="AGENT_REPORT_STORAGE_FAILED"):
        store.save({"inspection_id": "INSP-900002"})
    assert not store.path("INSP-900002").exists()
    assert not list(store.root.glob("*.tmp"))


@pytest.mark.parametrize("kind", ["malformed", "identity"])
def test_invalid_saved_report_is_safe_error(connection, kind):
    connection.store.root.mkdir()
    path = connection.store.path(connection.identifier)
    path.write_text("invalid" if kind == "malformed" else json.dumps({"inspection_id": "INSP-999999"}), encoding="utf-8")
    response = connection.h.client.get(f"/inspections/{connection.identifier}/agent-report")
    assert response.status_code == 503
    assert not connection.fake.requests
    assert str(path) not in response.text
