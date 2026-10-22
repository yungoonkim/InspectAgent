"""Isolated three-stage policy tests using synthetic Captures and Fake providers."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import threading
from uuid import uuid4

import pytest

import backend.main as main
from backend.config import Settings
from backend.grab_inspection import GrabInspectionRuntime
from backend.quality_shadow_store import ShadowStore
from backend.quality_shadow_worker import QualityShadowWorker
from backend.reinspection_store import JUDGE_ASSISTED_POLICY
from backend.storage import StorageWriteError
from backend.vision_review import VisionReviewService
from tests.test_grab_inspection import harness, inspect
from tests.test_reinspection_workflow import capture, first_warning, group_for, retry_payload, review
from tests.test_vision_review import FakeVisionClient


@pytest.fixture
def assisted(harness, monkeypatch):
    monkeypatch.setattr(harness.client.app.state.video_runtime.settings, "JUDGE_ASSISTED_WORKFLOW_ENABLED", True)
    return harness


def input_snapshot(harness):
    paths = [harness.directory / name for name in ("inspections.jsonl", "logs.jsonl")]
    paths.extend((harness.directory / "inputs").glob("*"))
    paths.extend((harness.directory / "maps").glob("*"))
    return {str(path): path.read_bytes() for path in paths if path.is_file()}


def fake_judge(harness, record, monkeypatch, verdict="REINSPECT", error=None):
    client = FakeVisionClient()
    draft = json.loads(client.text)
    draft["judge_verdict"] = verdict
    draft["defect_locations"] = ["MOCK TEST: upper edge"] if verdict == "NG" else []
    client.text = json.dumps(draft)
    client.error = error
    service = VisionReviewService(harness.directory / "vision", fake_client=client, allow_fake=True)
    monkeypatch.setattr(main.app.state, "vision_review_service", service, raising=False)
    endpoint = f'/inspections/{record["inspection_id"]}/vision-review'
    return SimpleNamespace(client=client, service=service, endpoint=endpoint)


def test_default_off_and_client_cannot_select_policy(harness):
    assert Settings.model_fields["JUDGE_ASSISTED_WORKFLOW_ENABLED"].default is False
    assert harness.client.app.state.video_runtime.settings.JUDGE_ASSISTED_WORKFLOW_ENABLED is False
    response = inspect(harness, {**harness.payload, "workflow_policy": JUDGE_ASSISTED_POLICY})
    assert response.status_code == 422
    assert not harness.fake.images
    record = first_warning(harness)
    group = group_for(harness, record)
    assert "workflow_policy" not in group
    assert (group["status"], group["attempt_count"], group["remaining_attempts"]) == ("RETRY_ALLOWED", 1, 2)
    assert review(harness, group).status_code == 409


@pytest.mark.parametrize("value,expected", [("false", False), ("true", True)])
def test_setting_can_be_loaded_without_changing_environment_files(monkeypatch, value, expected):
    monkeypatch.setenv("JUDGE_ASSISTED_WORKFLOW_ENABLED", value)
    assert Settings(_env_file=None).JUDGE_ASSISTED_WORKFLOW_ENABLED is expected


def test_fallback_setting_is_off_and_explicitly_opt_in(monkeypatch):
    import builtins
    original_import = builtins.__import__
    def without_settings(name, *args, **kwargs):
        if name == "pydantic_settings":
            raise ImportError("Synthetic fallback")
        return original_import(name, *args, **kwargs)
    monkeypatch.delenv("JUDGE_ASSISTED_WORKFLOW_ENABLED", raising=False)
    monkeypatch.setattr(builtins, "__import__", without_settings)
    specification = importlib.util.spec_from_file_location("assisted_fallback_config_test",
        Path(__file__).resolve().parents[1] / "backend/config.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    assert module.Settings().JUDGE_ASSISTED_WORKFLOW_ENABLED is False
    monkeypatch.setenv("JUDGE_ASSISTED_WORKFLOW_ENABLED", "true")
    assert module.Settings().JUDGE_ASSISTED_WORKFLOW_ENABLED is True


@pytest.mark.parametrize("score,expected", [(20.0, "OK"), (45.0, "NG")])
def test_normal_result_completes_without_judge_or_required_manual_review(assisted, monkeypatch, score, expected):
    assisted.fake.score = score
    record = inspect(assisted).json()
    group = group_for(assisted, record)
    provider = fake_judge(assisted, record, monkeypatch)
    assert record["final_result"] == expected
    assert group["workflow_policy"] == JUDGE_ASSISTED_POLICY
    assert group["status"] == "COMPLETED"
    assert group["attempt_count"] == 1
    assert group["max_attempts"] is None and group["remaining_attempts"] is None
    assert review(assisted, group, "MANUAL_OK").status_code == 409
    assert not provider.client.calls
    assert inspect(assisted, retry_payload(assisted, group), capture(assisted)).status_code == 409
    assert len(assisted.fake.images) == 1


@pytest.mark.parametrize("verdict,manual", [("OK", "MANUAL_OK"), ("OK", "MANUAL_NG"),
    ("NG", "MANUAL_OK"), ("NG", "MANUAL_NG"), ("REINSPECT", "HOLD"), ("REINSPECT", "MANUAL_NG")])
def test_judge_opinion_and_manual_decision_are_separate_from_primary_record(assisted, monkeypatch, verdict, manual):
    record = first_warning(assisted)
    group = group_for(assisted, record)
    assert group["status"] == "MANUAL_REVIEW_REQUIRED" and group["attempt_count"] == 1
    assert not group["manual_reviews"]
    before = input_snapshot(assisted)
    group_before = (assisted.runtime.reinspections.root / "state.json").read_bytes()
    provider = fake_judge(assisted, record, monkeypatch, verdict)
    consent = {"request_id": uuid4().hex, "confirm_external_transmission": True}
    response = assisted.client.post(provider.endpoint, json=consent)
    assert response.status_code == 200, response.text
    judge = response.json()["review"]
    assert judge["judge_verdict"] == verdict and judge["analysis_status"] == "COMPLETED"
    assert judge["inspection_id"] == record["inspection_id"]
    assert (assisted.runtime.reinspections.root / "state.json").read_bytes() == group_before
    vision_before = (assisted.directory / "vision/state.json").read_bytes()
    response = review(assisted, group, manual)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["status"] == ("MANUAL_REVIEW_REQUIRED" if manual == "HOLD" else "MANUAL_REVIEWED")
    decision = saved["manual_reviews"][-1]
    assert decision["result"] == manual
    assert decision["inspection_ids"] == [record["inspection_id"]]
    assert decision["inspection_id"] == record["inspection_id"]
    assert decision["image_id"] == record["image_id"]
    assert decision["crop_sha256"] == record["metrics"]["input_provenance"]["crop_sha256"]
    assert decision["server_final_result"] == "REINSPECT"
    assert input_snapshot(assisted) == before
    assert (assisted.directory / "vision/state.json").read_bytes() == vision_before
    assert assisted.client.get(provider.endpoint).json()["review"] == judge
    assert len(provider.client.calls) == 1 and len(assisted.fake.images) == 1


@pytest.mark.parametrize("manual", ["HOLD", "MANUAL_OK", "MANUAL_NG"])
def test_failed_judge_has_null_verdict_and_does_not_prevent_explicit_manual_review(assisted, monkeypatch, manual):
    record = first_warning(assisted)
    group = group_for(assisted, record)
    provider = fake_judge(assisted, record, monkeypatch, error=TimeoutError("MOCK TIMEOUT"))
    response = assisted.client.post(provider.endpoint, json={"request_id": uuid4().hex, "confirm_external_transmission": True})
    assert response.status_code == 200
    judge = response.json()["review"]
    assert judge["analysis_status"] == "ANALYSIS_FAILED" and judge["judge_verdict"] is None
    assert not group_for(assisted, record)["manual_reviews"]
    assert review(assisted, group, manual).status_code == 200
    assert assisted.client.get(provider.endpoint).json()["review"] == judge
    assert assisted.storage.get_inspection(record["inspection_id"]).final_result == "REINSPECT"
    assert len(provider.client.calls) == 1


@pytest.mark.parametrize("declined", [False, True])
@pytest.mark.parametrize("manual", ["HOLD", "MANUAL_OK", "MANUAL_NG"])
def test_no_judge_or_declined_consent_allows_explicit_review_without_transmission(assisted, monkeypatch, declined, manual):
    record = first_warning(assisted)
    group = group_for(assisted, record)
    provider = fake_judge(assisted, record, monkeypatch)
    if declined:
        response = assisted.client.post(provider.endpoint,
            json={"request_id": uuid4().hex, "confirm_external_transmission": False})
        assert response.status_code == 403
    assert review(assisted, group, manual).status_code == 200
    assert not provider.client.calls
    assert not (assisted.directory / "vision/state.json").exists()


def test_hold_then_decision_and_duplicate_request_are_audited_once(assisted):
    record = first_warning(assisted)
    group = group_for(assisted, record)
    request_id = uuid4().hex
    held = review(assisted, group, "HOLD", request_id=request_id).json()
    assert review(assisted, group, "HOLD", request_id=request_id).json() == held
    assert review(assisted, group, "MANUAL_OK", request_id=request_id).status_code == 409
    assert review(assisted, group, "MANUAL_OK").status_code == 409
    decided = review(assisted, held, "MANUAL_NG").json()
    assert [entry["result"] for entry in decided["manual_reviews"]] == ["HOLD", "MANUAL_NG"]
    assert decided["status"] == "MANUAL_REVIEWED"
    assert review(assisted, decided, "MANUAL_OK").status_code == 409
    assert assisted.storage.get_inspection(record["inspection_id"]).final_result == "REINSPECT"


@pytest.mark.parametrize("field", ["result", "operator_id", "reason", "request_id", "expected_version"])
def test_manual_review_still_requires_explicit_valid_audit_fields(assisted, field):
    group = group_for(assisted, first_warning(assisted))
    payload = {"expected_version": group["version"], "request_id": uuid4().hex,
        "result": "HOLD", "operator_id": "SYNTHETIC_OPERATOR", "reason": "MOCK TEST"}
    del payload[field]
    assert assisted.client.post(f'/reinspection-groups/{group["group_id"]}/manual-reviews', json=payload).status_code == 422
    assert not assisted.client.get(f'/reinspection-groups/{group["group_id"]}').json()["manual_reviews"]


@pytest.mark.parametrize("kind", ["csrf", "origin", "owner"])
def test_manual_review_preserves_session_and_csrf_guards(assisted, kind):
    group = group_for(assisted, first_warning(assisted))
    if kind == "csrf":
        assisted.client.headers.pop("X-Capture-CSRF")
    elif kind == "origin":
        assisted.client.headers["Origin"] = "http://invalid.example"
    else:
        token, csrf = assisted.captures.bootstrap()
        assisted.client.cookies.set(assisted.captures.cookie_name, token)
        assisted.client.headers["X-Capture-CSRF"] = csrf
    assert review(assisted, group).status_code in {403, 404}


@pytest.mark.parametrize("kind", ["final_result", "group_id", "current_id", "claim", "crop", "source_revision"])
def test_manual_review_verifies_committed_record_source_and_png(assisted, monkeypatch, kind):
    record = first_warning(assisted)
    group = group_for(assisted, record)
    state_path = assisted.runtime.reinspections.root / "state.json"
    if kind in {"final_result", "group_id"}:
        saved = assisted.storage.get_inspection(record["inspection_id"]).model_copy(deep=True)
        if kind == "final_result":
            saved.final_result = "OK"
        else:
            saved.metrics["reinspection"]["group_id"] = f"RIG-{uuid4().hex}"
        monkeypatch.setattr(assisted.storage, "get_inspection", lambda identifier: saved)
    elif kind in {"current_id", "claim", "source_revision"}:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if kind == "current_id":
            state["groups"][group["group_id"]]["current_inspection_id"] = "INSP-999999999"
        elif kind == "source_revision":
            state["groups"][group["group_id"]]["source_revision"] = "b" * 64
        else:
            capture_id = record["metrics"]["input_provenance"]["capture_id"]
            state["captures"][capture_id]["status"] = "RESERVED"
        state_path.write_text(json.dumps(state), encoding="utf-8")
    else:
        (assisted.directory / "inputs" / f'{record["image_id"]}.png').write_bytes(b"SYNTHETIC TAMPER")
    before = state_path.read_bytes()
    assert review(assisted, group).status_code == 409
    assert state_path.read_bytes() == before


def test_duplicate_capture_survives_runtime_recreation_and_settings_toggle(assisted, monkeypatch):
    record = first_warning(assisted)
    before = input_snapshot(assisted)
    capture_id = record["metrics"]["input_provenance"]["capture_id"]
    recreated = GrabInspectionRuntime(assisted.directory / "inputs")
    monkeypatch.setattr(main.app.state, "grab_inspection_runtime", recreated)
    monkeypatch.setattr(assisted.client.app.state.video_runtime.settings, "JUDGE_ASSISTED_WORKFLOW_ENABLED", False)
    assert inspect(assisted, capture_id=capture_id).json() == record
    assert len(assisted.fake.images) == 1 and input_snapshot(assisted) == before
    assert review(assisted, group_for(assisted, record), "HOLD").status_code == 200
    legacy = group_for(assisted, first_warning(assisted))
    assert "workflow_policy" not in legacy


def test_legacy_incomplete_group_is_not_migrated_and_manual_scope_is_preserved(harness, monkeypatch):
    first = first_warning(harness)
    legacy = group_for(harness, first)
    monkeypatch.setattr(harness.client.app.state.video_runtime.settings, "JUDGE_ASSISTED_WORKFLOW_ENABLED", True)
    assert review(harness, legacy, "HOLD").status_code == 409
    for unused in range(2):
        record = inspect(harness, retry_payload(harness, legacy), capture(harness)).json()
        legacy = group_for(harness, record)
    legacy = review(harness, legacy, "HOLD").json()
    assert "workflow_policy" not in legacy and legacy["attempt_count"] == 3
    assert len(legacy["manual_reviews"][0]["inspection_ids"]) == 3
    new_record = first_warning(harness)
    new_group = group_for(harness, new_record)
    assert new_group["workflow_policy"] == JUDGE_ASSISTED_POLICY
    assert review(harness, new_group, "MANUAL_OK").status_code == 200
    assert harness.client.get(f'/reinspection-groups/{legacy["group_id"]}').json() == legacy


def test_model_error_is_not_reviewable_and_failed_capture_never_reexecutes(assisted):
    assisted.fake.failure = RuntimeError("SYNTHETIC MODEL ERROR")
    capture_id = capture(assisted)
    failed = inspect(assisted, capture_id=capture_id).json()
    group = group_for(assisted, failed)
    assert failed["final_result"] == "REINSPECT"
    assert failed["result"] == "UNKNOWN" and failed["anomaly_score"] is None
    assert failed["defect_detection_status"] != "COMPLETED"
    assert group["status"] == "INSPECTION_FAILED" and group["attempt_count"] == 0
    assert review(assisted, group, "MANUAL_OK").status_code == 409
    assert inspect(assisted, capture_id=capture_id).json() == failed
    assert len(assisted.fake.images) == 1
    assisted.fake.failure = None
    payload = retry_payload(assisted, group)
    payload["same_product_confirmed"] = False
    restored = inspect(assisted, payload, capture(assisted, frame_index=failed["metrics"]["input_provenance"]["frame_index"])).json()
    restored_group = group_for(assisted, restored)
    assert restored_group["attempt_count"] == 1 and restored_group["status"] == "MANUAL_REVIEW_REQUIRED"
    assert len(restored_group["failed_attempts"]) == 1


def test_pipeline_error_keeps_recovery_required_without_manual_approval(assisted, monkeypatch):
    import backend.grab_inspection as module
    monkeypatch.setattr(module.ImageRegistry, "get_path", lambda registry, identifier: None)
    capture_id = capture(assisted)
    assert inspect(assisted, capture_id=capture_id).status_code == 503
    state = json.loads((assisted.runtime.reinspections.root / "state.json").read_text(encoding="utf-8"))
    group = next(iter(state["groups"].values()))
    records = [json.loads(line) for line in (assisted.directory / "inspections.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records[-1]["final_result"] == "ERROR"
    assert group["status"] == "RECOVERY_REQUIRED" and not group["attempts"]
    assert review(assisted, group, "MANUAL_OK").status_code == 422
    assert review(assisted, group, "MANUAL_OK", expected_version=1).status_code == 409
    assert inspect(assisted, capture_id=capture_id).status_code == 409
    assert not assisted.fake.images


def test_failure_before_inference_rolls_back_only_its_new_reservation(assisted):
    assisted.factory.return_value = None
    capture_id = capture(assisted)
    assert inspect(assisted, capture_id=capture_id).status_code == 503
    state = json.loads((assisted.runtime.reinspections.root / "state.json").read_text(encoding="utf-8"))
    assert not state["groups"] and not state["captures"] and not state["requests"]
    assisted.factory.return_value = assisted.fake
    assert inspect(assisted, capture_id=capture_id).status_code == 201
    assert len(assisted.fake.images) == 1


def test_manual_review_storage_read_failure_is_explicit_and_does_not_write(assisted, monkeypatch):
    group = group_for(assisted, first_warning(assisted))
    path = assisted.runtime.reinspections.root / "state.json"
    before = path.read_bytes()
    def unavailable(identifier):
        raise OSError("SYNTHETIC READ ERROR")
    monkeypatch.setattr(assisted.storage, "get_inspection", unavailable)
    response = review(assisted, group)
    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "MANUAL_REVIEW_RECORD_UNAVAILABLE"
    assert path.read_bytes() == before


@pytest.mark.parametrize("failure", ["inspection", "logs", "group_commit"])
def test_storage_failure_reservation_stays_fail_closed_without_duplicate_prediction(assisted, monkeypatch, failure):
    store = assisted.runtime.reinspections
    if failure == "group_commit":
        original = store._write
        calls = []
        def fail_commit(state):
            calls.append(True)
            if len(calls) == 2:
                raise OSError("SYNTHETIC COMMIT ERROR")
            return original(state)
        monkeypatch.setattr(store, "_write", fail_commit)
    else:
        def fail_write(*arguments):
            raise StorageWriteError("SYNTHETIC STORAGE ERROR")
        monkeypatch.setattr(assisted.storage, "save_inspection" if failure == "inspection" else "save_logs", fail_write)
    capture_id = capture(assisted)
    assert inspect(assisted, capture_id=capture_id).status_code == 503
    assert inspect(assisted, capture_id=capture_id).status_code == 409
    state = json.loads((store.root / "state.json").read_text(encoding="utf-8"))
    assert state["captures"][capture_id]["status"] == "RESERVED"
    assert next(iter(state["groups"].values()))["status"] == "RECOVERY_REQUIRED"
    assert len(assisted.fake.images) <= 1


def test_concurrent_duplicate_only_enters_fake_model_once(assisted):
    entered = threading.Event()
    release = threading.Event()
    original = assisted.fake.predict
    def waiting(image):
        entered.set()
        assert release.wait(5)
        return original(image)
    assisted.fake.predict = waiting
    capture_id = capture(assisted)
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(inspect, assisted, None, capture_id)
        try:
            assert entered.wait(5)
            assert inspect(assisted, capture_id=capture_id).status_code == 409
        finally:
            release.set()
        first = future.result(timeout=5)
    assert first.status_code == 201
    assert inspect(assisted, capture_id=capture_id).json() == first.json()
    assert len(assisted.fake.images) == 1


def test_concurrent_manual_reviews_cannot_both_commit_the_same_version(assisted):
    group = group_for(assisted, first_warning(assisted))
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(review, assisted, group, outcome) for outcome in ("MANUAL_OK", "MANUAL_NG")]
        responses = [future.result(timeout=5) for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 409]
    stored = assisted.client.get(f'/reinspection-groups/{group["group_id"]}').json()
    assert stored["version"] == group["version"] + 1 and len(stored["manual_reviews"]) == 1


def test_failed_model_requests_do_not_become_a_three_attempt_product_policy(assisted):
    assisted.fake.failure = RuntimeError("SYNTHETIC MODEL FAILURE")
    failed = inspect(assisted).json()
    group = group_for(assisted, failed)
    for unused in range(3):
        payload = retry_payload(assisted, group)
        payload["same_product_confirmed"] = False
        response = inspect(assisted, payload, capture(assisted, frame_index=120))
        assert response.status_code == 201
        group = group_for(assisted, response.json())
    assert len(group["failed_attempts"]) == 4 and group["attempt_count"] == 0
    assert group["max_attempts"] is None and group["remaining_attempts"] is None
    assert group["status"] == "INSPECTION_FAILED" and not group["manual_reviews"]


def test_static_registered_image_does_not_create_or_use_a_rig(assisted, monkeypatch):
    from backend.inspection import ImageRegistry
    path = assisted.directory / "static.png"
    token = assisted.client.cookies.get(assisted.captures.cookie_name)
    path.write_bytes(assisted.captures.image(token, assisted.metadata["capture_id"]))
    registry = ImageRegistry()
    registry.register_image("IMG-BOTTLE-0001", path)
    monkeypatch.setattr(main, "get_image_registry", lambda settings: registry)
    settings = assisted.client.app.state.video_runtime.settings
    monkeypatch.setitem(main.app.dependency_overrides, main.get_settings, lambda: settings)
    response = assisted.client.post('/inspections', json={"product_id": "SYNTHETIC_STATIC", "image_id": "IMG-BOTTLE-0001"})
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["final_result"] == "OK" and "reinspection" not in record["metrics"]
    assert record["metrics"].get("input_source") != "LIVEVIEW_GRAB"
    assert not (assisted.runtime.reinspections.root / "state.json").exists()


@pytest.mark.parametrize("policy", [None, "", "unknown-policy"])
def test_unknown_persisted_policy_never_falls_back_to_legacy(assisted, policy):
    record = first_warning(assisted)
    group = group_for(assisted, record)
    path = assisted.runtime.reinspections.root / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["groups"][group["group_id"]]["workflow_policy"] = policy
    path.write_text(json.dumps(state), encoding="utf-8")
    before = path.read_bytes()
    assert assisted.client.get(f'/reinspection-groups/{group["group_id"]}').status_code == 503
    assert review(assisted, group).status_code == 503
    assert path.read_bytes() == before


def test_shadow_runs_once_only_after_new_policy_commit(assisted, monkeypatch):
    monkeypatch.setattr(assisted.client.app.state.video_runtime.settings, "QUALITY_SHADOW_ENABLED", True)
    worker = QualityShadowWorker(ShadowStore(assisted.directory / "shadow"))
    assisted.runtime.shadow_worker = worker
    observed = []
    original_submit = worker.submit
    def submit(job):
        state = json.loads((assisted.runtime.reinspections.root / "state.json").read_text(encoding="utf-8"))
        claim = state["captures"][assisted.metadata["capture_id"]]
        assert claim["status"] == "COMMITTED"
        group = state["groups"][claim["group_id"]]
        assert group["workflow_policy"] == JUDGE_ASSISTED_POLICY
        assert group["current_inspection_id"] == job.source.inspection_id
        assert any(log.event_code == "INSPECTION_COMPLETED" for log in assisted.storage.get_logs(job.source.inspection_id))
        observed.append(job.source)
        return original_submit(job)
    monkeypatch.setattr(worker, "submit", submit)
    try:
        response = inspect(assisted)
        assert response.status_code == 201
        record = response.json()
        before = input_snapshot(assisted)
        assert worker.wait_idle()
        shadow = worker.store.read(observed[0])
        raw = (assisted.directory / "inputs" / f'{record["image_id"]}.png').read_bytes()
        assert shadow.source.crop_sha256 == hashlib.sha256(raw).hexdigest()
        assert inspect(assisted).json() == record
        assert len(observed) == 1 and input_snapshot(assisted) == before
    finally:
        assert worker.close()
