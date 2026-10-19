"""Read-only registered-video tests; no Grab POST, inspection, model or provider calls."""

import hashlib

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
import pytest

from backend.config import PROJECT_ROOT, Settings
from backend.video_api import VideoRuntime, get_video_runtime, router
from backend.video_source import DEMO_VIDEO, LEGACY_DEMO_VIDEO, MIXED_DEMO_VIDEO, VideoError, VideoFileSource


@pytest.fixture
def source():
    directory = PROJECT_ROOT / "data/outputs/videos"
    entries = (DEMO_VIDEO, LEGACY_DEMO_VIDEO, MIXED_DEMO_VIDEO)
    before = {entry.relative_path: hashlib.sha256((directory / entry.relative_path).read_bytes()).hexdigest() for entry in entries}
    yield VideoFileSource(directory)
    assert before == {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in before}


def test_new_video_has_unique_id_and_preserves_both_existing_entries_and_default(source):
    assert list(source.entries) == ["VID-000002", "VID-000001", "VID-000003"]
    assert source.entry("VID-000001") is LEGACY_DEMO_VIDEO
    assert source.entry("VID-000002") is DEMO_VIDEO
    assert source.entry("VID-000003") is MIXED_DEMO_VIDEO
    assert len({entry.relative_path for entry in source.entries.values()}) == 3


@pytest.mark.parametrize("identifier,count,duration", [("VID-000001", 240, 8), ("VID-000002", 240, 8), ("VID-000003", 480, 16)])
def test_existing_file_metadata_and_fingerprint_are_verified_without_reencoding(source, identifier, count, duration):
    metadata = source.metadata(identifier)
    assert metadata["frame_count"] == count and metadata["duration_seconds"] == duration
    assert (metadata["width"], metadata["height"], metadata["fps"], metadata["codec"]) == (1920, 480, 30, "h264")
    assert metadata["source_revision"] == source.entry(identifier).source_revision
    assert metadata["stream_url"] == f"/videos/{identifier}/stream"


def test_list_detail_and_range_stream_use_same_registered_file_without_capture_creation(source, tmp_path):
    settings = Settings(_env_file=None, GEMINI_API_KEY=None, ENABLE_PATCHCORE=False,
                        VIDEO_ROOT=str(source.root), CAPTURE_DIR=str(tmp_path / "captures"))
    runtime = VideoRuntime(settings)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_video_runtime] = lambda: runtime
    try:
        with TestClient(app) as client:
            response = client.get("/videos")
            assert response.status_code == 200
            videos = response.json()["videos"]
            assert [item["video_id"] for item in videos] == list(source.entries)
            mixed = next(item for item in videos if item["video_id"] == "VID-000003")
            assert mixed["frame_index_max"] == 479 and mixed["duration_seconds"] == 16
            assert client.get("/videos/VID-000003").json() == mixed
            stream = client.get(mixed["stream_url"], headers={"Range": "bytes=0-31"})
            assert stream.status_code == 206 and stream.headers["content-type"] == "video/mp4"
            assert stream.headers["etag"] == f'"{MIXED_DEMO_VIDEO.source_revision}"'
            assert stream.content == source.verified_path("VID-000003").read_bytes()[:32]
            assert not runtime.captures._captures
    finally:
        runtime.captures.close()


def test_last_frame_and_original_coordinate_roi_are_readable_without_a_grab_api_request(source):
    first, _ = source.grab_frame("VID-000003", 0, MIXED_DEMO_VIDEO.source_revision)
    last, metadata = source.grab_frame("VID-000003", 479, MIXED_DEMO_VIDEO.source_revision)
    assert first.shape == last.shape == (480, 1920, 3)
    assert not np.array_equal(first, last)
    assert last[110:410, 810:1110].shape == (300, 300, 3)
    assert metadata["frame_index_max"] == 479
    with pytest.raises(VideoError) as failure:
        source.validate_request("VID-000003", MIXED_DEMO_VIDEO.source_revision, 480)
    assert failure.value.code == "FRAME_INDEX_INVALID"
