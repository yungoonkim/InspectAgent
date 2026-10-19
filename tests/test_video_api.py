from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import cv2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import pytest

from backend.capture_store import CaptureStore
from backend.config import PROJECT_ROOT, Settings
from backend.video_api import VideoRuntime, allowed_origins, get_video_runtime, router
from backend.video_source import DEMO_VIDEO, VideoFileSource
from tests.video_helpers import synthetic_video


ORIGIN = "http://localhost:5173"


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    return synthetic_video(tmp_path_factory.mktemp("video-api"))


@pytest.fixture
def api(tmp_path, clip):
    settings = Settings(_env_file=None, CAPTURE_DIR=str(tmp_path / "captures"))
    runtime = VideoRuntime(settings)
    runtime.source = VideoFileSource(clip[0].parent, [clip[1]])
    clock = [1000.0]
    runtime.captures = CaptureStore(tmp_path / "captures", clock=lambda: clock[0], ttl_seconds=30, session_seconds=60)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_video_runtime] = lambda: runtime
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins(settings), allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    with TestClient(app) as client:
        yield SimpleNamespace(app=app, client=client, runtime=runtime, entry=clip[1], clock=clock)
    runtime.captures.close()


def bootstrap(client):
    response = client.post("/capture-sessions", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    return {"Origin": ORIGIN, "X-Capture-CSRF": response.json()["csrf_token"]}


def grab(api, index=120, **kwargs):
    headers = kwargs.pop("headers", None) or bootstrap(api.client)
    return api.client.post("/videos/VID-000001/grab", headers=headers,
                           json={"frame_index": index, "source_revision": api.entry.source_revision}, **kwargs)


def test_list_and_detail(api):
    response = api.client.get("/videos")
    assert response.status_code == 200
    metadata = response.json()["videos"][0]
    assert metadata["video_id"] == "VID-000001"
    assert metadata["source_revision"] == api.entry.source_revision
    assert metadata["frame_count"] == 240 and metadata["duration_seconds"] == 8
    assert api.client.get("/videos/VID-000001").json() == metadata
    assert "clip.mp4" not in response.text and str(api.runtime.source.root) not in response.text


def test_openapi_contract_unique_operations(api):
    schema = api.client.get("/openapi.json").json()
    operations = [definition["operationId"] for methods in schema["paths"].values() for definition in methods.values()]
    assert len(operations) == len(set(operations)) == 8
    assert "video/mp4" in schema["paths"]["/videos/{video_id}/stream"]["get"]["responses"]["200"]["content"]
    assert "image/png" in schema["paths"]["/captures/{capture_id}/image"]["get"]["responses"]["200"]["content"]


def test_stream_get_head_range_and_416(api, clip):
    url = "/videos/VID-000001/stream"
    complete = api.client.get(url)
    assert complete.status_code == 200 and complete.content == clip[0].read_bytes()
    assert complete.headers["content-type"] == "video/mp4"
    assert complete.headers["accept-ranges"] == "bytes"
    assert complete.headers["etag"] == f'"{api.entry.source_revision}"'
    head = api.client.head(url)
    assert head.status_code == 200 and head.content == b""
    assert int(head.headers["content-length"]) == len(complete.content)
    partial = api.client.get(url, headers={"Range": "bytes=10-29"})
    assert partial.status_code == 206 and partial.content == complete.content[10:30]
    assert partial.headers["content-range"] == f"bytes 10-29/{len(complete.content)}"
    assert partial.headers["content-length"] == "20"
    invalid = api.client.get(url, headers={"Range": f"bytes={len(complete.content)}-"})
    assert invalid.status_code == 416
    assert invalid.headers["content-range"] == f"bytes */{len(complete.content)}"


@pytest.mark.parametrize("frame_index", [0, 60, 120, 180, 239])
def test_grab_png_and_metadata(api, frame_index):
    response = grab(api, frame_index)
    assert response.status_code == 201
    result = response.json()
    assert result["frame_index"] == frame_index
    assert result["frame_timestamp_ms"] == frame_index / 30 * 1000
    assert result["timestamp_basis"] == "CFR_FRAME_INDEX" and result["pts_ms"] is None
    assert result["width"] == 64 and result["height"] == 48
    assert result["status"] == "CAPTURED" and "inspection_id" not in result
    assert api.client.get(f"/captures/{result['capture_id']}").json() == result
    image = api.client.get(result["image_url"])
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert image.headers["cache-control"] == "no-store"
    decoded = cv2.imdecode(np.frombuffer(image.content, np.uint8), cv2.IMREAD_COLOR)
    reference, metadata = api.runtime.source.grab_frame("VID-000001", frame_index, api.entry.source_revision)
    assert np.array_equal(decoded, reference)
    assert Image.open(BytesIO(image.content)).getpixel((10, 10)) == tuple(int(value) for value in reference[10, 10, ::-1])


@pytest.mark.parametrize("payload", [
    {}, {"frame_index": True}, {"frame_index": 1.0}, {"frame_index": "1"},
    {"frame_index": -1}, {"frame_index": 240}, {"frame_index": 1, "path": "../outside"},
    {"frame_index": 1, "source_revision": "bad"},
])
def test_invalid_payload(api, payload):
    body = {"source_revision": api.entry.source_revision, **payload}
    headers = bootstrap(api.client)
    response = api.client.post("/videos/VID-000001/grab", json=body, headers=headers)
    assert response.status_code == 422
    assert not api.runtime.captures._captures


def test_extra_field_is_forbidden(api):
    response = api.client.post("/videos/VID-000001/grab", headers=bootstrap(api.client),
                               json={"frame_index": 0, "source_revision": api.entry.source_revision, "capture_id": "chosen"})
    assert response.status_code == 422
    missing_revision = api.client.post("/videos/VID-000001/grab", headers=bootstrap(api.client), json={"frame_index": 0})
    assert missing_revision.status_code == 422


def test_revision_and_unknown_video(api):
    headers = bootstrap(api.client)
    response = api.client.post("/videos/VID-000001/grab", headers=headers, json={"frame_index": 0, "source_revision": "0" * 64})
    assert response.status_code == 409 and response.json()["detail"]["error_code"] == "VIDEO_REVISION_MISMATCH"
    for suffix in ("", "/stream"):
        assert api.client.get(f"/videos/VID-999999{suffix}").status_code == 404
    response = api.client.post("/videos/VID-999999/grab", headers=headers, json={"frame_index": 0, "source_revision": "0" * 64})
    assert response.status_code == 404
    assert not api.runtime.captures._captures


def test_changed_source_blocks_stream_and_grab(api):
    from dataclasses import replace
    api.runtime.source.entries["VID-000001"] = replace(api.entry, source_revision="0" * 64)
    for action in [lambda: api.client.get("/videos/VID-000001"),
                   lambda: api.client.get("/videos/VID-000001/stream"), lambda: grab(api)]:
        response = action()
        assert response.status_code == 409
        assert response.json()["detail"]["error_code"] == "VIDEO_REVISION_CHANGED"
    assert not api.runtime.captures._captures


def test_session_csrf_and_origin(api):
    body = {"frame_index": 0, "source_revision": api.entry.source_revision}
    assert api.client.post("/capture-sessions").status_code == 403
    assert api.client.post("/capture-sessions", headers={"Origin": "https://untrusted.invalid"}).status_code == 403
    assert api.client.post("/videos/VID-000001/grab", json=body, headers={"Origin": ORIGIN}).status_code == 401
    headers = bootstrap(api.client)
    assert api.client.post("/videos/VID-000001/grab", json=body, headers={"Origin": ORIGIN}).status_code == 403
    assert api.client.post("/videos/VID-000001/grab", json=body, headers={**headers, "Origin": "null"}).status_code == 403
    assert api.client.post("/videos/VID-000001/grab", json=body, headers=headers).status_code == 201


def test_cookie_and_secure_mode(api):
    response = api.client.post("/capture-sessions", headers={"Origin": ORIGIN})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    assert "secure" not in cookie
    assert "vision_capture_session" not in response.text
    api.runtime.settings.ENVIRONMENT = "production"
    response = api.client.post("/capture-sessions", headers={"Origin": ORIGIN})
    assert "secure" in response.headers["set-cookie"].lower()


def test_cross_session_and_expiry(api):
    captured = grab(api).json()
    with TestClient(api.app) as other:
        bootstrap(other)
        assert other.get(captured["image_url"]).status_code == 404
        assert other.get(f"/captures/{captured['capture_id']}").status_code == 404
    api.clock[0] += 30
    assert api.client.get(captured["image_url"]).status_code == 404
    assert not list(api.runtime.captures.root.glob("CAP-*.png"))


def test_failures_are_sanitized_and_no_capture(api, monkeypatch):
    def fail(path):
        raise RuntimeError("secret C:/private/path api-key")
    api.runtime.source._capture_factory = fail
    response = grab(api, 0)
    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "VIDEO_DECODE_FAILED"
    assert "secret" not in response.text and "private" not in response.text
    assert not api.runtime.captures._captures


def test_storage_failure_and_busy(api, monkeypatch):
    monkeypatch.setattr(cv2, "imencode", lambda *args: (False, None))
    response = grab(api)
    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "CAPTURE_STORAGE_UNAVAILABLE"
    assert not api.runtime.captures._captures
    assert api.runtime.source._slots.acquire(False) and api.runtime.source._slots.acquire(False)
    try:
        response = grab(api)
        assert response.status_code == 429
    finally:
        api.runtime.source._slots.release()
        api.runtime.source._slots.release()


def test_cors_credentials_and_blocked_origin(api):
    allowed = api.client.options("/videos/VID-000001/grab", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,x-capture-csrf"})
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert allowed.headers["access-control-allow-credentials"] == "true"
    rejected = api.client.options("/videos", headers={"Origin": "https://untrusted.invalid", "Access-Control-Request-Method": "GET"})
    assert rejected.status_code == 400 and "access-control-allow-origin" not in rejected.headers
    settings = Settings(_env_file=None, CORS_ALLOWED_ORIGINS="*")
    with pytest.raises(ValueError):
        allowed_origins(settings)


def test_real_approved_video_and_main_router(tmp_path):
    import time
    from backend.main import app
    approved = PROJECT_ROOT / "data/outputs/videos" / DEMO_VIDEO.relative_path
    if not approved.exists():
        pytest.skip("Approved H.264 demo file is not installed; synthetic security/API tests remain independent")
    runtime = VideoRuntime(Settings(_env_file=None, VIDEO_ROOT=str(approved.parent), CAPTURE_DIR=str(tmp_path / "captures")))
    clock = [time.time()]
    runtime.captures.clock = lambda: clock[0]
    app.dependency_overrides[get_video_runtime] = lambda: runtime
    try:
        client = TestClient(app)
        metadata = client.get("/videos").json()["videos"][0]
        assert metadata["source_revision"] == DEMO_VIDEO.source_revision
        assert metadata["width"] == 1920 and metadata["height"] == 480
        assert metadata["codec"] == "h264"
        assert client.get("/health").status_code == 200
        assert metadata["video_id"] == DEMO_VIDEO.video_id
        stream = metadata["stream_url"]
        assert client.get(stream).content == approved.read_bytes()
        assert int(client.head(stream).headers["content-length"]) == approved.stat().st_size
        assert client.get(stream, headers={"Range": "bytes=0-31"}).status_code == 206
        assert client.get(stream, headers={"Range": f"bytes={approved.stat().st_size}-"}).status_code == 416
        headers = bootstrap(client)
        for frame_index in (0, 120, 239):
            response = client.post(f"/videos/{DEMO_VIDEO.video_id}/grab", headers=headers, json={"frame_index": frame_index, "source_revision": DEMO_VIDEO.source_revision})
            assert response.status_code == 201
            captured = response.json()
            assert captured["frame_timestamp_ms"] == frame_index / 30 * 1000
            png = client.get(captured["image_url"])
            reference, information = runtime.source.grab_frame(DEMO_VIDEO.video_id, frame_index, DEMO_VIDEO.source_revision)
            assert captured["video_id"] == DEMO_VIDEO.video_id
            assert captured["source_revision"] == metadata["source_revision"]
            assert np.array_equal(cv2.imdecode(np.frombuffer(png.content, np.uint8), cv2.IMREAD_COLOR), reference)
            direct = cv2.VideoCapture(str(approved))
            try:
                for _index in range(frame_index + 1):
                    available, expected_frame = direct.read()
                    assert available
            finally:
                direct.release()
            assert np.array_equal(reference, expected_frame)
            assert np.array_equal(reference[121:399, 1014:1305], expected_frame[121:399, 1014:1305])
            assert "inspection_id" not in captured
        for frame_index, revision, expected in [(240, DEMO_VIDEO.source_revision, 422), (120, "0" * 64, 409)]:
            before = len(runtime.captures._captures)
            assert client.post(f"/videos/{DEMO_VIDEO.video_id}/grab", headers=headers, json={"frame_index": frame_index, "source_revision": revision}).status_code == expected
            assert len(runtime.captures._captures) == before
        stranger = TestClient(app)
        try:
            bootstrap(stranger)
            assert stranger.get(captured["image_url"]).status_code == 404
        finally:
            stranger.close()
        clock[0] += runtime.captures.ttl_seconds
        assert client.get(captured["image_url"]).status_code == 404
        assert not list(runtime.captures.root.glob("CAP-*.png"))
    finally:
        app.dependency_overrides.pop(get_video_runtime, None)
        runtime.captures.close()
