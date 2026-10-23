"""Synthetic PNG and MOCK TEST inferencer integration; no model/video/network."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
from fastapi.testclient import TestClient
import numpy as np
import pytest

import backend.main as main
from backend.capture_store import CaptureStore
from backend.config import Settings
from backend.grab_inspection import GrabInspectionRuntime
from backend.storage import JsonlInspectionStorage, StorageWriteError


class MockInferencer:
    device = "cpu"

    def __init__(self):
        self.images = []
        self.score = 20.0
        self.failure = None

    def predict(self, image):
        self.images.append(image.copy())
        if self.failure:
            raise self.failure
        signal = np.add.outer(np.arange(256, dtype=np.float32), np.arange(256, dtype=np.float32) * 2)
        return {"anomaly_score": self.score, "anomaly_map": signal, "inference_time_ms": 1.0, "model_name": "MOCK_TEST_ONLY"}


@pytest.fixture
def harness(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, OUTPUT_DIR=str(tmp_path), ENABLE_PATCHCORE=True,
                        JUDGE_ASSISTED_WORKFLOW_ENABLED=False,
                        BRIGHTNESS_LOW_THRESHOLD=125, BRIGHTNESS_HIGH_THRESHOLD=150)
    clock = [1000.0]
    captures = CaptureStore(tmp_path / "captures", clock=lambda: clock[0])
    token, csrf = captures.bootstrap()
    frame = np.full((240, 320, 3), 140, dtype=np.uint8)
    frame[:, :, 0] = 90
    frame[:, :, 2] = 180
    metadata = captures.save(token, csrf, frame, {"video_id": "VID-000001", "source_revision": "a" * 64,
        "fps": 30, "width": 320, "height": 240}, 120)
    runtime = GrabInspectionRuntime(tmp_path / "inputs")
    storage = JsonlInspectionStorage(tmp_path / "inspections.jsonl", tmp_path / "logs.jsonl")
    fake = MockInferencer()
    factory = Mock(return_value=fake)
    monkeypatch.setattr(main, "get_patchcore_inferencer", factory)
    monkeypatch.setattr(main, "get_inspection_storage", lambda: storage)
    monkeypatch.setenv("ANOMALY_MAP_DIR", str(tmp_path / "maps"))
    monkeypatch.setattr(main.app.state, "video_runtime", SimpleNamespace(settings=settings, captures=captures,
        origins=["http://localhost:5173"]), raising=False)
    monkeypatch.setattr(main.app.state, "grab_inspection_runtime", runtime, raising=False)
    client = TestClient(main.app)
    client.cookies.set(CaptureStore.cookie_name, token)
    client.headers.update({"Origin": "http://localhost:5173", "X-Capture-CSRF": csrf})
    payload = {"product_id": "ABCD1541", "source_revision": "a" * 64,
               "roi": {"x": 17, "y": 21, "width": 160, "height": 96}}
    yield SimpleNamespace(client=client, captures=captures, metadata=metadata, runtime=runtime, storage=storage,
        frame=frame, payload=payload, fake=fake, factory=factory, directory=tmp_path, clock=clock)
    client.close()


def inspect(harness, payload=None, capture_id=None):
    return harness.client.post(f'/captures/{capture_id or harness.metadata["capture_id"]}/inspect',
                               json=payload or harness.payload)


def test_mock_crop_pipeline_preserves_pixels_links_record_and_map(harness):
    original = harness.captures.image(harness.client.cookies.get(CaptureStore.cookie_name), harness.metadata["capture_id"])
    response = inspect(harness)
    assert response.status_code == 201, response.text
    result = response.json()
    identifier = result["inspection_id"]
    assert identifier.startswith("INSP-") and result["image_id"].startswith("IMG-GRAB-")
    assert len(harness.fake.images) == 1
    crop = harness.frame[21:117, 17:177]
    assert np.array_equal(harness.fake.images[0], crop)
    assert result["metrics"]["model_version"] == "MOCK_TEST_ONLY"
    assert result["final_result"] == "OK"
    source = result["metrics"]["input_provenance"]
    assert source["capture_id"] == harness.metadata["capture_id"] and source["frame_index"] == 120
    assert source["roi"] == harness.payload["roi"] and source["model_input_resolution"] == [256, 256]
    assert "실험적" in source["limitation"]
    raw_image = harness.client.get(f"/inspections/{identifier}/input-image")
    decoded = cv2.imdecode(np.frombuffer(raw_image.content, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    assert np.array_equal(decoded, crop)
    assert hashlib.sha256(raw_image.content).hexdigest() == source["crop_sha256"]
    map_response = harness.client.get(f"/inspections/{identifier}/anomaly-map")
    assert map_response.status_code == 200
    metadata = map_response.json()
    assert metadata["image_id"] == result["image_id"]
    assert (metadata["original_image_width"], metadata["original_image_height"]) == (160, 96)
    assert metadata["spatial_transform"]["crop"] is None
    assert metadata["spatial_transform"]["original_resolution"] == [160, 96]
    overlay = harness.client.get(f"/inspections/{identifier}/anomaly-map/overlay.png")
    assert overlay.status_code == 200 and overlay.headers["cache-control"] == "no-store"
    rgba = cv2.imdecode(np.frombuffer(overlay.content, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    assert rgba.shape == (96, 160, 4)
    signal = np.add.outer(np.arange(256, dtype=np.float32), np.arange(256, dtype=np.float32) * 2)
    expected = cv2.resize(signal / signal.max(), (160, 96), interpolation=cv2.INTER_LINEAR)
    expected_colors = cv2.applyColorMap((expected * 255).astype(np.uint8), cv2.COLORMAP_JET)
    assert np.array_equal(rgba[:, :, :3], expected_colors)
    assert harness.captures.image(harness.client.cookies.get(CaptureStore.cookie_name), harness.metadata["capture_id"]) == original
    stored = harness.storage.get_inspection(identifier)
    assert stored.metrics["input_provenance"] == source
    assert len(harness.storage.get_logs(identifier)) == 6


@pytest.mark.parametrize("field,value", [("x", -1), ("x", True), ("x", 1.5), ("width", 0),
    ("width", 15), ("height", False), ("width", 5000), ("unknown", 1)])
def test_invalid_roi_fails_before_model_or_record(harness, field, value):
    payload = json.loads(json.dumps(harness.payload))
    payload["roi"][field] = value
    assert inspect(harness, payload).status_code == 422
    harness.factory.assert_not_called()
    assert (harness.directory / "inspections.jsonl").read_text() == ""


@pytest.mark.parametrize("change,status", [("revision", 409), ("bounds", 422), ("extra", 422), ("path", 404)])
def test_revision_bounds_extra_and_path_rejected(harness, change, status):
    payload = json.loads(json.dumps(harness.payload))
    identifier = harness.metadata["capture_id"]
    if change == "revision": payload["source_revision"] = "b" * 64
    if change == "bounds": payload["roi"]["x"] = 300
    if change == "extra": payload["path"] = "C:/private/secret.png"
    if change == "path": identifier = "INSP-000001"
    assert inspect(harness, payload, identifier).status_code == status
    harness.factory.assert_not_called()


@pytest.mark.parametrize("kind", ["csrf", "origin", "session", "expired", "missing"])
def test_capture_authorization_and_ttl(harness, kind):
    if kind == "csrf": harness.client.headers["X-Capture-CSRF"] = "invalid"
    if kind == "origin": harness.client.headers["Origin"] = "http://untrusted.invalid"
    if kind == "session": harness.client.cookies.clear()
    if kind == "expired": harness.clock[0] += 1801
    if kind == "missing": (harness.directory / "captures" / f'{harness.metadata["capture_id"]}.png').unlink()
    assert inspect(harness).status_code in {401, 403, 404}
    harness.factory.assert_not_called()


def test_other_session_cannot_read_grab_image_or_map(harness):
    result = inspect(harness).json()
    identifier = result["inspection_id"]
    token, csrf = harness.captures.bootstrap()
    harness.client.cookies.set(CaptureStore.cookie_name, token)
    harness.client.headers["X-Capture-CSRF"] = csrf
    assert inspect(harness).status_code == 404
    for suffix in ("input-image", "anomaly-map", "anomaly-map/overlay.png"):
        assert harness.client.get(f"/inspections/{identifier}/{suffix}").status_code == 404
    assert len(harness.fake.images) == 1


def test_duplicate_requests_do_not_repeat_inference_or_overwrite_sidecars(harness):
    first = inspect(harness).json()
    before = {path.name: path.read_bytes() for path in (harness.directory / "maps").iterdir()}
    second = inspect(harness).json()
    assert second["inspection_id"] == first["inspection_id"] and len(harness.fake.images) == 1
    assert before == {path.name: path.read_bytes() for path in (harness.directory / "maps").iterdir()}
    harness.payload["roi"]["x"] += 1
    third = inspect(harness)
    assert third.status_code == 409
    assert third.json()["detail"]["error_code"] == "CAPTURE_ALREADY_USED"
    assert len(harness.fake.images) == 1
    for name, raw in before.items(): assert (harness.directory / "maps" / name).read_bytes() == raw


def test_input_survives_capture_ttl_but_not_owner_session_expiry(harness):
    identifier = inspect(harness).json()["inspection_id"]
    harness.clock[0] += 1801
    assert harness.client.get(f"/inspections/{identifier}/input-image").status_code == 200
    harness.clock[0] += 2000
    assert harness.client.get(f"/inspections/{identifier}/input-image").status_code == 404


def test_busy_request_never_enters_model(harness):
    with harness.runtime._lock:
        response = inspect(harness)
    assert response.status_code == 409 and response.json()["detail"]["error_code"] == "GRAB_INSPECTION_BUSY"
    harness.factory.assert_not_called()


def test_model_failure_is_error_not_a_product_ng(harness):
    harness.fake.failure = RuntimeError("MOCK_TEST_FAILURE")
    response = inspect(harness)
    assert response.status_code == 201
    assert response.json()["final_result"] == "REINSPECT"
    assert response.json()["final_reason_code"] == "DEFECT_DETECTION_UNAVAILABLE"
    assert response.json()["result"] == "UNKNOWN" and response.json()["anomaly_score"] is None
    assert not list((harness.directory / "maps").glob("*.json"))


def test_unavailable_model_does_not_issue_inspection(harness):
    harness.factory.return_value = None
    assert inspect(harness).status_code == 503
    assert (harness.directory / "inspections.jsonl").read_text() == ""


def test_storage_failure_is_not_automatically_retried(harness, monkeypatch):
    monkeypatch.setattr(harness.storage, "save_inspection", Mock(side_effect=StorageWriteError("PRIVATE")))
    response = inspect(harness)
    assert response.status_code == 503 and "PRIVATE" not in response.text
    assert inspect(harness).status_code == 409 and len(harness.fake.images) == 1


@pytest.mark.parametrize("kind,status", [("format", 415), ("damaged", 422), ("gray", 422), ("alpha", 422)])
def test_unsupported_or_damaged_input_rejected_without_prediction(harness, monkeypatch, kind, status):
    raw = b"not PNG" if kind == "format" else b"\x89PNG\r\n\x1a\ninvalid"
    if kind in {"gray", "alpha"}:
        shape = (240, 320) if kind == "gray" else (240, 320, 4)
        success, encoded = cv2.imencode(".png", np.full(shape, 140, dtype=np.uint8))
        assert success
        raw = encoded.tobytes()
    monkeypatch.setattr(harness.captures, "image", lambda *arguments: raw)
    assert inspect(harness).status_code == status
    harness.factory.assert_not_called()


@pytest.mark.parametrize("score,expected", [(45.0, "NG"), (34.1442, "OK"), (float("nan"), "REINSPECT")])
def test_existing_score_and_final_verdict_policy(harness, score, expected):
    harness.fake.score = score
    result = inspect(harness).json()
    assert result["final_result"] == expected
    if expected == "REINSPECT":
        assert result["result"] == "UNKNOWN" and result["anomaly_score"] is None


def test_separate_capture_cannot_reuse_previous_inspection_or_pixels(harness):
    first = inspect(harness).json()
    token = harness.client.cookies.get(CaptureStore.cookie_name)
    frame = np.full((240, 320, 3), 132, dtype=np.uint8)
    csrf = harness.client.headers["X-Capture-CSRF"]
    second_capture = harness.captures.save(token, csrf, frame, {"video_id":"VID-000001", "source_revision":"a" * 64,
        "fps":30, "width":320, "height":240}, 121)
    second = inspect(harness, capture_id=second_capture["capture_id"]).json()
    assert first["inspection_id"] != second["inspection_id"] and first["image_id"] != second["image_id"]
    assert second["metrics"]["input_provenance"]["capture_id"] == second_capture["capture_id"]
    assert second["metrics"]["input_provenance"]["frame_index"] == 121
    assert np.array_equal(harness.fake.images[1], frame[21:117,17:177])
    assert not np.array_equal(harness.fake.images[0], harness.fake.images[1])


def test_map_save_failure_is_explicit_without_changing_verdict(harness, monkeypatch):
    monkeypatch.setattr("backend.inspection.save_anomaly_map_artifact", Mock(side_effect=OSError("MOCK_STORAGE_FAILURE")))
    result = inspect(harness).json()
    assert result["final_result"] == "OK" and result["metrics"]["anomaly_map_available"] is False
    assert harness.client.get(f'/inspections/{result["inspection_id"]}/anomaly-map').status_code == 404
    assert len(harness.fake.images) == 1


def test_cuda_or_unverified_spatial_transform_blocks_before_model(harness):
    harness.fake.device = "cuda"
    assert inspect(harness).status_code == 503
    assert harness.fake.images == []
    harness.fake.device = "cpu"
    harness.fake.model = SimpleNamespace(pre_processor=None)
    harness.fake.transform = SimpleNamespace()
    response = inspect(harness)
    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "GRAB_SPATIAL_TRANSFORM_UNVERIFIED"
    assert harness.fake.images == []
