from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import stat
import threading

import cv2
import numpy as np


class VideoError(Exception):
    def __init__(self, status_code: int, code: str):
        self.status_code = status_code
        self.code = code
        super().__init__(code)


def reject_links(path: Path) -> None:
    for component in (path, *path.parents):
        if component.exists() or component.is_symlink():
            information = component.lstat()
            if stat.S_ISLNK(information.st_mode) or getattr(information, "st_file_attributes", 0) & 0x400:
                raise ValueError("REPARSE_PATH_REJECTED")


@dataclass(frozen=True)
class VideoEntry:
    video_id: str
    relative_path: str
    source_revision: str
    width: int
    height: int
    fps: float
    frame_count: int
    codec: str = "h264"


LEGACY_DEMO_VIDEO = VideoEntry(
    "VID-000001", "bottle_conveyor_clean_h264_1920x480_8s.mp4",
    "f1c5a12ee25672bfb8241311ecd16f7fefb7e549cb43a44a81bb4858ea9f9a2d",
    1920, 480, 30.0, 240,
)

DEMO_VIDEO = VideoEntry(
    "VID-000002", "bottle_conveyor_bright_no_lines_h264_1920x480_8s.mp4",
    "2eaee8ad99835600137ed54c1cfee25b009e22f41023fc1b41a08584ff314991",
    1920, 480, 30.0, 240,
)

MIXED_DEMO_VIDEO = VideoEntry(
    "VID-000003", "bottle_conveyor_mixed_ok_ng_16s_h264_1920x480.mp4",
    "bcdf19620579a60b4d7211f6cb7e2db948336b240b0ac78114c18bb2359ef7d5",
    1920, 480, 30.0, 480,
)


class VideoFileSource:
    def __init__(self, root: Path, entries=None, *, max_bytes=128 * 1024 * 1024,
                 max_width=1920, max_height=1080, max_frames=900, max_decoders=2,
                 capture_factory=None):
        self.root = Path(root).absolute()
        self.entries = {entry.video_id: entry for entry in (entries if entries is not None else [DEMO_VIDEO, LEGACY_DEMO_VIDEO, MIXED_DEMO_VIDEO])}
        self.max_bytes = max_bytes
        self.max_width = max_width
        self.max_height = max_height
        self.max_frames = max_frames
        self._slots = threading.BoundedSemaphore(max_decoders)
        self._capture_factory = capture_factory or cv2.VideoCapture

    def entry(self, video_id: str) -> VideoEntry:
        if video_id not in self.entries:
            raise VideoError(404, "VIDEO_NOT_FOUND")
        return self.entries[video_id]

    def verified_path(self, video_id: str) -> Path:
        entry = self.entry(video_id)
        try:
            relative = Path(entry.relative_path)
            if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".mp4":
                raise VideoError(415, "VIDEO_FORMAT_UNSUPPORTED")
            candidate = self.root / relative
            reject_links(candidate)
            root = self.root.resolve(strict=True)
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(root) or not resolved.is_file():
                raise VideoError(404, "VIDEO_NOT_AVAILABLE")
            if resolved.stat().st_size > self.max_bytes:
                raise VideoError(413, "VIDEO_LIMIT_EXCEEDED")
            with resolved.open("rb") as source:
                revision = hashlib.file_digest(source, "sha256").hexdigest()
            if revision != entry.source_revision:
                raise VideoError(409, "VIDEO_REVISION_CHANGED")
            return resolved
        except VideoError:
            raise
        except FileNotFoundError:
            raise VideoError(404, "VIDEO_NOT_AVAILABLE") from None
        except (OSError, ValueError, RuntimeError):
            raise VideoError(503, "VIDEO_UNAVAILABLE") from None

    def validate_request(self, video_id: str, revision: str, frame_index: int) -> VideoEntry:
        entry = self.entry(video_id)
        self.verified_path(video_id)
        if revision != entry.source_revision:
            raise VideoError(409, "VIDEO_REVISION_MISMATCH")
        if type(frame_index) is not int or not 0 <= frame_index < entry.frame_count:
            raise VideoError(422, "FRAME_INDEX_INVALID")
        return entry

    @contextmanager
    def _decoder(self, path: Path):
        if not self._slots.acquire(blocking=False):
            raise VideoError(429, "VIDEO_DECODER_BUSY")
        capture = None
        try:
            capture = self._capture_factory(str(path))
            if not capture.isOpened():
                raise VideoError(415, "VIDEO_DECODE_UNAVAILABLE")
            yield capture
        except VideoError:
            raise
        except Exception:
            raise VideoError(503, "VIDEO_DECODE_FAILED") from None
        finally:
            try:
                if capture is not None:
                    try:
                        capture.release()
                    except Exception:
                        raise VideoError(503, "VIDEO_DECODE_FAILED") from None
            finally:
                self._slots.release()

    def _metadata(self, entry: VideoEntry, capture) -> dict:
        values = [capture.get(prop) for prop in (
            cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT,
            cv2.CAP_PROP_FPS, cv2.CAP_PROP_FRAME_COUNT,
        )]
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise VideoError(415, "VIDEO_METADATA_INVALID")
        width, height, fps, count = values
        if width > self.max_width or height > self.max_height or count > self.max_frames:
            raise VideoError(413, "VIDEO_LIMIT_EXCEEDED")
        if (width, height, fps, count) != (entry.width, entry.height, entry.fps, entry.frame_count):
            raise VideoError(415, "VIDEO_METADATA_INVALID")
        fourcc = int(capture.get(cv2.CAP_PROP_FOURCC)).to_bytes(4, "little").decode("ascii", "replace").lower()
        permitted = {"h264": {"h264", "avc1"}, "mpeg4": {"mp4v", "fmp4"}}
        if fourcc not in permitted.get(entry.codec, set()):
            raise VideoError(415, "VIDEO_FORMAT_UNSUPPORTED")
        return {
            "video_id": entry.video_id, "source_revision": entry.source_revision,
            "width": entry.width, "height": entry.height, "fps": entry.fps,
            "frame_count": entry.frame_count, "duration_seconds": entry.frame_count / entry.fps,
            "codec": entry.codec, "stream_url": f"/videos/{entry.video_id}/stream",
            "frame_index_min": 0, "frame_index_max": entry.frame_count - 1,
        }

    def metadata(self, video_id: str) -> dict:
        entry = self.entry(video_id)
        with self._decoder(self.verified_path(video_id)) as capture:
            return self._metadata(entry, capture)

    def list_videos(self) -> list[dict]:
        return [self.metadata(video_id) for video_id in self.entries]

    def grab_frame(self, video_id: str, frame_index: int, revision: str) -> tuple[np.ndarray, dict]:
        entry = self.validate_request(video_id, revision, frame_index)
        with self._decoder(self.verified_path(video_id)) as capture:
            metadata = self._metadata(entry, capture)
            for _index in range(frame_index + 1):
                success, frame = capture.read()
                if not success:
                    raise VideoError(503, "VIDEO_FRAME_UNAVAILABLE")
                if frame.shape != (entry.height, entry.width, 3) or frame.dtype != np.uint8:
                    raise VideoError(415, "VIDEO_FRAME_INVALID")
            return frame, metadata
