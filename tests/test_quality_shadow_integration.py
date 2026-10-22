"""Post-commit integration through the real workflow with an isolated Fake model."""

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import backend.main as main
from backend.config import Settings
from backend.quality_shadow_store import ShadowStore
from backend.quality_shadow_store import ShadowStorageError
from backend.quality_shadow_worker import QualityShadowWorker
from backend.reinspection_store import ReinspectionError
from backend.storage import StorageWriteError
from tests.test_grab_inspection import harness, inspect


@pytest.fixture
def enabled(harness, monkeypatch):
    settings = harness.client.app.state.video_runtime.settings
    monkeypatch.setattr(settings, "QUALITY_SHADOW_ENABLED", True)
    worker = QualityShadowWorker(ShadowStore(harness.directory / "quality_shadow_metrics"))
    harness.runtime.shadow_worker = worker
    yield harness, worker
    assert worker.close()


def test_default_off_preserves_existing_gemini_settings_and_pipeline(harness):
    defaults = Settings(_env_file=None)
    assert defaults.QUALITY_SHADOW_ENABLED is False
    assert Settings.model_fields["AGENT_FINAL_MODEL_TIMEOUT_SECONDS"].default == 30
    assert Settings.model_fields["VISION_REVIEW_TIMEOUT_SECONDS"].default == 30
    assert Settings.model_fields["VISION_REVIEW_MODEL"].default == "gemini-3.8-flash"
    result = inspect(harness)
    assert result.status_code == 201
    assert result.json()["final_result"] == "OK"
    assert not (harness.directory / "quality_shadow_metrics").exists()
    assert harness.runtime.shadow_worker is None
    assert "quality_observability" not in result.json()["metrics"]


@pytest.mark.parametrize("score,expected", [(20.0, "OK"), (45.0, "NG")])
def test_shadow_is_after_log_and_rig_commit_without_response_or_record_changes(enabled, monkeypatch, score, expected):
    harness, worker = enabled
    harness.fake.score = score
    original_submit = worker.submit
    observed = []
    def submit(job):
        stored = harness.storage.get_inspection(job.source.inspection_id)
        assert stored is not None
        assert any(log.event_code == "INSPECTION_COMPLETED" for log in harness.storage.get_logs(stored.inspection_id))
        state = json.loads((harness.directory / "reinspection_history/state.json").read_text(encoding="utf-8"))
        assert state["captures"][harness.metadata["capture_id"]]["status"] == "COMMITTED"
        observed.append(job.source)
        return original_submit(job)
    monkeypatch.setattr(worker, "submit", submit)
    response = inspect(harness)
    assert response.status_code == 201
    document = response.json()
    assert document["final_result"] == expected
    assert len(observed) == 1
    inspection_bytes = (harness.directory / "inspections.jsonl").read_bytes()
    logs_bytes = (harness.directory / "logs.jsonl").read_bytes()
    state_bytes = (harness.directory / "reinspection_history/state.json").read_bytes()
    assert worker.wait_idle()
    result = worker.store.read(observed[0])
    assert result.source.inspection_id == document["inspection_id"]
    assert result.source.crop_sha256 == document["metrics"]["input_provenance"]["crop_sha256"]
    assert round(result.metrics["mean_gv"].value, 2) == document["metrics"]["mean"]
    assert (harness.directory / "inspections.jsonl").read_bytes() == inspection_bytes
    assert (harness.directory / "logs.jsonl").read_bytes() == logs_bytes
    assert (harness.directory / "reinspection_history/state.json").read_bytes() == state_bytes
    assert inspect(harness).json() == document
    assert len(observed) == 1
    assert "quality_observability" not in document


def test_shadow_failures_and_broken_logging_do_not_turn_success_into_error(enabled, monkeypatch):
    harness, worker = enabled
    def broken(job):
        raise RuntimeError("PRIVATE_SHOULD_NOT_ESCAPE")
    monkeypatch.setattr(worker, "submit", broken)
    import backend.quality_shadow_worker as module
    monkeypatch.setattr(module.logger, "warning", Mock(side_effect=RuntimeError("bad handler")))
    response = inspect(harness)
    assert response.status_code == 201
    assert response.json()["final_result"] == "OK"


def test_queue_rejection_does_not_change_inspection_result(enabled, monkeypatch):
    harness, worker = enabled
    rejected = Mock(return_value=False)
    monkeypatch.setattr(worker, "submit", rejected)
    response = inspect(harness)
    assert response.status_code == 201 and response.json()["final_result"] == "OK"
    assert rejected.call_count == 1


@pytest.mark.parametrize("failure", ["compute", "publish"])
def test_background_compute_and_write_failure_preserve_committed_records(enabled, monkeypatch, failure):
    harness, worker = enabled
    if failure == "compute":
        monkeypatch.setattr(worker, "compute", Mock(side_effect=RuntimeError("SYNTHETIC_COMPUTE_FAILURE")))
    else:
        monkeypatch.setattr(worker.store, "publish", Mock(side_effect=ShadowStorageError("SHADOW_STORAGE_UNAVAILABLE")))
    response = inspect(harness)
    assert response.status_code == 201 and response.json()["final_result"] == "OK"
    record_bytes = (harness.directory / "inspections.jsonl").read_bytes()
    logs_bytes = (harness.directory / "logs.jsonl").read_bytes()
    state_bytes = (harness.directory / "reinspection_history/state.json").read_bytes()
    assert worker.wait_idle()
    assert (harness.directory / "inspections.jsonl").read_bytes() == record_bytes
    assert (harness.directory / "logs.jsonl").read_bytes() == logs_bytes
    assert (harness.directory / "reinspection_history/state.json").read_bytes() == state_bytes
    expected = "computation_failed" if failure == "compute" else "SHADOW_STORAGE_UNAVAILABLE"
    assert worker.snapshot()["counters"][expected] == 1


