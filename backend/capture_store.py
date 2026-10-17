from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import secrets
import threading
import time
import uuid

import cv2
import numpy as np

from backend.video_source import reject_links


class CaptureError(Exception):
    def __init__(self, status_code: int, code: str):
        self.status_code = status_code
        self.code = code
        super().__init__(code)


@dataclass
class _Session:
    csrf: str
    expires: float


@dataclass
class _Capture:
    owner: str
    metadata: dict
    expires: float
    size: int
    digest: str


class CaptureStore:
    cookie_name = "vision_capture_session"
    marker_name = ".visioninsight-captures"
    marker_value = "VisionInsight private captures v1\n"

    def __init__(self, root: Path, *, ttl_seconds=1800, session_seconds=3600,
                 max_bytes=256 * 1024 * 1024, max_captures=128,
                 max_per_session=32, max_sessions=256, clock=time.time):
        self.root = Path(root).absolute()
        self.ttl_seconds = ttl_seconds
        self.session_seconds = session_seconds
        self.max_bytes = max_bytes
        self.max_captures = max_captures
        self.max_per_session = max_per_session
        self.max_sessions = max_sessions
        self.clock = clock
        self._sessions = {}
        self._captures = {}
        self._initialized = False
        self._lock = threading.RLock()

    def _directory(self) -> Path:
        try:
            reject_links(self.root)
            self.root.mkdir(parents=True, exist_ok=True)
            reject_links(self.root)
            root = self.root.resolve(strict=True)
            marker = root / self.marker_name
            reject_links(marker)
            if not self._initialized:
                entries = list(root.iterdir())
                if marker.exists():
                    if marker.read_text(encoding="utf8") != self.marker_value:
                        raise ValueError("Unrecognized capture directory")
                    for path in entries:
                        reject_links(path)
                        if path.name != self.marker_name and (not path.is_file() or not re.fullmatch(r"(?:CAP-[0-9a-f]{32}\.png|TMP-[0-9a-f]{32})", path.name)):
                            raise ValueError("Unmanaged capture entry")
                    for path in entries:
                        if path.name != self.marker_name:
                            path.unlink()
                elif entries:
                    raise ValueError("Nonempty unmanaged capture directory")
                else:
                    with marker.open("x", encoding="utf8") as output:
                        output.write(self.marker_value)
                self._initialized = True
            elif not marker.is_file() or marker.read_text(encoding="utf8") != self.marker_value:
                raise ValueError("Capture ownership marker missing")
            return root
        except (OSError, ValueError, RuntimeError):
            raise CaptureError(503, "CAPTURE_STORAGE_UNAVAILABLE") from None

    def _remove(self, capture_id: str):
        root = self._directory()
        try:
            (root / f"{capture_id}.png").unlink(missing_ok=True)
        except OSError:
            raise CaptureError(503, "CAPTURE_STORAGE_UNAVAILABLE") from None
        self._captures.pop(capture_id, None)

    def cleanup(self):
        with self._lock:
            now = self.clock()
            for capture_id, record in list(self._captures.items()):
                if record.expires <= now:
                    self._remove(capture_id)
            self._sessions = {key: session for key, session in self._sessions.items() if session.expires > now}

    @staticmethod
    def _session_key(token: str) -> str:
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    def _session(self, token):
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            return None
        key = self._session_key(token)
        session = self._sessions.get(key)
        return (key, session) if session is not None else None

    def bootstrap(self, token=None) -> tuple[str, str]:
        with self._lock:
            self.cleanup()
            existing = self._session(token)
            if existing:
                return token, existing[1].csrf
            if len(self._sessions) >= self.max_sessions:
                raise CaptureError(503, "CAPTURE_SESSION_LIMIT")
            token = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            self._sessions[self._session_key(token)] = _Session(csrf, self.clock() + self.session_seconds)
            return token, csrf

    def authorize(self, token, csrf=None, *, write=False) -> str:
        with self._lock:
            self.cleanup()
            session = self._session(token)
            if session is None:
                raise CaptureError(401 if write else 404, "CAPTURE_SESSION_REQUIRED" if write else "CAPTURE_NOT_FOUND")
            if write and (not isinstance(csrf, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", csrf) or not secrets.compare_digest(csrf, session[1].csrf)):
                raise CaptureError(403, "CAPTURE_CSRF_INVALID")
            return session[0]

    def save(self, token: str, csrf: str, frame: np.ndarray, metadata: dict, frame_index: int) -> dict:
        with self._lock:
            owner = self.authorize(token, csrf, write=True)
            if len(self._captures) >= self.max_captures or sum(record.owner == owner for record in self._captures.values()) >= self.max_per_session:
                raise CaptureError(503, "CAPTURE_CAPACITY_EXCEEDED")
            root = self._directory()
            capture_id = f"CAP-{uuid.uuid4().hex}"
            final = root / f"{capture_id}.png"
            temporary = root / f"TMP-{uuid.uuid4().hex}"
            if final.exists():
                raise CaptureError(503, "CAPTURE_STORAGE_UNAVAILABLE")
            now = self.clock()
            expires = now + self.ttl_seconds
            result = {
                "capture_id": capture_id, "video_id": metadata["video_id"],
                "frame_index": frame_index, "source_revision": metadata["source_revision"],
                "frame_timestamp_ms": frame_index / metadata["fps"] * 1000,
                "timestamp_basis": "CFR_FRAME_INDEX", "pts_ms": None,
                "width": metadata["width"], "height": metadata["height"],
                "image_url": f"/captures/{capture_id}/image",
                "created_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat(),
                "status": "CAPTURED",
            }
            try:
                success, encoded = cv2.imencode(".png", frame)
                if not success:
                    raise ValueError("PNG encoding failed")
                payload = encoded.tobytes()
                if len(payload) + sum(record.size for record in self._captures.values()) > self.max_bytes:
                    raise CaptureError(503, "CAPTURE_CAPACITY_EXCEEDED")
                with temporary.open("xb") as output:
                    output.write(payload)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, final)
                self._captures[capture_id] = _Capture(owner, result, expires, len(payload), hashlib.sha256(payload).hexdigest())
                return result.copy()
            except CaptureError:
                raise
            except (OSError, ValueError, cv2.error):
                raise CaptureError(503, "CAPTURE_STORAGE_UNAVAILABLE") from None
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                    if capture_id not in self._captures:
                        final.unlink(missing_ok=True)
                except OSError:
                    raise CaptureError(503, "CAPTURE_STORAGE_UNAVAILABLE") from None

    def _get(self, token, capture_id: str) -> _Capture:
        owner = self.authorize(token)
        if not re.fullmatch(r"CAP-[0-9a-f]{32}", capture_id):
            raise CaptureError(404, "CAPTURE_NOT_FOUND")
        record = self._captures.get(capture_id)
        if record is None or record.owner != owner:
            raise CaptureError(404, "CAPTURE_NOT_FOUND")
        try:
            path = self._directory() / f"{capture_id}.png"
            reject_links(path)
            if not path.is_file() or path.stat().st_size != record.size:
                raise ValueError("Capture missing or changed")
        except (OSError, ValueError):
            raise CaptureError(404, "CAPTURE_NOT_FOUND") from None
        return record

    def metadata(self, token, capture_id: str) -> dict:
        with self._lock:
            return self._get(token, capture_id).metadata.copy()

    def image(self, token, capture_id: str) -> bytes:
        with self._lock:
            record = self._get(token, capture_id)
            try:
                payload = (self._directory() / f"{capture_id}.png").read_bytes()
                if hashlib.sha256(payload).hexdigest() != record.digest:
                    raise ValueError("Capture changed")
                return payload
            except (OSError, ValueError):
                raise CaptureError(404, "CAPTURE_NOT_FOUND") from None

    def close(self):
        with self._lock:
            for capture_id in list(self._captures):
                self._remove(capture_id)
            self._sessions.clear()
