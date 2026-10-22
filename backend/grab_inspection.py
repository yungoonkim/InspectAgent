"""Session-owned manual crops adapted to the existing inspection workflow."""

import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import threading
from uuid import uuid4

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from backend.capture_store import CaptureError
from backend.inspection import ImageRegistry, execute_inspection_workflow
from backend.video_source import reject_links
from backend.anomaly_map_store import get_anomaly_map_metadata
from backend.reinspection_store import ReinspectionStore, completed
from backend.quality_shadow_metrics import SourceIdentity
from backend.quality_shadow_worker import ShadowJob, report_shadow_failure


LIMITATION = "LiveView Grab 기반 검사는 기존 PatchCore 모델을 이용한 실험적 검사입니다. 영상 Crop에 대한 임계값 보정 및 검출 성능은 별도로 검증되지 않았습니다."


class GrabInspectionError(Exception):
    def __init__(self, status_code, code):
        self.status_code = status_code
        self.code = code
        super().__init__(code)


class GrabRoi(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: StrictInt = Field(ge=0, le=4096)
    y: StrictInt = Field(ge=0, le=4096)
    width: StrictInt = Field(ge=16, le=1920)
    height: StrictInt = Field(ge=16, le=1080)


class GrabInspectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: StrictStr = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    source_revision: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    roi: GrabRoi
    group_id: StrictStr | None = Field(default=None, pattern=r"^RIG-[0-9a-f]{32}$")
    parent_inspection_id: StrictStr | None = Field(default=None, pattern=r"^INSP-[0-9]+$")
    expected_version: StrictInt | None = Field(default=None, ge=0)
    same_product_confirmed: StrictBool = False
    request_id: StrictStr | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


class ProvenanceStorage:
    def __init__(self, storage, provenance):
        self.storage = storage
        self.provenance = provenance

    def save_inspection(self, record):
        metadata = get_anomaly_map_metadata(record.inspection_id)
        available = bool(metadata and metadata["image_id"] == record.image_id
                         and metadata["original_image_width"] == self.provenance["crop_width"]
                         and metadata["original_image_height"] == self.provenance["crop_height"])
        record.metrics = {**record.metrics, "input_source": "LIVEVIEW_GRAB", "input_provenance": self.provenance,
                          "anomaly_map_available": available}
        if "reinspection" in self.provenance:
            link = self.provenance["reinspection"]
            record.metrics["reinspection"] = {**link,
                "attempt_number": link["attempt_number"] if completed(record) else None}
        return self.storage.save_inspection(record)

    def save_logs(self, logs):
        return self.storage.save_logs(logs)


def verify_spatial_contract(inferencer):
    if str(getattr(inferencer, "device", "cpu")) != "cpu":
        raise GrabInspectionError(503, "GRAB_CPU_REQUIRED")
    if not hasattr(inferencer, "model"):
        return
    allowed = {"Compose", "Sequential", "ModuleList", "Resize", "ToImage", "ToDtype", "Normalize", "ConvertImageDtype", "Identity"}
    def check(transform):
        if transform is None or type(transform).__name__ not in allowed:
            raise GrabInspectionError(503, "GRAB_SPATIAL_TRANSFORM_UNVERIFIED")
        if type(transform).__name__ == "Resize" and tuple(transform.size) != (256, 256):
            raise GrabInspectionError(503, "GRAB_SPATIAL_TRANSFORM_UNVERIFIED")
        for child in getattr(transform, "transforms", ()):
            check(child)
        if type(transform).__name__ in {"Sequential", "ModuleList"}:
            for child in transform:
                check(child)
    check(inferencer.transform)
    check(getattr(getattr(inferencer.model, "pre_processor", None), "export_transform", None))


class CheckedPredictor:
    def __init__(self, inferencer):
        self.inferencer = inferencer

    def predict(self, image):
        prediction = self.inferencer.predict(image)
        signal = prediction.get("anomaly_map")
        if (not math.isfinite(float(prediction["anomaly_score"]))
                or not isinstance(signal, np.ndarray) or signal.shape != (256, 256)
                or signal.dtype.kind not in "fiu" or not np.isfinite(signal).all()):
            raise ValueError("Invalid Grab model output")
        return prediction


class GrabInspectionRuntime:
    def __init__(self, root, *, max_inputs=128, max_bytes=256 * 1024 * 1024, shadow_worker=None):
        self.root = Path(root).absolute()
        self.max_inputs = max_inputs
        self.max_bytes = max_bytes
        self._lock = threading.Lock()
        self._attempts = {}
        self.reinspections = ReinspectionStore(self.root.parent / "reinspection_history")
        self.shadow_worker = shadow_worker

    def _path(self, image_id, suffix):
        if re.fullmatch(r"IMG-GRAB-[0-9a-f]{32}", image_id or "") is None:
            raise GrabInspectionError(404, "GRAB_INPUT_NOT_FOUND")
        try:
            reject_links(self.root)
            target = self.root / f"{image_id}{suffix}"
            reject_links(target)
            if target.resolve().parent != self.root.resolve():
                raise ValueError("Invalid input path")
            return target
        except (OSError, ValueError, RuntimeError):
            raise GrabInspectionError(503, "GRAB_INPUT_STORAGE_UNAVAILABLE") from None

    def authorize_record(self, record, owner):
        if record is None or record.metrics.get("input_source") != "LIVEVIEW_GRAB":
            raise GrabInspectionError(404, "GRAB_INPUT_NOT_FOUND")
        try:
            metadata = json.loads(self._path(record.image_id, ".json").read_text(encoding="utf-8"))
            if not secrets.compare_digest(metadata["owner"], owner):
                raise ValueError("Different owner")
            payload = self._path(record.image_id, ".png").read_bytes()
            if (metadata["image_id"] != record.image_id
                    or hashlib.sha256(payload).hexdigest() != record.metrics["input_provenance"]["crop_sha256"]
                    or metadata["crop_sha256"] != record.metrics["input_provenance"]["crop_sha256"]):
                raise ValueError("Changed crop")
            return payload
        except (OSError, ValueError, KeyError, TypeError):
            raise GrabInspectionError(404, "GRAB_INPUT_NOT_FOUND") from None

    def inspect(self, captures, token, csrf, capture_id, payload, storage, inferencer_factory, settings):
        owner = captures.authorize(token, csrf, write=True)
        metadata = captures.metadata(token, capture_id)
        if metadata["source_revision"] != payload.source_revision:
            raise GrabInspectionError(409, "SOURCE_REVISION_MISMATCH")
        metadata = {**metadata, "capture_sha256": hashlib.sha256(captures.image(token, capture_id)).hexdigest()}
        created = False
        def operation(context):
            nonlocal created
            record = self._inspect(captures, token, csrf, capture_id, payload, storage, inferencer_factory, settings, context)
            created = True
            return record
        record = self.reinspections.execute(owner, capture_id, payload, metadata, storage, operation,
            judge_assisted=getattr(settings, "JUDGE_ASSISTED_WORKFLOW_ENABLED", False) is True)
        if created and completed(record) and getattr(settings, "QUALITY_SHADOW_ENABLED", False) and self.shadow_worker is not None:
            try:
                frozen_record = record.model_copy(deep=True)
                provenance = frozen_record.metrics["input_provenance"]
                source = SourceIdentity(inspection_id=record.inspection_id, image_id=record.image_id,
                    crop_sha256=provenance["crop_sha256"], width=provenance["crop_width"], height=provenance["crop_height"])
                self.shadow_worker.submit(ShadowJob(source, lambda: self.authorize_record(frozen_record, owner)))
            except Exception:
                report_shadow_failure("QUALITY_SHADOW_ENQUEUE_FAILED")
        return record

    def _inspect(self, captures, token, csrf, capture_id, payload, storage, inferencer_factory, settings, context):
        owner = captures.authorize(token, csrf, write=True)
        metadata = captures.metadata(token, capture_id)
        if metadata["source_revision"] != payload.source_revision:
            raise GrabInspectionError(409, "SOURCE_REVISION_MISMATCH")
        raw = captures.image(token, capture_id)
        if raw[:8] != b"\x89PNG\r\n\x1a\n":
            raise GrabInspectionError(415, "GRAB_PNG_REQUIRED")
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if (frame is None or frame.dtype != np.uint8 or frame.shape != (metadata["height"], metadata["width"], 3)
                or metadata["width"] > 1920 or metadata["height"] > 1080):
            raise GrabInspectionError(422, "GRAB_IMAGE_INVALID")
        roi = payload.roi
        if roi.x + roi.width > metadata["width"] or roi.y + roi.height > metadata["height"]:
            raise GrabInspectionError(422, "GRAB_ROI_OUT_OF_BOUNDS")
        key = (owner, capture_id, payload.model_dump_json())
        if not self._lock.acquire(blocking=False):
            raise GrabInspectionError(409, "GRAB_INSPECTION_BUSY")
        try:
            if key in self._attempts:
                record = self._attempts[key]
                if record is None:
                    raise GrabInspectionError(409, "GRAB_INSPECTION_ALREADY_ATTEMPTED")
                return record
            if len(self._attempts) >= self.max_inputs:
                raise GrabInspectionError(503, "GRAB_INPUT_CAPACITY_EXCEEDED")
            inferencer = inferencer_factory()
            if inferencer is None:
                raise GrabInspectionError(503, "GRAB_MODEL_UNAVAILABLE")
            verify_spatial_contract(inferencer)
            crop = frame[roi.y:roi.y + roi.height, roi.x:roi.x + roi.width].copy()
            success, encoded = cv2.imencode(".png", crop)
            if not success:
                raise GrabInspectionError(503, "GRAB_INPUT_STORAGE_UNAVAILABLE")
            encoded = encoded.tobytes()
            image_id = f"IMG-GRAB-{uuid4().hex}"
            target = self._path(image_id, ".png")
            manifest = self._path(image_id, ".json")
            created_png = False
            created_manifest = False
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                reject_links(self.root)
                existing = list(self.root.glob("IMG-GRAB-*.png"))
                if len(existing) >= self.max_inputs or sum(path.stat().st_size for path in existing) + len(encoded) > self.max_bytes:
                    raise GrabInspectionError(503, "GRAB_INPUT_CAPACITY_EXCEEDED")
                with target.open("xb") as output:
                    created_png = True
                    output.write(encoded)
                    output.flush()
                    os.fsync(output.fileno())
                with manifest.open("x", encoding="utf-8") as output:
                    created_manifest = True
                    json.dump({"image_id": image_id, "owner": owner, "crop_sha256": hashlib.sha256(encoded).hexdigest()}, output)
            except GrabInspectionError:
                raise
            except OSError:
                if created_manifest:
                    manifest.unlink(missing_ok=True)
                if created_png:
                    target.unlink(missing_ok=True)
                raise GrabInspectionError(503, "GRAB_INPUT_STORAGE_UNAVAILABLE") from None
            provenance = {
                "capture_id": capture_id, "video_id": metadata["video_id"], "frame_index": metadata["frame_index"],
                "source_revision": metadata["source_revision"], "frame_timestamp_ms": metadata["frame_timestamp_ms"],
                "source_width": metadata["width"], "source_height": metadata["height"], "roi": roi.model_dump(),
                "crop_width": roi.width, "crop_height": roi.height, "crop_sha256": hashlib.sha256(encoded).hexdigest(),
                "capture_sha256": hashlib.sha256(raw).hexdigest(), "model_input_resolution": [256, 256],
                "preprocessing": "EXISTING_BGR_TO_RGB_RESIZE_256_IMAGENET_EXTERNAL_AND_INTERNAL_NORMALIZE_UNRESOLVED",
                "coordinate_system": "ORIGINAL_FRAME_PIXELS_HALF_OPEN", "limitation": LIMITATION,
            }
            registry = ImageRegistry()
            registry.register_image(image_id, target)
            self._attempts[key] = None
            provenance["reinspection"] = {key: value for key, value in context.items() if key != "started"}
            context["started"] = True
            record, logs = execute_inspection_workflow(
                payload.product_id, image_id, registry=registry, storage=ProvenanceStorage(storage, provenance),
                low_threshold=settings.BRIGHTNESS_LOW_THRESHOLD, high_threshold=settings.BRIGHTNESS_HIGH_THRESHOLD,
                inferencer=CheckedPredictor(inferencer), decision_threshold=settings.DECISION_THRESHOLD,
                capture_anomaly_map=True,
            )
            self._attempts[key] = record
            return record
        finally:
            self._lock.release()


_runtime_lock = threading.Lock()


def get_grab_runtime(request, settings):
    with _runtime_lock:
        if not hasattr(request.app.state, "grab_inspection_runtime"):
            root = Path(settings.absolute_output_path) / "grab_inspection_inputs"
            request.app.state.grab_inspection_runtime = GrabInspectionRuntime(root,
                shadow_worker=getattr(request.app.state, "quality_shadow_worker", None))
        return request.app.state.grab_inspection_runtime


def require_grab_owner(request, record):
    if record is not None and record.metrics.get("input_source") == "LIVEVIEW_GRAB":
        from backend.video_api import get_video_runtime
        runtime = get_video_runtime(request)
        owner = runtime.captures.authorize(request.cookies.get(runtime.captures.cookie_name))
        get_grab_runtime(request, runtime.settings).authorize_record(record, owner)
