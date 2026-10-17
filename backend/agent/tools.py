"""Allowlisted, read-only inspection queries without image or model execution."""

from datetime import datetime, timezone
from collections import Counter
import math
import re
from typing import Any, Dict, Optional

from backend.storage import InspectionRecord, InspectionStorageBase


MAX_HISTORY_LIMIT = 20
HISTORY_SCAN_LIMIT = 1000
INSPECTION_ID_PATTERN = re.compile(r"INSP-[0-9]{6,12}")
PRODUCT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
IMAGE_ID_PATTERN = re.compile(r"IMG-BOTTLE-(?:[0-9]{4,8}|INJ-[0-9]{4,8}|NONEXISTENT)")
TIMESTAMP_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})"
)
ENUM_FIELDS = {
    "status": {"COMPLETED", "FAILED"},
    "result": {"OK", "NG", "UNKNOWN"},
    "image_quality_status": {
        "NORMAL", "WARNING_LOW_BRIGHTNESS", "WARNING_HIGH_BRIGHTNESS", "ERROR",
    },
    "defect_detection_status": {"COMPLETED", "FAILED", "SKIPPED", "UNINSPECTED"},
    "final_result": {"OK", "NG", "REINSPECT", "ERROR"},
    "final_reason_code": {
        "INSPECTION_FAILED", "IMAGE_QUALITY_WARNING", "DEFECT_DETECTION_UNAVAILABLE",
        "PRODUCT_ANOMALY_DETECTED", "ALL_CHECKS_PASSED", "UNKNOWN_STATE_COMBINATION",
    },
    "decision_confidence": {"HIGH", "UNCERTAIN_DUE_TO_IMAGE_QUALITY", "NOT_APPLICABLE"},
    "model_version": {"PatchCore", "PatchCore-ResNet18-180Train", "patchcore_bottle_v1_180"},
    "level": {"DEBUG", "INFO", "WARN", "ERROR"},
    "stage": {"init", "load", "analyze", "inference", "decision", "complete"},
    "event_code": {
        "INSPECTION_STARTED", "IMAGE_LOADED", "IMAGE_LOAD_FAILED", "ANALYSIS_COMPLETED",
        "INFERENCE_STARTED", "INFERENCE_COMPLETED", "INFERENCE_FAILED",
        "INSPECTION_COMPLETED", "INSPECTION_FAILED", "DECISION_MADE",
        "BRIGHTNESS_LOW_WARNING", "BRIGHTNESS_HIGH_WARNING",
    },
}
NUMBER_FIELDS = {"mean", "std", "min", "max", "anomaly_score", "decision_threshold", "inference_time_ms"}
SIZE_FIELDS = {"width", "height", "channels"}
QUALITY_FIELDS = ("mean", "std", "min", "max", "width", "height", "channels")


def _valid_id(value: Any, pattern: re.Pattern) -> bool:
    prohibited = ("ground_truth", "broken_large", "broken_small", "contamination", "evaluation_answers")
    return (
        isinstance(value, str)
        and pattern.fullmatch(value) is not None
        and not any(marker in value.lower() for marker in prohibited)
    )


def _enum(value: Any, field: str) -> Optional[str]:
    return value if isinstance(value, str) and value in ENUM_FIELDS[field] else None


def _number(value: Any) -> Optional[float]:
    if type(value) not in (int, float):
        return None
    try:
        return value if math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def _timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or TIMESTAMP_PATTERN.fullmatch(value) is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _safe_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    result = {}
    for field in sorted(NUMBER_FIELDS):
        value = _number(metrics.get(field))
        if field in QUALITY_FIELDS and value is not None and value > 255:
            value = None
        result[field] = value
    for field in sorted(SIZE_FIELDS):
        value = metrics.get(field)
        result[field] = value if type(value) is int and 0 < value <= 100000 else None
    for field in ("decision_confidence", "model_version", "defect_detection_status", "image_quality_status", "final_result", "final_reason_code", "result"):
        result[field] = _enum(metrics.get(field), field)
    return result


