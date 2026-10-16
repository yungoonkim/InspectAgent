"""Evidence sufficiency and final coverage for scoped brightness-warning reports."""

import math

from backend.agent.errors import AgentFailure
from backend.agent.reporting import CORE_FIELDS, _same_scalar, build_catalog
from backend.agent.tools import INSPECTION_ID_PATTERN, _timestamp, _valid_id


WARNINGS = {"WARNING_LOW_BRIGHTNESS", "WARNING_HIGH_BRIGHTNESS"}
METRICS = ("mean", "std", "min", "max")
EVENT_STAGES = {"ANALYSIS_COMPLETED": "analyze", "INSPECTION_COMPLETED": "complete"}


def validate_required_warning_events(codes):
    if not isinstance(codes, (tuple, list)) or any(not isinstance(code, str) for code in codes):
        raise ValueError("INVALID_WARNING_LOG_POLICY")
    result = tuple(codes)
    if len(result) != len(set(result)) or not set(result) <= set(EVENT_STAGES):
        raise ValueError("INVALID_WARNING_LOG_POLICY")
    return result


def warning_report_scope(state):
    snapshot = state.snapshot or {}
    return snapshot.get("image_quality_status") in WARNINGS and tuple(snapshot.get(name) for name in
        ("status", "result", "defect_detection_status", "final_result", "final_reason_code")) == (
            "COMPLETED", "OK", "COMPLETED", "REINSPECT", "IMAGE_QUALITY_WARNING",
        )


def _number(value, upper=None):
    return (type(value) in (int, float) and math.isfinite(value) and value >= 0
            and (upper is None or value <= upper))


def _matching_metrics(left, right):
    fields = (*METRICS, "width", "height", "channels")
    return all(name in left and name in right and _same_scalar(left[name], right[name]) for name in fields)


def warning_evidence_ready(state, *, required_event_codes=()):
    """Permit only a consistent, completed, model-OK brightness-warning investigation."""
    try:
        return _warning_evidence_ready(state, tuple(required_event_codes))
    except (AgentFailure, KeyError, IndexError, TypeError, ValueError, OverflowError):
        return False


