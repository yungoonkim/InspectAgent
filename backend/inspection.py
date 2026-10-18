"""Inspection domain service for VisionInsight.

Implements inspection ID generation, neutral image registry mapping,
and execution decoupled from ground truth or defect classifications.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Tuple
import logging
import cv2
import numpy as np

from backend.config import Settings, get_settings
from backend.vision import analyze_image
from backend.storage import (
    EventCode,
    InspectionLogRecord,
    InspectionRecord,
    InspectionStage,
    InspectionStorageBase,
    LogLevel,
    get_inspection_storage,
    get_utc_now_iso,
)
from backend.decision import FinalReasonCode, FinalResult, determine_final_verdict
from backend.anomaly_map_store import save_anomaly_map_artifact

logger = logging.getLogger("vision_insight.inspection")


class InspectionIdGenerator:
    """Thread-safe sequential inspection ID generator.

    Generates non-colliding IDs in format: INSP-000001, INSP-000002, etc.
    """

    def __init__(self, start_idx: int = 1):
        self._lock = threading.Lock()
        self._counter = start_idx

    def next_id(self) -> str:
        """Generate the next unique inspection ID."""
        with self._lock:
            current = self._counter
            self._counter += 1
            return f"INSP-{current:06d}"

    def reset(self, start_idx: int = 1) -> None:
        """Reset counter (useful for test isolation)."""
        with self._lock:
            self._counter = start_idx

    def sync_with_storage(self, file_path: Path) -> None:
        """Sync counter with highest existing INSP-XXXXXX to prevent duplicate IDs across restarts."""
        if not file_path.exists():
            return
        import re
        pattern = re.compile(r"INSP-(\d+)")
        max_idx = 0
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    match = pattern.search(line)
                    if match:
                        val = int(match.group(1))
                        if val > max_idx:
                            max_idx = val
        except Exception:
            pass
        with self._lock:
            if max_idx >= self._counter:
                self._counter = max_idx + 1



class ImageRegistry:
    """Server-side registry that maps neutral image IDs to internal dataset file paths.

    CRITICAL SAFETY RULE:
    Ground truth directories ('broken_large', 'contamination', etc.) are masked internally
    so that Agent tools and external clients only interact with neutral IDs (e.g. IMG-BOTTLE-0001).
    """

    def __init__(
        self,
        dataset_root: Optional[Path] = None,
        injected_root: Optional[Path] = None,
        allow_test_stubs: bool = False,
    ):
        self._mapping: Dict[str, Path] = {}
        self._lock = threading.Lock()
        self._dataset_root = dataset_root
        self._injected_root = injected_root
        self._allow_test_stubs = allow_test_stubs
        if dataset_root is not None:
            self.refresh(dataset_root, injected_root=injected_root, allow_test_stubs=allow_test_stubs)

    def refresh(
        self,
        dataset_root: Path,
        injected_root: Optional[Path] = None,
        allow_test_stubs: Optional[bool] = None,
    ) -> None:
        """Scan dataset root and optional injected images directory to build deterministic neutral ID mappings."""
        with self._lock:
            self._mapping.clear()
            self._dataset_root = dataset_root
            self._injected_root = injected_root
            if allow_test_stubs is not None:
                self._allow_test_stubs = allow_test_stubs

            if not dataset_root.exists() or not dataset_root.is_dir():
                return

            # Discover all PNG images deterministically across dataset subdirectories
            # Sorting ensures reproducible ID-to-image assignment
            discovered_paths: List[Path] = []
            for path in sorted(dataset_root.glob("**/*.png")):
                # Ensure ground_truth directory is strictly excluded if present
                if "ground_truth" not in path.parts:
                    discovered_paths.append(path)

            for idx, img_path in enumerate(discovered_paths, start=1):
                image_id = f"IMG-BOTTLE-{idx:04d}"
                self._mapping[image_id] = img_path.resolve()

            # Scan test injected directory if configured and exists
            if injected_root is not None and injected_root.exists() and injected_root.is_dir():
                injected_paths = sorted([
                    p for p in injected_root.glob("**/*.png")
                    if p.is_file()
                ])
                for idx, inj_path in enumerate(injected_paths, start=1):
                    # If filename starts with IMG-BOTTLE-INJ-, preserve exact neutral stem, else format
                    stem = inj_path.stem.upper()
                    if stem.startswith("IMG-BOTTLE-INJ-"):
                        inj_id = stem
                    else:
                        inj_id = f"IMG-BOTTLE-INJ-{idx:04d}"
                    self._mapping[inj_id] = inj_path.resolve()

            # In approved non-production environments, register neutral test stub for T05 load failure
            if self._allow_test_stubs and dataset_root is not None:
                test_missing_path = (dataset_root.parent / "test_data" / "injected_images" / "nonexistent_sample.png").resolve()
                self._mapping["IMG-BOTTLE-NONEXISTENT"] = test_missing_path

    def register_image(self, image_id: str, path: Path) -> None:
        """Register a specific neutral image_id mapped to a server-side path."""
        with self._lock:
            self._mapping[image_id] = path.resolve()

    def get_path(self, image_id: str) -> Optional[Path]:
        """Resolve a neutral image_id to its absolute server-side filesystem path."""
        with self._lock:
            return self._mapping.get(image_id)

    def list_image_ids(self) -> List[str]:
        """Return list of all registered neutral image IDs without leaking file paths."""
        with self._lock:
            return list(self._mapping.keys())

    def contains(self, image_id: str) -> bool:
        """Check if an image_id is registered."""
        with self._lock:
            return image_id in self._mapping


# Singleton instances for application lifecycle
_id_generator = InspectionIdGenerator()
_image_registry: Optional[ImageRegistry] = None


def get_inspection_id_generator(settings: Optional[Settings] = None) -> InspectionIdGenerator:
    """Retrieve or initialize the singleton inspection ID generator synced with storage."""
    global _id_generator
    curr_settings = settings or get_settings()
    _id_generator.sync_with_storage(curr_settings.absolute_inspections_path)
    return _id_generator


def get_image_registry(settings: Optional[Settings] = None) -> ImageRegistry:
    """Retrieve or initialize the singleton image registry."""
    global _image_registry
    if _image_registry is None:
        curr_settings = settings or get_settings()
        injected_dir = curr_settings.absolute_injected_images_path
        allow_stubs = (curr_settings.ENVIRONMENT != "production")
        _image_registry = ImageRegistry(
            dataset_root=curr_settings.absolute_dataset_path,
            injected_root=injected_dir,
            allow_test_stubs=allow_stubs,
        )
    return _image_registry



def execute_inspection(
    product_id: str,
    image_id: str,
    registry: Optional[ImageRegistry] = None,
    id_gen: Optional[InspectionIdGenerator] = None,
) -> Dict[str, Any]:
    """Execute Day 1 inspection workflow.

    1. Validates that image_id exists in server-side registry.
    2. Loads the image securely using OpenCV.
    3. Allocates a unique non-colliding inspection_id.
    4. Sets result='UNKNOWN' since a defect classifier is not yet integrated.
    5. Returns structured inspection details with KST (+09:00) ISO 8601 timestamp.

    Raises:
        KeyError: If image_id is not found in server registry.
        FileNotFoundError: If the mapped image file does not exist on disk.
        ValueError: If OpenCV fails to decode the image.
    """
    reg = registry or get_image_registry()
    generator = id_gen or _id_generator

    # 1. Resolve image path from neutral ID (Prevents arbitrary path traversal)
    image_path = reg.get_path(image_id)
    if image_path is None:
        raise KeyError(f"Image ID '{image_id}' is not registered or allowed by server.")

    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"Underlying image file for '{image_id}' not found on server.")

    # 2. Secure OpenCV image loading
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Failed to decode image file for '{image_id}'.")

    # 3. Generate non-colliding unique inspection ID
    inspection_id = generator.next_id()

    # 4. Determine dimensions and metadata
    height = int(image.shape[0])
    width = int(image.shape[1])
    channels = int(image.shape[2]) if len(image.shape) > 2 else 1

    # 5. Timestamp in KST (UTC+09:00)
    kst = timezone(timedelta(hours=9))
    timestamp = datetime.now(kst).isoformat()

    return {
        "inspection_id": inspection_id,
        "product_id": product_id,
        "image_id": image_id,
        "status": "COMPLETED",
        "result": "UNKNOWN",  # Fixed to UNKNOWN for Day 1 as classifier is pending
        "timestamp": timestamp,
        "image_metadata": {
            "filename": image_path.name,
            "width": width,
            "height": height,
            "channels": channels,
        },
    }


def _sanitize_error_message(err: Exception) -> str:
    """Sanitize error messages to prevent leaking server internal paths or ground truth details.

    Converts raw exceptions containing file system paths or internal dataset directories
    into neutral, safe error descriptions.
    """
    raw_msg = str(err)
    sensitive_markers = [":\\", ":/", "/dataset", "\\dataset", "ground_truth", "broken_large", "broken_small", "contamination"]
    if any(marker in raw_msg.lower() for marker in sensitive_markers):
        return f"{type(err).__name__}: An internal error occurred during ML inference processing."
    return f"{type(err).__name__}: {raw_msg}"


def execute_inspection_workflow(
    product_id: str,
    image_id: str,
    registry: Optional[ImageRegistry] = None,
    id_gen: Optional[InspectionIdGenerator] = None,
    storage: Optional[InspectionStorageBase] = None,
    low_threshold: Optional[float] = None,
    high_threshold: Optional[float] = None,
    inferencer: Optional[Any] = None,
    decision_threshold: Optional[float] = None,
    capture_anomaly_map: bool = False,
) -> Tuple[InspectionRecord, List[InspectionLogRecord]]:
    """Execute Day 2 inspection workflow with end-to-end JSONL logging and record persistence.

    Lifecycle Steps:
    1. Generate a collision-free inspection ID.
    2. Log INSPECTION_STARTED event.
    3. Resolve neutral image_id to disk path and decode with OpenCV.
       - On failure: log IMAGE_LOAD_FAILED and INSPECTION_FAILED, persist failed record, and re-raise.
       - On success: log IMAGE_LOADED event with dimensions and metadata.
    4. Execute OpenCV brightness and size analysis.
       - Log ANALYSIS_COMPLETED event with brightness metrics.
    5. Evaluate quality status (NORMAL / WARNING_LOW_BRIGHTNESS / WARNING_HIGH_BRIGHTNESS).
       - Product defect result remains strictly UNKNOWN.
    6. Log INSPECTION_COMPLETED event.
    7. Persist InspectionRecord and all event logs to respective JSONL stores.

    Guarantees:
    - Events that did not occur are never logged.
    - Records and logs are linked by identical inspection_id.
    """
    reg = registry or get_image_registry()
    generator = id_gen or get_inspection_id_generator()
    store = storage or get_inspection_storage()

    # 1. Allocate unique inspection ID
    inspection_id = generator.next_id()
    collected_logs: List[InspectionLogRecord] = []

    # 2. Stage: INIT -> INSPECTION_STARTED
    start_log = InspectionLogRecord(
        timestamp=get_utc_now_iso(),
        inspection_id=inspection_id,
        level=LogLevel.INFO,
        stage=InspectionStage.INIT,
        event_code=EventCode.INSPECTION_STARTED,
        message=f"Inspection initiated for product {product_id} with image_id {image_id}",
        source="inspection",
    )
    collected_logs.append(start_log)

    # 3. Stage: LOAD -> Resolve and decode image
    image_path = reg.get_path(image_id)
    if image_path is None:
        err_msg = f"Image ID '{image_id}' is not registered or allowed by server."
        fail_load_log = InspectionLogRecord(
            timestamp=get_utc_now_iso(),
            inspection_id=inspection_id,
            level=LogLevel.ERROR,
            stage=InspectionStage.LOAD,
            event_code=EventCode.IMAGE_LOAD_FAILED,
            message=err_msg,
            source="vision",
        )
        collected_logs.append(fail_load_log)

        fail_insp_log = InspectionLogRecord(
            timestamp=get_utc_now_iso(),
            inspection_id=inspection_id,
            level=LogLevel.ERROR,
            stage=InspectionStage.COMPLETE,
            event_code=EventCode.INSPECTION_FAILED,
            message="Inspection aborted due to unregistered image_id",
            source="inspection",
        )
        collected_logs.append(fail_insp_log)

        failed_record = InspectionRecord(
            inspection_id=inspection_id,
            product_id=product_id,
            timestamp=get_utc_now_iso(),
            image_id=image_id,
            result="UNKNOWN",
            image_quality_status="ERROR",
            metrics={"error": err_msg},
            status="FAILED",
            defect_detection_status="SKIPPED",
            final_result=FinalResult.ERROR,
            final_reason_code=FinalReasonCode.INSPECTION_FAILED,
        )
        store.save_inspection(failed_record)
        store.save_logs(collected_logs)
        raise KeyError(err_msg)

    if not image_path.exists() or not image_path.is_file():
        err_msg = f"Underlying image file for '{image_id}' not found on server."
        fail_load_log = InspectionLogRecord(
            timestamp=get_utc_now_iso(),
            inspection_id=inspection_id,
            level=LogLevel.ERROR,
            stage=InspectionStage.LOAD,
            event_code=EventCode.IMAGE_LOAD_FAILED,
            message=err_msg,
            source="vision",
        )
        collected_logs.append(fail_load_log)

        fail_insp_log = InspectionLogRecord(
            timestamp=get_utc_now_iso(),
            inspection_id=inspection_id,
            level=LogLevel.ERROR,
            stage=InspectionStage.COMPLETE,
            event_code=EventCode.INSPECTION_FAILED,
            message="Inspection aborted due to missing image file on server",
            source="inspection",
        )
        collected_logs.append(fail_insp_log)

        failed_record = InspectionRecord(
            inspection_id=inspection_id,
            product_id=product_id,
            timestamp=get_utc_now_iso(),
            image_id=image_id,
            result="UNKNOWN",
            image_quality_status="ERROR",
            metrics={"error": err_msg},
            status="FAILED",
            defect_detection_status="SKIPPED",
            final_result=FinalResult.ERROR,
            final_reason_code=FinalReasonCode.INSPECTION_FAILED,
        )
        store.save_inspection(failed_record)
        store.save_logs(collected_logs)
        raise FileNotFoundError(err_msg)

    image = cv2.imread(str(image_path))
    if image is None:
        err_msg = f"Failed to decode image file with OpenCV for image_id '{image_id}'"
        fail_decode_log = InspectionLogRecord(
            timestamp=get_utc_now_iso(),
            inspection_id=inspection_id,
            level=LogLevel.ERROR,
            stage=InspectionStage.LOAD,
            event_code=EventCode.IMAGE_LOAD_FAILED,
            message=err_msg,
            source="vision",
        )
        collected_logs.append(fail_decode_log)

        fail_insp_log = InspectionLogRecord(
            timestamp=get_utc_now_iso(),
            inspection_id=inspection_id,
            level=LogLevel.ERROR,
            stage=InspectionStage.COMPLETE,
            event_code=EventCode.INSPECTION_FAILED,
            message="Inspection aborted due to image decode failure",
            source="inspection",
        )
        collected_logs.append(fail_insp_log)

        failed_record = InspectionRecord(
            inspection_id=inspection_id,
            product_id=product_id,
            timestamp=get_utc_now_iso(),
            image_id=image_id,
            result="UNKNOWN",
            image_quality_status="ERROR",
            metrics={"error": err_msg},
            status="FAILED",
            defect_detection_status="SKIPPED",
            final_result=FinalResult.ERROR,
            final_reason_code=FinalReasonCode.INSPECTION_FAILED,
        )
        store.save_inspection(failed_record)
        store.save_logs(collected_logs)
        raise ValueError(err_msg)

    # Image load success
    height = int(image.shape[0])
    width = int(image.shape[1])
    channels = int(image.shape[2]) if len(image.shape) > 2 else 1
    load_success_log = InspectionLogRecord(
        timestamp=get_utc_now_iso(),
        inspection_id=inspection_id,
        level=LogLevel.INFO,
        stage=InspectionStage.LOAD,
        event_code=EventCode.IMAGE_LOADED,
        message=f"Image loaded successfully ({width}x{height}, {channels} channels)",
        metrics={"width": width, "height": height, "channels": channels, "image_id": image_id},
        source="vision",
    )
    collected_logs.append(load_success_log)

    # 4. Stage: ANALYZE -> Execute vision quality analysis
    analysis = analyze_image(
        image=image,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        filename=f"{image_id}.png",
    )

    quality_eval = analysis["quality_evaluation"]
    quality_status = quality_eval["quality_status"]
    is_warning = quality_eval["warning_triggered"]
    brightness_metrics = analysis["brightness_metrics"]

    # Analysis completed event
    analysis_log = InspectionLogRecord(
        timestamp=get_utc_now_iso(),
        inspection_id=inspection_id,
        level=LogLevel.WARN if is_warning else LogLevel.INFO,
        stage=InspectionStage.ANALYZE,
        event_code=EventCode.ANALYSIS_COMPLETED,
        message=quality_eval["description"],
        metrics=brightness_metrics,
        source="vision",
    )
    collected_logs.append(analysis_log)

    # 5. Stage: INFERENCE -> Execute PatchCore anomaly detection if inferencer is active
    anomaly_score: Optional[float] = None
    inference_time_ms: Optional[float] = None
    model_version: Optional[str] = None
    defect_detection_status: str = "SKIPPED"
    inference_error_msg: Optional[str] = None

    if inferencer is not None:
        infer_start_log = InspectionLogRecord(
            timestamp=get_utc_now_iso(),
            inspection_id=inspection_id,
            level=LogLevel.INFO,
            stage=InspectionStage.INFERENCE,
            event_code=EventCode.INFERENCE_STARTED,
            message="PatchCore anomaly inference started",
            source="ml",
        )
        collected_logs.append(infer_start_log)

        try:
            pred = inferencer.predict(image)
            anomaly_score = float(pred["anomaly_score"])
            inference_time_ms = float(pred["inference_time_ms"])
            model_version = str(pred.get("model_name", "PatchCore"))
            defect_detection_status = "COMPLETED"

            infer_done_log = InspectionLogRecord(
                timestamp=get_utc_now_iso(),
                inspection_id=inspection_id,
                level=LogLevel.INFO,
                stage=InspectionStage.INFERENCE,
                event_code=EventCode.INFERENCE_COMPLETED,
                message=f"PatchCore anomaly inference completed. Score: {anomaly_score:.4f}, Latency: {inference_time_ms:.2f}ms",
                metrics={
                    "anomaly_score": anomaly_score,
                    "inference_time_ms": inference_time_ms,
                    "model": model_version,
                    "defect_detection_status": defect_detection_status,
                },
                source="ml",
            )
            collected_logs.append(infer_done_log)

            # Save anomaly map sidecar artifact if requested and available
            if capture_anomaly_map and isinstance(pred.get("anomaly_map"), np.ndarray):
                try:
                    save_anomaly_map_artifact(
                        inspection_id=inspection_id,
                        image_id=image_id,
                        anomaly_map=pred["anomaly_map"],
                        original_width=width,
                        original_height=height,
                        model_name=model_version or "PatchCore",
                        anomaly_score=anomaly_score,
                        decision_threshold=decision_threshold,
                    )
                except Exception as map_err:
                    logger.warning(f"Failed to persist anomaly map sidecar for {inspection_id}: {map_err}")
        except Exception as infer_err:
            defect_detection_status = "FAILED"
            inference_error_msg = _sanitize_error_message(infer_err)
            infer_fail_log = InspectionLogRecord(
                timestamp=get_utc_now_iso(),
                inspection_id=inspection_id,
                level=LogLevel.ERROR,
                stage=InspectionStage.INFERENCE,
                event_code=EventCode.INFERENCE_FAILED,
                message=f"PatchCore inference failed: {inference_error_msg}",
                source="ml",
            )
            collected_logs.append(infer_fail_log)

    # 6. Stage: DECISION -> Determine product OK / NG / UNKNOWN verdict
    verdict: str = "UNKNOWN"
    decision_confidence: str = "NOT_APPLICABLE"

    if defect_detection_status == "COMPLETED" and decision_threshold is not None and anomaly_score is not None:
        if anomaly_score > decision_threshold:
            verdict = "NG"
        else:
            verdict = "OK"

        if is_warning:
            decision_confidence = "UNCERTAIN_DUE_TO_IMAGE_QUALITY"
        else:
            decision_confidence = "HIGH"

    # Evaluate comprehensive final verdict
    final_result, final_reason_code = determine_final_verdict(
        status="COMPLETED",
        image_quality_status=quality_status,
        defect_detection_status=defect_detection_status,
        result=verdict,
    )

    # 7. Stage: COMPLETE -> Record final completion
    score_desc = f", Score: {anomaly_score:.4f}" if anomaly_score is not None else ""
    if is_warning and defect_detection_status == "COMPLETED":
        complete_level = LogLevel.WARN
        complete_msg = (
            f"Inspection completed with image quality warning ({quality_status}). "
            f"Final: {final_result} ({final_reason_code}), Product: {verdict}{score_desc}"
        )
    else:
        complete_level = LogLevel.INFO
        complete_msg = f"Inspection completed successfully. Final: {final_result} ({final_reason_code}), Quality: {quality_status}, Verdict: {verdict}{score_desc}"

    complete_metrics: Dict[str, Any] = {
        "verdict": verdict,
        "defect_detection_status": defect_detection_status,
        "image_quality_status": quality_status,
        "final_result": final_result,
        "final_reason_code": final_reason_code,
    }
    if anomaly_score is not None:
        complete_metrics["anomaly_score"] = anomaly_score
    if decision_threshold is not None:
        complete_metrics["decision_threshold"] = decision_threshold
    if decision_confidence != "NOT_APPLICABLE":
        complete_metrics["decision_confidence"] = decision_confidence

    complete_log = InspectionLogRecord(
        timestamp=get_utc_now_iso(),
        inspection_id=inspection_id,
        level=complete_level,
        stage=InspectionStage.COMPLETE,
        event_code=EventCode.INSPECTION_COMPLETED,
        message=complete_msg,
        metrics=complete_metrics,
        source="inspection",
    )
    collected_logs.append(complete_log)

    # 8. Build and persist InspectionRecord
    combined_metrics: Dict[str, Any] = {
        **analysis["image_size"],
        **brightness_metrics,
        "filename": f"{image_id}.png",
        "defect_detection_status": defect_detection_status,
        "decision_confidence": decision_confidence,
        "final_result": final_result,
        "final_reason_code": final_reason_code,
    }
    if inference_error_msg is not None:
        combined_metrics["defect_detection_error"] = inference_error_msg
    if anomaly_score is not None:
        combined_metrics["anomaly_score"] = anomaly_score
        combined_metrics["inference_time_ms"] = inference_time_ms
        combined_metrics["model_version"] = model_version
        combined_metrics["decision_threshold"] = decision_threshold

    record = InspectionRecord(
        inspection_id=inspection_id,
        product_id=product_id,
        timestamp=get_utc_now_iso(),
        image_id=image_id,
        result=verdict,
        image_quality_status=quality_status,
        metrics=combined_metrics,
        status="COMPLETED",
        anomaly_score=anomaly_score,
        decision_threshold=decision_threshold,
        inference_time_ms=inference_time_ms,
        defect_detection_status=defect_detection_status,
        final_result=final_result,
        final_reason_code=final_reason_code,
    )

    store.save_inspection(record)
    store.save_logs(collected_logs)

    return record, collected_logs

