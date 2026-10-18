"""MOCK TEST only: durable manual workflow, no checkpoint, API provider, or real DB."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
import threading
from uuid import uuid4

import numpy as np
import pytest

from backend.grab_inspection import GrabInspectionRuntime
from backend.reinspection_store import ReinspectionError, ReinspectionStore
from tests.test_grab_inspection import harness, inspect


def capture(harness, brightness=60, frame_index=None):
    if frame_index is None:
        frame_index = getattr(harness, "last_frame", 120) + 1
    harness.last_frame = max(frame_index, getattr(harness, "last_frame", 120))
    frame = np.full((240, 320, 3), brightness, dtype=np.uint8)
    frame[0, 0, 0] = frame_index % 256
    return harness.captures.save(harness.client.cookies.get(harness.captures.cookie_name),
        harness.client.headers["X-Capture-CSRF"], frame,
        {"video_id": "VID-000001", "source_revision": "a" * 64, "fps": 30, "width": 320, "height": 240},
        frame_index)["capture_id"]


def group_for(harness, result):
    response = harness.client.get('/reinspection-groups/' + result["metrics"]["reinspection"]["group_id"])
    assert response.status_code == 200, response.text
    return response.json()


def retry_payload(harness, group):
    return {**harness.payload, "group_id": group["group_id"], "expected_version": group["version"],
        "parent_inspection_id": group["current_inspection_id"], "same_product_confirmed": True,
        "request_id": uuid4().hex}


def first_warning(harness):
    response = inspect(harness, capture_id=capture(harness))
    assert response.status_code == 201, response.text
    return response.json()


def three_warnings(harness):
    first = first_warning(harness)
    group = group_for(harness, first)
    for attempt in range(2):
        response = inspect(harness, retry_payload(harness, group), capture(harness))
        assert response.status_code == 201, response.text
        group = group_for(harness, response.json())
    return group


def review(harness, group, result="HOLD", **changes):
    body = {"expected_version": group["version"], "request_id": uuid4().hex,
        "result": result, "operator_id": "DEVELOPMENT_OPERATOR", "reason": "MOCK TEST ONLY: visual review pending"}
    body.update(changes)
    return harness.client.post(f'/reinspection-groups/{group["group_id"]}/manual-reviews', json=body)


def test_three_attempts_and_fourth_rejection_preserve_raw_ng(harness):
    harness.fake.score = 40.1631
    group = three_warnings(harness)
    assert (group["attempt_count"], group["remaining_attempts"], group["status"]) == (3, 0, "MANUAL_REVIEW_REQUIRED")
    assert [entry["attempt_number"] for entry in group["attempts"]] == [1, 2, 3]
    identifiers = [entry["inspection_id"] for entry in group["attempts"]]
    assert len(set(identifiers)) == 3
    assert group["first_inspection_id"] == identifiers[0]
    assert group["attempts"][1]["parent_inspection_id"] == identifiers[0]
    assert all(entry["result"] == "NG" and entry["final_result"] == "REINSPECT" for entry in group["attempts"])
    before = (harness.directory / "inspections.jsonl").read_bytes()
    assert inspect(harness, retry_payload(harness, group), capture(harness)).status_code == 409
    assert len(harness.fake.images) == 3
    assert (harness.directory / "inspections.jsonl").read_bytes() == before


@pytest.mark.parametrize("score,expected", [(20.0, "OK"), (45.0, "NG")])
def test_intermediate_verdict_closes_group(harness, score, expected):
    group = group_for(harness, first_warning(harness))
    harness.fake.score = score
    result = inspect(harness, retry_payload(harness, group), capture(harness, 140)).json()
    group = group_for(harness, result)
    assert group["attempt_count"] == 2 and group["status"] == "COMPLETED"
    assert group["remaining_attempts"] == 0
    assert result["final_result"] == expected
    assert inspect(harness, retry_payload(harness, group), capture(harness)).status_code == 409


def test_model_failure_not_counted_and_next_new_capture_allowed(harness):
    group = group_for(harness, first_warning(harness))
    harness.fake.failure = RuntimeError("MOCK TEST FAILURE")
    failed = inspect(harness, retry_payload(harness, group), capture(harness)).json()
    group = group_for(harness, failed)
    assert group["attempt_count"] == 1 and len(group["failed_attempts"]) == 1
    assert failed["metrics"]["reinspection"]["attempt_number"] is None
    harness.fake.failure = None
    result = inspect(harness, retry_payload(harness, group), capture(harness)).json()
    assert group_for(harness, result)["attempt_count"] == 2


@pytest.mark.parametrize("field,value", [("same_product_confirmed", False), ("expected_version", 0),
    ("parent_inspection_id", "INSP-000001"), ("product_id", "OTHER_PRODUCT")])
def test_continuity_and_product_scope_required(harness, field, value):
    group = group_for(harness, first_warning(harness))
    payload = retry_payload(harness, group)
    payload[field] = value
    assert inspect(harness, payload, capture(harness)).status_code == 409
    assert len(harness.fake.images) == 1


@pytest.mark.parametrize("field,value", [("same_product_confirmed", 1), ("expected_version", True),
    ("group_id", "../secret"), ("request_id", "invalid")])
def test_workflow_strict_input(harness, field, value):
    payload = {**harness.payload, field: value}
    assert inspect(harness, payload).status_code == 422
    harness.factory.assert_not_called()


def test_capture_not_reused_with_different_roi_or_group(harness):
    first = first_warning(harness)
    group = group_for(harness, first)
    original = group["attempts"][0]["input_provenance"]["capture_id"]
    payload = retry_payload(harness, group)
    payload["roi"] = {**payload["roi"], "x": 18}
    assert inspect(harness, payload, original).status_code == 409
    assert len(harness.fake.images) == 1


def test_idempotency_survives_runtime_recreation(harness, monkeypatch):
    identifier = capture(harness)
    payload = {**harness.payload, "request_id": uuid4().hex}
    first = inspect(harness, payload, identifier).json()
    import backend.main as main
    monkeypatch.setattr(main.app.state, "grab_inspection_runtime", GrabInspectionRuntime(harness.directory / "inputs"))
    second = inspect(harness, payload, identifier).json()
    assert first["inspection_id"] == second["inspection_id"] and len(harness.fake.images) == 1
    assert group_for(harness, second)["attempt_count"] == 1
    assert inspect(harness, payload, capture(harness)).status_code == 409


def test_independent_groups_do_not_mix_counts(harness):
    first = group_for(harness, first_warning(harness))
    second = group_for(harness, first_warning(harness))
    assert first["group_id"] != second["group_id"]
    assert first["attempt_count"] == second["attempt_count"] == 1


@pytest.mark.parametrize("outcome", ["MANUAL_OK", "MANUAL_NG", "HOLD"])
def test_manual_review_is_separate_immutable_engine_record(harness, outcome):
    group = three_warnings(harness)
    before_records = (harness.directory / "inspections.jsonl").read_bytes()
    before_logs = (harness.directory / "logs.jsonl").read_bytes()
    response = review(harness, group, outcome)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["manual_reviews"][0]["result"] == outcome
    assert result["manual_reviews"][0]["authority"] == "DEVELOPMENT_SELF_DECLARED_NOT_AUTHENTICATED"
    assert result["status"] == ("MANUAL_REVIEW_REQUIRED" if outcome == "HOLD" else "MANUAL_REVIEWED")
    assert (harness.directory / "inspections.jsonl").read_bytes() == before_records
    assert (harness.directory / "logs.jsonl").read_bytes() == before_logs
    assert all(harness.storage.get_inspection(entry["inspection_id"]).final_result == "REINSPECT" for entry in group["attempts"])


@pytest.mark.parametrize("field,value", [("reason", "   "), ("operator_id", ""), ("result", "OK"),
    ("reason", "unsafe\ntext"), ("expected_version", True), ("path", "/private")])
def test_manual_review_validation(harness, field, value):
    group = three_warnings(harness)
    assert review(harness, group, **{field: value}).status_code == 422


def test_hold_can_be_followed_by_explicit_review_preserving_history(harness):
    group = three_warnings(harness)
    identifier = uuid4().hex
    held = review(harness, group, request_id=identifier).json()
    assert len(review(harness, group, request_id=identifier).json()["manual_reviews"]) == 1
    assert review(harness, held, request_id=identifier, reason="different").status_code == 409
    assert review(harness, group, "MANUAL_OK").status_code == 409
    final = review(harness, held, "MANUAL_NG").json()
    assert [entry["result"] for entry in final["manual_reviews"]] == ["HOLD", "MANUAL_NG"]
    assert review(harness, final, "MANUAL_OK").status_code == 409


def test_manual_review_before_limit_is_rejected(harness):
    group = group_for(harness, first_warning(harness))
    assert review(harness, group).status_code == 409


@pytest.mark.parametrize("kind", ["origin", "csrf", "owner"])
def test_manual_review_access_control(harness, kind):
    group = three_warnings(harness)
    if kind == "origin": harness.client.headers["Origin"] = "http://untrusted.invalid"
    if kind == "csrf": harness.client.headers["X-Capture-CSRF"] = "bad"
    if kind == "owner":
        token, csrf = harness.captures.bootstrap()
        harness.client.cookies.set(harness.captures.cookie_name, token)
        harness.client.headers["X-Capture-CSRF"] = csrf
    assert review(harness, group).status_code in {403, 404}
    if kind != "csrf": assert harness.client.get('/reinspection-groups/' + group["group_id"]).status_code in {403, 404}


def test_public_group_has_no_owner_and_get_without_origin_is_safe(harness):
    first = first_warning(harness)
    harness.client.headers.pop("Origin")
    group = group_for(harness, first)
    assert "owner" not in group
    assert len(harness.fake.images) == 1
    assert review(harness, group).status_code == 403


def test_new_store_reads_persistent_history_and_manual_status(harness):
    group = review(harness, three_warnings(harness), "MANUAL_NG").json()
    store = ReinspectionStore(harness.runtime.reinspections.root)
    owner = harness.captures.authorize(harness.client.cookies.get(harness.captures.cookie_name))
    assert store.get(group["group_id"], owner) == group


def test_competing_requests_only_one_enters_fake_predict(harness):
    entered = threading.Event()
    release = threading.Event()
    original = harness.fake.predict
    def waiting_predict(image):
        entered.set()
        assert release.wait(5)
        return original(image)
    harness.fake.predict = waiting_predict
    first_capture, second_capture = capture(harness), capture(harness)
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(inspect, harness, None, first_capture)
        try:
            assert entered.wait(5)
            rejected = inspect(harness, capture_id=second_capture)
            assert rejected.status_code == 409 and rejected.json()["detail"]["error_code"] == "REINSPECTION_BUSY"
        finally:
            release.set()
        assert future.result(timeout=5).status_code == 201
    assert len(harness.fake.images) == 1


@pytest.mark.parametrize("exception_type", [RuntimeError, TimeoutError])
def test_process_lock_and_exception_release(tmp_path, exception_type):
    store = ReinspectionStore(tmp_path / "history")
    locking = ("import msvcrt; msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)" if os.name == "nt"
               else "import fcntl; fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)")
    script = "import sys\nhandle=open(sys.argv[1],'r+b')\nhandle.seek(0)\ntry:\n    " + locking + "\nexcept OSError:\n    sys.exit(73)\n"
    with pytest.raises(ReinspectionError, match="REINSPECTION_STORAGE_UNAVAILABLE"):
        with store.locked():
            result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(store.root / "workflow.lock")],
                                    capture_output=True, timeout=5)
            assert result.returncode == 73
            raise exception_type("MOCK TEST FAILURE")
    assert subprocess.run([sys.executable, "-I", "-B", "-c", script, str(store.root / "workflow.lock")],
                          capture_output=True, timeout=5).returncode == 0


def test_final_group_save_failure_leaves_persistent_fail_closed_reservation(harness, monkeypatch):
    store = harness.runtime.reinspections
    original = store._write
    calls = []
    def fail_final(state):
        calls.append(True)
        if len(calls) == 2:
            raise OSError("MOCK DISK FAILURE")
        original(state)
    monkeypatch.setattr(store, "_write", fail_final)
    identifier = capture(harness)
    assert inspect(harness, capture_id=identifier).status_code == 503
    assert inspect(harness, capture_id=identifier).status_code == 409
    assert len(harness.fake.images) == 1
    saved = json.loads((store.root / "state.json").read_text(encoding="utf-8"))
    assert next(iter(saved["groups"].values()))["status"] == "RECOVERY_REQUIRED"


def test_corrupt_history_does_not_reset_counts(harness):
    group = group_for(harness, first_warning(harness))
    (harness.runtime.reinspections.root / "state.json").write_text("invalid", encoding="utf-8")
    response = inspect(harness, retry_payload(harness, group), capture(harness))
    assert response.status_code == 503 and len(harness.fake.images) == 1


@pytest.mark.parametrize("change", ["video", "revision", "dimensions"])
def test_video_revision_and_resolution_scope(harness, change):
    group = group_for(harness, first_warning(harness))
    metadata = {"video_id": "VID-OTHER" if change == "video" else "VID-000001",
        "source_revision": ("b" if change == "revision" else "a") * 64,
        "fps": 30, "width": 320, "height": 241 if change == "dimensions" else 240}
    token = harness.client.cookies.get(harness.captures.cookie_name)
    identifier = harness.captures.save(token, harness.client.headers["X-Capture-CSRF"],
        np.full((metadata["height"], metadata["width"], 3), 60, dtype=np.uint8), metadata, 125)["capture_id"]
    payload = retry_payload(harness, group)
    payload["source_revision"] = metadata["source_revision"]
    assert inspect(harness, payload, identifier).status_code == 409
    assert len(harness.fake.images) == 1


def test_lost_post_response_can_be_recovered_by_capture_without_inference(harness):
    first = first_warning(harness)
    capture_id = first["metrics"]["input_provenance"]["capture_id"]
    response = harness.client.get('/reinspection-groups/by-capture/' + capture_id)
    assert response.status_code == 200
    assert response.json() == group_for(harness, first)
    assert len(harness.fake.images) == 1
    token, csrf = harness.captures.bootstrap()
    harness.client.cookies.set(harness.captures.cookie_name, token)
    assert harness.client.get('/reinspection-groups/by-capture/' + capture_id).status_code == 404


def test_capture_expiry_does_not_erase_group_count(harness):
    first = first_warning(harness)
    harness.clock[0] += 1801
    assert group_for(harness, first)["attempt_count"] == 1
    assert len(harness.fake.images) == 1


@pytest.mark.parametrize("kind", ["same_frame", "same_png"])
def test_new_capture_id_does_not_make_same_recorded_image_a_reinspection(harness, kind):
    first = first_warning(harness)
    group = group_for(harness, first)
    source = first["metrics"]["input_provenance"]
    if kind == "same_frame":
        identifier = capture(harness, brightness=80, frame_index=source["frame_index"])
    else:
        original = harness.captures.image(harness.client.cookies.get(harness.captures.cookie_name),source["capture_id"])
        import cv2
        frame = cv2.imdecode(np.frombuffer(original,dtype=np.uint8),cv2.IMREAD_UNCHANGED)
        identifier = harness.captures.save(harness.client.cookies.get(harness.captures.cookie_name),
            harness.client.headers["X-Capture-CSRF"],frame,{"video_id":"VID-000001","source_revision":"a"*64,
                "fps":30,"width":320,"height":240},source["frame_index"]+1)["capture_id"]
    response = inspect(harness,retry_payload(harness,group),identifier)
    assert response.status_code == 409 and response.json()["detail"]["error_code"] == "REINSPECTION_SAME_RECORDED_IMAGE"
    assert len(harness.fake.images) == 1 and group_for(harness,first)["attempt_count"] == 1


def test_repeated_atomic_snapshots_are_readable(tmp_path):
    store = ReinspectionStore(tmp_path / "history")
    with store.locked():
        for version in range(200):
            state = {"schema_version": 1, "groups": {}, "captures": {}, "requests": {}, "version": version}
            store._write(state)
            assert store._read()["version"] == version


@pytest.mark.skipif(os.name != "nt", reason="Windows file replacement contention policy")
@pytest.mark.parametrize("persistent", [False, True])
def test_windows_replace_contention_is_bounded_without_reexecuting_inspection(tmp_path, monkeypatch, persistent):
    store = ReinspectionStore(tmp_path / "history")
    state = {"schema_version": 1, "groups": {}, "captures": {}, "requests": {}, "version": 0}
    with store.locked():
        store._write(state)
    original = os.replace
    calls = []
    def contended(source, target):
        calls.append(True)
        if persistent or len(calls) == 1:
            error = PermissionError(13, "MOCK TEST: Windows replacement contention")
            error.winerror = 5
            raise error
        original(source, target)
    monkeypatch.setattr("backend.reinspection_store.os.replace", contended)
    state["version"] = 1
    if persistent:
        with pytest.raises(ReinspectionError, match="REINSPECTION_STORAGE_UNAVAILABLE"):
            with store.locked():
                store._write(state)
        assert len(calls) == 4 and store._read()["version"] == 0
    else:
        with store.locked():
            store._write(state)
        assert len(calls) == 2 and store._read()["version"] == 1
    assert not list(store.root.glob("TMP-*"))
