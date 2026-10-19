"""Two independently generated synthetic Crops through real API code with Fake inference/SDK."""

import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import cv2
import numpy as np
import pytest

import backend.main as main
from backend.capture_store import CaptureStore
from backend.vision_review import VisionReviewService
from tests.test_grab_inspection import harness
from tests.test_vision_review import FakeVisionClient


@pytest.fixture
def dynamic(harness, monkeypatch):
    fake = FakeVisionClient()
    service = VisionReviewService(harness.directory / "dynamic-vision", fake_client=fake, allow_fake=True)
    monkeypatch.setattr(main.app.state, "vision_review_service", service, raising=False)
    return SimpleNamespace(h=harness, fake=fake, service=service)


def new_crop(runtime, variant):
    rows, columns = np.indices((240, 320))
    frame = np.stack(((columns + variant * 11) % 90 + 20,
                      (rows + variant * 17) % 80 + 25,
                      (rows + columns + variant * 23) % 70 + 30), axis=-1).astype(np.uint8)
    metadata = runtime.h.captures.save(runtime.h.client.cookies.get(CaptureStore.cookie_name),
        runtime.h.client.headers["X-Capture-CSRF"], frame,
        {"video_id": "VID-000001", "source_revision": "a" * 64, "fps": 30, "width": 320, "height": 240},
        150 + variant)
    roi = {"x": 17 + variant * 13, "y": 21 + variant * 7, "width": 160, "height": 96}
    response = runtime.h.client.post(f'/captures/{metadata["capture_id"]}/inspect', json={
        "product_id": "SYNTHETIC_PRODUCT_" + str(variant), "source_revision": metadata["source_revision"],
        "roi": roi, "request_id": uuid4().hex})
    assert response.status_code == 201, response.text
    record = response.json()
    expected = frame[roi["y"]:roi["y"] + roi["height"], roi["x"]:roi["x"] + roi["width"]]
    assert np.array_equal(runtime.h.fake.images[-1], expected)
    assert record["final_result"] == "REINSPECT"
    return record


def submit(runtime, record, request_id=None, confirmed=True):
    return runtime.h.client.post(f'/inspections/{record["inspection_id"]}/vision-review', json={
        "request_id": request_id or uuid4().hex, "confirm_external_transmission": confirmed})


def test_two_new_crops_have_distinct_dynamic_ids_hashes_maps_logs_and_bound_consent(dynamic):
    first, second = new_crop(dynamic, 1), new_crop(dynamic, 2)
    assert first["inspection_id"] != second["inspection_id"] and first["image_id"] != second["image_id"]
    assert first["metrics"]["input_provenance"]["crop_sha256"] != second["metrics"]["input_provenance"]["crop_sha256"]
    assert first["metrics"]["input_provenance"]["capture_id"] != second["metrics"]["input_provenance"]["capture_id"]
    paths = [*dynamic.h.directory.glob("*.jsonl"), *dynamic.h.runtime.root.glob("*"),
             * (dynamic.h.directory / "maps").glob("*"), dynamic.h.runtime.reinspections.root / "state.json"]
    before = {path: path.read_bytes() for path in paths if path.is_file()}
    for index, record in enumerate((first, second)):
        identifier = record["inspection_id"]
        metadata = dynamic.h.client.get(f"/inspections/{identifier}/anomaly-map")
        assert metadata.status_code == 200 and metadata.json()["image_id"] == record["image_id"]
        assert any(log.event_code == "INSPECTION_COMPLETED" for log in dynamic.h.storage.get_logs(identifier))
        request_id = uuid4().hex
        response = submit(dynamic, record, request_id)
        assert response.status_code == 200, response.text
        review = response.json()["review"]
        assert review["inspection_id"] == identifier and review["image_id"] == record["image_id"]
        assert review["analysis_mode"] == "FAKE_TEST" and review["analysis_status"] == "COMPLETED"
        raw = (dynamic.h.runtime.root / f'{record["image_id"]}.png').read_bytes()
        assert dynamic.fake.calls[index]["contents"][0]["parts"][1]["inline_data"]["data"] == raw
        assert review["image_sha256"] == hashlib.sha256(raw).hexdigest()
        entry = json.loads((dynamic.service.files.root / "state.json").read_text(encoding="utf-8"))["reviews"][identifier]
        assert entry["transmission_consent"]["request_id"] == request_id
        assert entry["transmission_consent"]["image_sha256"] == review["image_sha256"]
        assert entry["transmission_consent"]["inspection_id"] == identifier
        assert review["consent_confirmed_at"] == entry["transmission_consent"]["confirmed_at"]
        assert submit(dynamic, record, request_id).json()["review"] == review
        assert submit(dynamic, record).status_code == 409
    assert len(dynamic.fake.calls) == 2 and len(dynamic.h.fake.images) == 2
    assert all(path.read_bytes() == content for path, content in before.items())