def _record_data(record: InspectionRecord) -> Dict[str, Any]:
    timestamp = _timestamp(record.timestamp)
    data = {
        "inspection_id": record.inspection_id if _valid_id(record.inspection_id, INSPECTION_ID_PATTERN) else None,
        "product_id": record.product_id if _valid_id(record.product_id, PRODUCT_ID_PATTERN) else None,
        "image_id": record.image_id if _valid_id(record.image_id, IMAGE_ID_PATTERN) else None,
        "timestamp": timestamp.isoformat() if timestamp else None,
        "timestamp_status": "VALID" if timestamp else "INVALID_OR_MISSING",
    }
    for field in ("status", "result", "image_quality_status", "defect_detection_status", "final_result", "final_reason_code"):
        data[field] = _enum(getattr(record, field), field)
    for field in ("anomaly_score", "decision_threshold", "inference_time_ms"):
        data[field] = _number(getattr(record, field))
    data["decision_confidence"] = _enum(record.metrics.get("decision_confidence"), "decision_confidence")
    data["model_version"] = _enum(record.metrics.get("model_version"), "model_version")
    safe_metrics = _safe_metrics(record.metrics)
    data["metrics"] = {field: safe_metrics[field] for field in QUALITY_FIELDS}
    return data


def _response(data: Any = None, error: Optional[str] = None, **metadata: Any) -> Dict[str, Any]:
    return {"ok": error is None, "error": error, "data": data, "metadata": metadata}


def _brightness_comparison(current, candidates, limit, candidate_count):
    metrics = current["metrics"]
    current_mean = metrics.get("mean")
    current_time = _timestamp(current.get("timestamp"))
    dimensions = tuple(metrics.get(name) for name in ("width", "height", "channels"))
    available = (current_time is not None and current.get("status") == "COMPLETED"
        and _number(current_mean) is not None and current_mean <= 255
        and all(type(value) is int and 0 < value <= 100000 for value in dimensions))
    counts = Counter(record.get("inspection_id") for record in candidates)
    samples = []
    if available:
        for record in candidates:
            identifier = record.get("inspection_id")
            timestamp = _timestamp(record.get("timestamp"))
            past_metrics = record.get("metrics", {})
            mean = past_metrics.get("mean")
            if (not _valid_id(identifier, INSPECTION_ID_PATTERN) or counts[identifier] != 1
                or identifier == current["inspection_id"] or record.get("product_id") != current["product_id"]
                or timestamp is None or timestamp >= current_time or record.get("status") != "COMPLETED"
                or record.get("final_result") == "ERROR" or record.get("image_quality_status") not in {
                    "NORMAL", "WARNING_LOW_BRIGHTNESS", "WARNING_HIGH_BRIGHTNESS"}
                or _number(mean) is None or mean > 255
                or tuple(past_metrics.get(name) for name in ("width", "height", "channels")) != dimensions):
                continue
            samples.append(record)
        samples.sort(key=lambda record: (_timestamp(record["timestamp"]), record["inspection_id"]), reverse=True)
        samples = samples[:limit]
    values = [record["metrics"]["mean"] for record in samples]
    historical_mean = math.fsum(values) / len(values) if values else None
    status = ("CURRENT_UNAVAILABLE" if not available else "NO_HISTORY" if candidate_count == 0
        else "NO_COMPARABLE_HISTORY" if not values else "SINGLE_OBSERVATION" if len(values) == 1
        else "DESCRIPTIVE_SUMMARY")
    return {
        "current": current, "samples": samples, "limit": limit,
        "summary": {
            "scope": "STORED_VALUES_ONLY_UNVERIFIED_MEASUREMENT_CONTRACT",
            "status": status, "current_mean": current_mean, "sample_count": len(values),
            "historical_mean": historical_mean, "historical_min": min(values) if values else None,
            "historical_max": max(values) if values else None,
            "absolute_mean_difference": abs(current_mean - historical_mean) if values else None,
        },
    }


