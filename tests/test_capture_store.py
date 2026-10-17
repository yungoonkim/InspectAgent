from io import BytesIO
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import pytest

from backend.capture_store import CaptureError, CaptureStore
from tests.video_helpers import directory_link


@pytest.fixture
def store(tmp_path):
    clock = [1000.0]
    instance = CaptureStore(tmp_path / "captures", clock=lambda: clock[0], ttl_seconds=30, session_seconds=60)
    instance.test_clock = clock
    return instance


def save(store):
    token, csrf = store.bootstrap()
    frame = np.full((8, 10, 3), (3, 40, 210), np.uint8)
    metadata = {"video_id": "VID-000001", "source_revision": "a" * 64, "fps": 30, "width": 10, "height": 8}
    return token, csrf, store.save(token, csrf, frame, metadata, 120), frame


def expect(code, action, status=None):
    with pytest.raises(CaptureError) as raised:
        action()
    assert raised.value.code == code
    if status:
        assert raised.value.status_code == status


def test_png_exact_and_rgb_order(store):
    token, csrf, captured, frame = save(store)
    payload = store.image(token, captured["capture_id"])
    assert np.array_equal(cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR), frame)
    assert Image.open(BytesIO(payload)).getpixel((0, 0)) == (210, 40, 3)
    assert captured["frame_timestamp_ms"] == 4000
    assert captured["pts_ms"] is None
    assert captured["timestamp_basis"] == "CFR_FRAME_INDEX"
    assert captured["width"] == 10 and captured["height"] == 8
    assert "inspection_id" not in captured and token not in str(captured)
    assert store.metadata(token, captured["capture_id"]) == captured
    assert len(list(store.root.glob("CAP-*.png"))) == 1
    assert not list(store.root.glob("TMP-*"))


def test_session_server_generated_and_bootstrap_stable(store):
    token, csrf = store.bootstrap("client-chosen-session")
    assert token != "client-chosen-session" and len(token) == 43
    assert store.bootstrap(token) == (token, csrf)
    assert token not in store._sessions
    expect("CAPTURE_SESSION_REQUIRED", lambda: store.authorize("x" * 43, csrf, write=True), 401)


@pytest.mark.parametrize("csrf", [None, "wrong", "é" * 43])
def test_invalid_csrf(store, csrf):
    token, expected = store.bootstrap()
    expect("CAPTURE_CSRF_INVALID", lambda: store.authorize(token, csrf, write=True), 403)


def test_other_session_cannot_access(store):
    token, csrf, captured, frame = save(store)
    stranger, stranger_csrf = store.bootstrap()
    for action in (store.metadata, store.image):
        expect("CAPTURE_NOT_FOUND", lambda: action(stranger, captured["capture_id"]), 404)
        expect("CAPTURE_NOT_FOUND", lambda: action(None, captured["capture_id"]), 404)


def test_ttl_expiry_and_file_cleanup(store):
    token, csrf, captured, frame = save(store)
    store.test_clock[0] += 30
    expect("CAPTURE_NOT_FOUND", lambda: store.metadata(token, captured["capture_id"]), 404)
    assert not list(store.root.glob("CAP-*.png"))
    assert store.authorize(token, csrf, write=True)


def test_session_expiry_separate_from_capture_ttl(store):
    store.ttl_seconds = 120
    token, csrf, captured, frame = save(store)
    store.test_clock[0] += 60
    expect("CAPTURE_NOT_FOUND", lambda: store.image(token, captured["capture_id"]), 404)
    expect("CAPTURE_SESSION_REQUIRED", lambda: store.authorize(token, csrf, write=True), 401)


@pytest.mark.parametrize("setting", ["max_bytes", "max_captures", "max_per_session"])
def test_capacity(store, setting):
    existing = None
    if setting == "max_bytes":
        store.max_bytes = 1
    else:
        setattr(store, setting, 1)
        existing = save(store)
    if setting == "max_per_session":
        token, csrf, captured, frame = existing
        metadata = {"video_id": "VID-000001", "source_revision": "a" * 64, "fps": 30, "width": 10, "height": 8}
        expect("CAPTURE_CAPACITY_EXCEEDED", lambda: store.save(token, csrf, frame, metadata, 120), 503)
    else:
        expect("CAPTURE_CAPACITY_EXCEEDED", lambda: save(store), 503)
    assert not list(store.root.glob("TMP-*"))


def test_session_capacity(store):
    store.max_sessions = 1
    store.bootstrap()
    expect("CAPTURE_SESSION_LIMIT", lambda: store.bootstrap(), 503)


@pytest.mark.parametrize("operation", ["encode", "rename", "fsync"])
def test_write_failure_has_no_orphans(store, monkeypatch, operation):
    def fail(*args, **kwargs):
        raise OSError("secret/internal/path")
    if operation == "encode":
        monkeypatch.setattr(cv2, "imencode", lambda *args: (False, None))
    else:
        monkeypatch.setattr(os, "replace" if operation == "rename" else "fsync", fail)
    expect("CAPTURE_STORAGE_UNAVAILABLE", lambda: save(store), 503)
    assert not list(store.root.glob("CAP-*.png"))
    assert not list(store.root.glob("TMP-*"))
    assert not store._captures


def test_restart_invalidates_sessions_and_clears_owned_pngs(store):
    token, csrf, captured, frame = save(store)
    restarted = CaptureStore(store.root, clock=store.clock)
    expect("CAPTURE_NOT_FOUND", lambda: restarted.metadata(token, captured["capture_id"]), 404)
    new_token, new_csrf, new_capture, frame = save(restarted)
    assert not (store.root / f"{captured['capture_id']}.png").exists()
    assert (store.root / f"{new_capture['capture_id']}.png").is_file()


def test_unmanaged_directory_never_deleted(store):
    store.root.mkdir()
    foreign = store.root / "someone-else.txt"
    foreign.write_text("keep")
    expect("CAPTURE_STORAGE_UNAVAILABLE", lambda: save(store), 503)
    assert foreign.read_text() == "keep"


def test_junction_root_rejected(store, tmp_path):
    target = tmp_path / "outside"
    target.mkdir()
    directory_link(store.root, target)
    expect("CAPTURE_STORAGE_UNAVAILABLE", lambda: save(store), 503)
    assert not list(target.iterdir())


@pytest.mark.parametrize("capture_id", ["../outside.png", "CAP-invalid", "C:/Windows/win.ini", "CAP-" + "0" * 32])
def test_invalid_capture_ids(store, capture_id):
    token, csrf = store.bootstrap()
    expect("CAPTURE_NOT_FOUND", lambda: store.image(token, capture_id), 404)


def test_deleted_and_modified_png(store):
    token, csrf, captured, frame = save(store)
    path = store.root / f"{captured['capture_id']}.png"
    contents = path.read_bytes()
    path.write_bytes(bytes([contents[0] ^ 1]) + contents[1:])
    expect("CAPTURE_NOT_FOUND", lambda: store.image(token, captured["capture_id"]), 404)
    path.unlink()
    expect("CAPTURE_NOT_FOUND", lambda: store.metadata(token, captured["capture_id"]), 404)


def test_close_removes_own_captures(store):
    save(store)
    store.close()
    assert not list(store.root.glob("CAP-*.png"))
    assert not store._sessions