@pytest.mark.parametrize("confirmation,expected", [(False, 403), (None, 422), (1, 422), ("true", 422)])
def test_consent_is_mandatory_strict_and_never_sends_without_it(dynamic, confirmation, expected):
    record = new_crop(dynamic, 1)
    assert submit(dynamic, record, confirmed=confirmation).status_code == expected
    assert not dynamic.fake.calls and not dynamic.service.files.root.exists()
    omitted = dynamic.h.client.post(f'/inspections/{record["inspection_id"]}/vision-review', json={"request_id": uuid4().hex})
    assert omitted.status_code == 403 and not dynamic.fake.calls


def test_request_id_cannot_authorize_a_different_image(dynamic):
    first, second = new_crop(dynamic, 1), new_crop(dynamic, 2)
    request_id = uuid4().hex
    assert submit(dynamic, first, request_id).status_code == 200
    assert submit(dynamic, second, request_id).status_code == 409
    assert len(dynamic.fake.calls) == 1
    assert submit(dynamic, second).status_code == 200
    assert len(dynamic.fake.calls) == 2


def test_expired_capture_does_not_require_new_grab_to_judge_its_durable_crop(dynamic):
    record = new_crop(dynamic, 1)
    dynamic.h.clock[0] += 1801
    dynamic.h.captures.cleanup()
    assert not list(dynamic.h.captures.root.glob("CAP-*.png"))
    response = submit(dynamic, record)
    assert response.status_code == 200, response.text
    assert response.json()["review"]["image_sha256"] == record["metrics"]["input_provenance"]["crop_sha256"]
    assert len(dynamic.h.fake.images) == 1


def test_new_server_session_can_inspect_new_product_without_claiming_old_group(dynamic, monkeypatch):
    first = new_crop(dynamic, 1)
    old_group = first["metrics"]["reinspection"]["group_id"]
    state_path = dynamic.h.runtime.reinspections.root / "state.json"
    previous = json.loads(state_path.read_text(encoding="utf-8"))["groups"][old_group]
    replacement = CaptureStore(dynamic.h.directory / "restarted-captures", clock=lambda: dynamic.h.clock[0])
    old_cookie = dynamic.h.client.cookies.get(CaptureStore.cookie_name)
    cookie, csrf = replacement.bootstrap(old_cookie)
    dynamic.h.client.cookies.set(CaptureStore.cookie_name, cookie)
    dynamic.h.client.headers["X-Capture-CSRF"] = csrf
    dynamic.h.captures = replacement
    monkeypatch.setattr(main.app.state.video_runtime, "captures", replacement)
    assert dynamic.h.client.get('/reinspection-groups/' + old_group).status_code == 404
    assert submit(dynamic, first).status_code == 404
    second = new_crop(dynamic, 2)
    assert second["metrics"]["reinspection"]["group_id"] != old_group
    assert submit(dynamic, second).status_code == 200
    assert json.loads(state_path.read_text(encoding="utf-8"))["groups"][old_group] == previous
    assert dynamic.h.storage.get_inspection(first["inspection_id"]).final_result == "REINSPECT"