def _warning_evidence_ready(state, required_event_codes, *, final_report=False):
    if not _valid_id(state.inspection_id, INSPECTION_ID_PATTERN) or not state.snapshot:
        return False
    snapshot = state.snapshot
    if snapshot["inspection_id"] != state.inspection_id or not warning_report_scope(state):
        return False
    score, threshold = snapshot["anomaly_score"], snapshot["decision_threshold"]
    if not _number(score) or not _number(threshold) or score > threshold:
        return False
    if len(required_event_codes) != len(set(required_event_codes)) or not set(required_event_codes) <= set(EVENT_STAGES):
        return False
    allowed_tools = {"get_inspection_result", "analyze_image_quality", "get_execution_logs"}
    if final_report:
        allowed_tools.add("get_inspection_history")
    if not state.trace:
        return False
    for entry in state.trace:
        optional_unavailable = (final_report and entry.tool_name in {"get_execution_logs", "get_inspection_history"}
            and entry.executed and not entry.success and entry.error_code == "DATA_UNAVAILABLE")
        if (not entry.executed or entry.tool_name not in allowed_tools
            or not optional_unavailable and (not entry.success or entry.error_code is not None)):
            return False
        if entry.tool_name == "get_inspection_history":
            if entry.arguments.get("product_id") != "TARGET-PRODUCT":
                return False
        elif entry.arguments.get("inspection_id") != state.inspection_id:
            return False
    catalog = build_catalog(state)
    successful = {entry.evidence_id: entry.tool_name for entry in state.trace if entry.success}
    if set(successful) != set(state.evidence) or {entry.evidence_id for entry in catalog.entries} != set(state.evidence):
        return False
    records = []
    qualities = []
    events = []
    for identifier, (tool, document) in state.evidence.items():
        if successful[identifier] != tool:
            return False
        data = document["data"]
        if tool == "get_inspection_history":
            continue
        if tool == "get_execution_logs":
            events.extend(data)
        else:
            if data["inspection_id"] != state.inspection_id:
                return False
            (records if tool == "get_inspection_result" else qualities).append(data)
    if not records or not qualities:
        return False
    for record in records:
        if any(not _same_scalar(record[name], snapshot[name]) for name in (*CORE_FIELDS, "anomaly_score", "decision_threshold")):
            return False
        if not _matching_metrics(record["metrics"], snapshot["metrics"]):
            return False
    for quality in qualities:
        metrics = quality["metrics"]
        if quality["image_quality_status"] != snapshot["image_quality_status"] or not _matching_metrics(metrics, snapshot["metrics"]):
            return False
        if any(not _number(metrics[name], 255) for name in METRICS) or not metrics["min"] <= metrics["mean"] <= metrics["max"]:
            return False
        if any(type(metrics[name]) is not int or not 0 < metrics[name] <= 100000 for name in ("width", "height", "channels")):
            return False
        if quality["threshold_status"] == "NOT_RECORDED":
            if quality["brightness_thresholds"] is not None:
                return False
        elif quality["threshold_status"] == "RECORDED":
            thresholds = quality["brightness_thresholds"]
            low, high = thresholds["low_threshold"], thresholds["high_threshold"]
            if not _number(low, 255) or not _number(high, 255) or low > high:
                return False
            if snapshot["image_quality_status"] == "WARNING_LOW_BRIGHTNESS" and not metrics["mean"] < low:
                return False
            if snapshot["image_quality_status"] == "WARNING_HIGH_BRIGHTNESS" and not metrics["mean"] > high:
                return False
        else:
            return False
    if any(quality != qualities[-1] for quality in qualities):
        return False
    for event in events:
        code = event["event_code"]
        if not isinstance(code, str) or code.endswith("FAILED") or event["level"] == "ERROR":
            return False
        for name in ("image_quality_status", "final_result", "final_reason_code", "result", "defect_detection_status"):
            value = event["metrics"].get(name)
            if value is not None and not _same_scalar(value, snapshot[name]):
                return False
    for code in required_event_codes:
        matching = [event for event in events if event["event_code"] == code]
        if not matching or any(event["stage"] != EVENT_STAGES[code] or event["level"] != "WARN"
            or event["timestamp_status"] != "VALID" or _timestamp(event["timestamp"]) is None for event in matching):
            return False
        if code == "ANALYSIS_COMPLETED" and any(any(name not in event["metrics"]
            or not _same_scalar(event["metrics"][name], snapshot["metrics"][name]) for name in METRICS) for event in matching):
            return False
        if code == "INSPECTION_COMPLETED" and any(any(event["metrics"].get(name) != snapshot[name]
            for name in ("image_quality_status", "final_result", "final_reason_code")) for event in matching):
            return False
    if set(required_event_codes) == set(EVENT_STAGES):
        analyzed = [_timestamp(event["timestamp"]) for event in events if event["event_code"] == "ANALYSIS_COMPLETED"]
        completed = [_timestamp(event["timestamp"]) for event in events if event["event_code"] == "INSPECTION_COMPLETED"]
        if max(analyzed) > min(completed):
            return False
    return True


def warning_report_covered(draft, state, *, required_event_codes=()):
    """Run only after Pydantic and deterministic fact/value verification."""
    try:
        ready = _warning_evidence_ready(state, tuple(required_event_codes), final_report=True)
    except (AgentFailure, KeyError, IndexError, TypeError, ValueError, OverflowError):
        return False
    if not ready:
        return False
    quality = next(document["data"] for tool, document in state.evidence.values() if tool == "analyze_image_quality")
    required = {"/data/image_quality_status", "/data/threshold_status", *(f"/data/metrics/{name}" for name in METRICS)}
    if quality["threshold_status"] == "RECORDED":
        required.update({"/data/brightness_thresholds/low_threshold", "/data/brightness_thresholds/high_threshold"})
    found = {fact.source_field for fact in draft.observed_facts if fact.source_tool == "analyze_image_quality"}
    if not required <= found:
        return False
    event_fields = {}
    for fact in draft.observed_facts:
        if fact.source_tool == "get_execution_logs":
            prefix, field = fact.source_field.rsplit("/", 1)
            event_fields.setdefault((fact.evidence_id, fact.source_event, prefix), set()).add(field)
    return all(any(source_event == code and {"stage", "timestamp"} <= fields
        for (identifier, source_event, prefix), fields in event_fields.items()) for code in required_event_codes)
