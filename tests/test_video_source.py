from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import threading
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from backend.video_source import DEMO_VIDEO, VideoEntry, VideoError, VideoFileSource
from tests.video_helpers import directory_link, synthetic_video


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    return synthetic_video(tmp_path_factory.mktemp("video-source"))


@pytest.fixture
def source(clip):
    path, entry = clip
    return VideoFileSource(path.parent, [entry])


def assert_error(code, action, status=None):
    with pytest.raises(VideoError) as raised:
        action()
    assert raised.value.code == code
    if status is not None:
        assert raised.value.status_code == status


def test_list_and_metadata_no_paths(source):
    listed = source.list_videos()
    assert len(listed) == 1
    assert listed[0]["video_id"] == "VID-000001"
    assert listed[0]["width"] == 64
    assert listed[0]["height"] == 48
    assert listed[0]["fps"] == 30
    assert listed[0]["frame_count"] == 240
    assert listed[0]["frame_index_max"] == 239
    assert listed[0]["duration_seconds"] == 8
    assert "clip.mp4" not in str(listed)


@pytest.mark.parametrize("video_id", ["VID-999999", "../clip.mp4", "C:/Windows/win.ini", "%2e%2e", "clip.mp4"])
def test_unknown_ids(source, video_id):
    assert_error("VIDEO_NOT_FOUND", lambda: source.metadata(video_id), 404)


def test_missing_file(tmp_path):
    source = VideoFileSource(tmp_path)
    assert_error("VIDEO_NOT_AVAILABLE", lambda: source.metadata(DEMO_VIDEO.video_id), 404)


def test_revision_changed(clip):
    path, entry = clip
    source = VideoFileSource(path.parent, [replace(entry, source_revision="0" * 64)])
    assert_error("VIDEO_REVISION_CHANGED", lambda: source.metadata(entry.video_id), 409)


def test_request_revision_mismatch(source):
    assert_error("VIDEO_REVISION_MISMATCH", lambda: source.grab_frame("VID-000001", 0, "0" * 64), 409)


@pytest.mark.parametrize("frame_index", [True, False, -1, 240, 900, 1.0, "1", None])
def test_strict_frame_index(source, clip, frame_index):
    assert_error("FRAME_INDEX_INVALID", lambda: source.grab_frame("VID-000001", frame_index, clip[1].source_revision), 422)


@pytest.mark.parametrize("frame_index", [0, 60, 120, 180, 239])
def test_sequential_and_repeat(source, clip, frame_index):
    capture = cv2.VideoCapture(str(clip[0]))
    try:
        for _index in range(frame_index + 1):
            success, expected = capture.read()
            assert success
    finally:
        capture.release()
    outputs = [source.grab_frame("VID-000001", frame_index, clip[1].source_revision) for _repeat in range(3)]
    assert all(np.array_equal(frame, expected) for frame, metadata in outputs)
    assert all(frame.shape == (48, 64, 3) for frame, metadata in outputs)


def test_parallel_positions_are_independent(source, clip):
    indices = [0, 239]
    with ThreadPoolExecutor(max_workers=2) as executor:
        frames = list(executor.map(lambda index: source.grab_frame("VID-000001", index, clip[1].source_revision)[0], indices))
    assert not np.array_equal(frames[0], frames[1])
    assert np.array_equal(frames[0], source.grab_frame("VID-000001", 0, clip[1].source_revision)[0])


@pytest.mark.parametrize("limits", [{"max_bytes": 1}, {"max_width": 63}, {"max_height": 47}, {"max_frames": 239}])
def test_limits(clip, limits):
    path, entry = clip
    source = VideoFileSource(path.parent, [entry], **limits)
    assert_error("VIDEO_LIMIT_EXCEEDED", lambda: source.metadata(entry.video_id), 413)


@pytest.mark.parametrize("field,value", [("fps", 0), ("fps", float("nan")), ("fps", float("inf")), ("fps", 29), ("frame_count", 239)])
def test_invalid_metadata_and_release(clip, field, value):
    released = []
    properties = {cv2.CAP_PROP_FRAME_WIDTH: 64, cv2.CAP_PROP_FRAME_HEIGHT: 48,
                  cv2.CAP_PROP_FPS: 30, cv2.CAP_PROP_FRAME_COUNT: 240}
    key = {"fps": cv2.CAP_PROP_FPS, "frame_count": cv2.CAP_PROP_FRAME_COUNT}[field]
    properties[key] = value
    capture = SimpleNamespace(isOpened=lambda: True, get=lambda prop: properties[prop], release=lambda: released.append(True))
    source = VideoFileSource(clip[0].parent, [clip[1]], capture_factory=lambda path: capture)
    assert_error("VIDEO_METADATA_INVALID", lambda: source.metadata("VID-000001"), 415)
    assert released == [True]