class InspectionTools:
    """Four business-ID queries backed exclusively by an injected storage interface."""

    def __init__(self, storage: InspectionStorageBase):
        self._storage = storage

    def _lookup(self, inspection_id: str):
        if not _valid_id(inspection_id, INSPECTION_ID_PATTERN):
            return None, "INVALID_ARGUMENT"
        try:
            record = self._storage.get_inspection(inspection_id)
        except Exception:
            return None, "STORAGE_ERROR"
        if record is None:
            return None, "NOT_FOUND"
        if record.inspection_id != inspection_id:
            return None, "DATA_UNAVAILABLE"
        return record, None

    def get_inspection_result(self, inspection_id: str) -> Dict[str, Any]:
        """Return stored verdicts and numeric evidence; never recalculate a verdict."""
        record, error = self._lookup(inspection_id)
        return _response(error=error) if error else _response(_record_data(record))

    def get_execution_logs(self, inspection_id: str) -> Dict[str, Any]:
        """Sort valid times ascending, then retain undated entries in storage order."""
        record, error = self._lookup(inspection_id)
        if error:
            return _response(error=error)
        try:
            logs = self._storage.get_logs(inspection_id)
        except Exception:
            return _response(error="STORAGE_ERROR")
        entries = []
        for log in logs:
            if log.inspection_id != inspection_id:
                continue
            timestamp = _timestamp(log.timestamp)
            entries.append({
                "timestamp": timestamp.isoformat() if timestamp else None,
                "timestamp_status": "VALID" if timestamp else "INVALID_OR_MISSING",
                "level": _enum(log.level, "level"),
                "stage": _enum(log.stage, "stage"),
                "event_code": _enum(log.event_code, "event_code"),
                "metrics": _safe_metrics(log.metrics or {}),
            })
        entries.sort(key=lambda entry: (
            entry["timestamp"] is None,
            _timestamp(entry["timestamp"]) or datetime.max.replace(tzinfo=timezone.utc),
        ))
        invalid_count = sum(entry["timestamp"] is None for entry in entries)
        return _response(
            entries, error=None if entries else "DATA_UNAVAILABLE",
            inspection_exists=True, ordering="TIMESTAMP_ASC_INVALID_LAST_STABLE",
            invalid_timestamp_count=invalid_count, messages_included=False,
        )

    def analyze_image_quality(self, inspection_id: str) -> Dict[str, Any]:
        """Expose recorded image quality without reloading images or current settings."""
        record, error = self._lookup(inspection_id)
        if error:
            return _response(error=error)
        safe_record = _record_data(record)
        data = {
            "inspection_id": safe_record["inspection_id"],
            "image_quality_status": safe_record["image_quality_status"],
            "metrics": safe_record["metrics"],
            "brightness_thresholds": None,
            "threshold_status": "NOT_RECORDED",
        }
        thresholds = record.metrics.get("applied_thresholds")
        if isinstance(thresholds, dict):
            low = _number(thresholds.get("low_threshold"))
            high = _number(thresholds.get("high_threshold"))
            if low is not None and high is not None and low <= high <= 255:
                data["brightness_thresholds"] = {"low_threshold": low, "high_threshold": high}
                data["threshold_status"] = "RECORDED"
        return _response(data, measurement_source="STORED_RECORD", physical_cause_confirmed=False)

    def get_inspection_history(self, product_id: str, limit: int = 5, inspection_id: Optional[str] = None) -> Dict[str, Any]:
        """Return latest valid timestamps within a bounded storage-order candidate set."""
        if not _valid_id(product_id, PRODUCT_ID_PATTERN) or type(limit) is not int or not 1 <= limit <= MAX_HISTORY_LIMIT:
            return _response(error="INVALID_ARGUMENT")
        current = None
        if inspection_id is not None:
            current, error = self._lookup(inspection_id)
            if error:
                return _response(error=error)
            if current.product_id != product_id:
                return _response(error="INVALID_ARGUMENT")
        try:
            records = self._storage.list_inspections(limit=HISTORY_SCAN_LIMIT, product_id=product_id)
        except Exception:
            return _response(error="STORAGE_ERROR")
        candidates = [_record_data(record) for record in records[:HISTORY_SCAN_LIMIT] if record.product_id == product_id]
        valid = [record for record in candidates if record["timestamp"] is not None]
        invalid = [record for record in candidates if record["timestamp"] is None]
        valid.sort(key=lambda record: _timestamp(record["timestamp"]), reverse=True)
        response = _response(
            (valid + invalid)[:limit], error=None if candidates else "DATA_UNAVAILABLE",
            ordering="TIMESTAMP_DESC_INVALID_LAST_STABLE", scan_limit=HISTORY_SCAN_LIMIT,
            candidate_count=len(candidates), scan_limit_reached=len(records) >= HISTORY_SCAN_LIMIT,
            ordering_scope="RETURNED_STORAGE_CANDIDATES", global_latest_guaranteed=False,
            invalid_timestamp_count=len(invalid),
        )
        if current is not None:
            response["brightness_comparison"] = _brightness_comparison(
                _record_data(current), candidates, limit, len(candidates),
            )
        return response