@pytest.mark.parametrize("fields", [["schema_version"], ["algorithm_version"], ["schema_version", "algorithm_version"]])
def test_version_validation_failure_preserves_committed_inspection(enabled, monkeypatch, fields):
    harness, worker = enabled
    original_compute = worker.compute
    def unversioned(image, source):
        document = original_compute(image, source).model_dump(mode="json")
        for field in fields:
            del document[field]
        return document
    monkeypatch.setattr(worker, "compute", unversioned)
    response = inspect(harness)
    assert response.status_code == 201
    document = response.json()
    assert document["final_result"] == "OK"
    paths = [harness.directory / name for name in ("inspections.jsonl", "logs.jsonl", "reinspection_history/state.json")]
    originals = [path.read_bytes() for path in paths]
    assert worker.wait_idle()
    assert [path.read_bytes() for path in paths] == originals
    assert worker.snapshot()["counters"]["job_failed"] == 1
    assert worker.snapshot()["counters"].get("published", 0) == 0
    assert not list(worker.store.root.rglob("*.json"))
    assert inspect(harness).json() == document


@pytest.mark.parametrize("failure", ["logs", "rig_commit", "model", "image_load"])
def test_original_failures_never_enqueue_an_uncommitted_shadow(enabled, monkeypatch, failure):
    harness, worker = enabled
    if failure == "logs":
        monkeypatch.setattr(harness.storage, "save_logs", Mock(side_effect=StorageWriteError("synthetic logs failed")))
    elif failure == "rig_commit":
        original = harness.runtime.reinspections._write
        calls = []
        def commit(state):
            calls.append(True)
            if len(calls) == 2:
                raise ReinspectionError(503, "SYNTHETIC_COMMIT_FAILED")
            return original(state)
        monkeypatch.setattr(harness.runtime.reinspections, "_write", commit)
    elif failure == "model":
        harness.fake.failure = RuntimeError("MOCK_MODEL_FAILURE")
    else:
        import backend.grab_inspection as module
        monkeypatch.setattr(module.ImageRegistry, "get_path", lambda registry, identifier: None)
    try:
        response = inspect(harness)
        if failure == "rig_commit":
            assert response.status_code == 503
    except (StorageWriteError, KeyError):
        assert failure in {"logs", "image_load"}
    assert worker.snapshot()["counters"].get("accepted", 0) == 0
    assert not list(worker.store.root.rglob("*.json"))
    if failure == "image_load":
        rows = [json.loads(line) for line in (harness.directory / "inspections.jsonl").read_text(encoding="utf-8").splitlines()]
        assert rows[-1]["final_result"] == "ERROR"


def test_original_quality_warning_priority_survives_shadow(enabled):
    from tests.test_reinspection_workflow import capture

    harness, worker = enabled
    harness.fake.score = 45
    identifier = capture(harness)
    response = inspect(harness, capture_id=identifier)
    assert response.status_code == 201
    document = response.json()
    assert document["result"] == "NG"
    assert document["final_result"] == "REINSPECT"
    assert document["final_reason_code"] == "IMAGE_QUALITY_WARNING"
    assert worker.wait_idle()
    assert worker.snapshot()["counters"]["published"] == 1


@pytest.mark.parametrize("enabled_flag", [False, True])
def test_lifespan_only_starts_worker_when_enabled_and_closes_it(tmp_path, monkeypatch, enabled_flag):
    settings = Settings(_env_file=None, OUTPUT_DIR=str(tmp_path), ENABLE_PATCHCORE=False, QUALITY_SHADOW_ENABLED=enabled_flag)
    async def no_agent_close():
        return None
    captures = SimpleNamespace(close=Mock())
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "AgentRuntime", lambda: SimpleNamespace(aclose=no_agent_close))
    monkeypatch.setattr(main, "VideoRuntime", lambda current: SimpleNamespace(captures=captures))
    application = SimpleNamespace(state=SimpleNamespace())
    async def run():
        async with main.lifespan(application):
            worker = application.state.quality_shadow_worker
            assert (worker is not None) == enabled_flag
            assert not (tmp_path / "quality_shadow_metrics").exists()
        if enabled_flag:
            assert not application.state.quality_shadow_worker.snapshot()["alive"]
    asyncio.run(run())
    captures.close.assert_called_once()


def test_fallback_settings_have_the_same_default_off(monkeypatch):
    import builtins
    original_import = builtins.__import__
    def without_settings(name, *args, **kwargs):
        if name == "pydantic_settings":
            raise ImportError("synthetic fallback")
        return original_import(name, *args, **kwargs)
    monkeypatch.delenv("QUALITY_SHADOW_ENABLED", raising=False)
    monkeypatch.setattr(builtins, "__import__", without_settings)
    specification = importlib.util.spec_from_file_location("shadow_fallback_config_test", Path(__file__).resolve().parents[1] / "backend/config.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    assert module.Settings().QUALITY_SHADOW_ENABLED is False
    monkeypatch.setenv("QUALITY_SHADOW_ENABLED", "true")
    assert module.Settings().QUALITY_SHADOW_ENABLED is True