def test_corrupt_video(tmp_path):
    import hashlib
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"invalid-video")
    entry = VideoEntry("VID-000001", path.name, hashlib.sha256(path.read_bytes()).hexdigest(), 64, 48, 30, 240)
    source = VideoFileSource(tmp_path, [entry])
    assert_error("VIDEO_DECODE_UNAVAILABLE", lambda: source.metadata(entry.video_id), 415)


@pytest.mark.parametrize("behavior", ["eof", "exception", "wrong_shape"])
def test_decode_failure_releases_slot(source, clip, behavior):
    real_factory = source._capture_factory
    released = []

    def factory(path):
        capture = real_factory(path)
        def read():
            if behavior == "exception":
                raise RuntimeError("secret/internal/path")
            return (False, None) if behavior == "eof" else (True, np.zeros((1, 1, 3), np.uint8))
        def release():
            capture.release()
            released.append(True)
        return SimpleNamespace(isOpened=capture.isOpened, get=capture.get, read=read, release=release)

    source._capture_factory = factory
    code = {"eof": "VIDEO_FRAME_UNAVAILABLE", "exception": "VIDEO_DECODE_FAILED", "wrong_shape": "VIDEO_FRAME_INVALID"}[behavior]
    assert_error(code, lambda: source.grab_frame("VID-000001", 0, clip[1].source_revision))
    assert released == [True]
    source._capture_factory = real_factory
    assert source.metadata("VID-000001")["width"] == 64


def test_decode_capacity(source):
    assert source._slots.acquire(False)
    assert source._slots.acquire(False)
    try:
        assert_error("VIDEO_DECODER_BUSY", lambda: source.metadata("VID-000001"), 429)
    finally:
        source._slots.release()
        source._slots.release()
    assert source.metadata("VID-000001")


def test_real_parallel_limit_and_release(clip):
    entered = threading.Event()
    finish = threading.Event()
    released = []

    def factory(path):
        capture = cv2.VideoCapture(path)
        def read():
            entered.set()
            assert finish.wait(5)
            return capture.read()
        def release():
            capture.release()
            released.append(True)
        return SimpleNamespace(isOpened=capture.isOpened, get=capture.get, read=read, release=release)

    source = VideoFileSource(clip[0].parent, [clip[1]], max_decoders=1, capture_factory=factory)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(source.grab_frame, "VID-000001", 0, clip[1].source_revision)
        try:
            assert entered.wait(5)
            assert_error("VIDEO_DECODER_BUSY", lambda: source.grab_frame("VID-000001", 1, clip[1].source_revision), 429)
        finally:
            finish.set()
        assert pending.result()[0].shape == (48, 64, 3)
    assert released == [True]


def test_release_exception_is_sanitized_and_slot_returns(source):
    real_factory = source._capture_factory
    def factory(path):
        capture = real_factory(path)
        def release():
            capture.release()
            raise RuntimeError("secret C:/internal")
        return SimpleNamespace(isOpened=capture.isOpened, get=capture.get, release=release)
    source._capture_factory = factory
    assert_error("VIDEO_DECODE_FAILED", lambda: source.metadata("VID-000001"), 503)
    source._capture_factory = real_factory
    assert source.metadata("VID-000001")


@pytest.mark.parametrize("relative_path", ["../outside.mp4", "C:/outside.mp4", "clip.avi"])
def test_registry_path_escape(clip, relative_path):
    source = VideoFileSource(clip[0].parent, [replace(clip[1], relative_path=relative_path)])
    assert_error("VIDEO_FORMAT_UNSUPPORTED", lambda: source.metadata("VID-000001"))


def test_directory_junction_rejected(tmp_path):
    target = tmp_path / "outside"
    path, entry = synthetic_video(target)
    link = tmp_path / "linked"
    directory_link(link, target)
    source = VideoFileSource(link, [entry])
    assert_error("VIDEO_UNAVAILABLE", lambda: source.metadata(entry.video_id), 503)
