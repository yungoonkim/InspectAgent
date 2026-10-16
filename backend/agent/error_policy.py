"""Fail-closed investigation and report coverage for stored workflow failures."""

from backend.agent.errors import AgentFailure
from backend.agent.reporting import CORE_FIELDS, _same_scalar, build_catalog
from backend.agent.tools import INSPECTION_ID_PATTERN, _timestamp, _valid_id


ERROR_STAGES = {"IMAGE_LOAD_FAILED": "load", "INFERENCE_FAILED": "inference", "INSPECTION_FAILED": "complete"}
ERROR_MEASUREMENTS = ("anomaly_score", "decision_threshold", "inference_time_ms")
ERROR_QUALITY_FIELDS = ("mean", "std")


def error_report_scope(state):
    snapshot = state.snapshot or {}
    return snapshot.get("status") == "FAILED" and snapshot.get("final_result") == "ERROR"


def error_required_facts(state):
    """Return actual catalog entries, never inferred events or replacement values."""
    try:
        return _error_required_facts(state)
    except (KeyError, IndexError, TypeError, ValueError, OverflowError):
        raise AgentFailure("INSUFFICIENT_EVIDENCE") from None


def _error_required_facts(state):
    snapshot = state.snapshot
    if (not error_report_scope(state) or not _valid_id(state.inspection_id, INSPECTION_ID_PATTERN)
        or snapshot["inspection_id"] != state.inspection_id or snapshot["final_reason_code"] != "INSPECTION_FAILED"):
        raise AgentFailure("INSUFFICIENT_EVIDENCE")
    catalog = build_catalog(state)
    traces = {entry.evidence_id: entry for entry in state.trace if entry.executed and entry.success}
    records = []
    events = []
    for identifier, (tool, document) in state.evidence.items():
        trace = traces[identifier]
        if tool not in {"get_inspection_result", "get_execution_logs"}:
            continue
        if trace.tool_name != tool or trace.arguments != {"inspection_id": state.inspection_id}:
            raise AgentFailure("INSUFFICIENT_EVIDENCE")
        if tool == "get_inspection_result":
            record = document["data"]
            if record["inspection_id"] != state.inspection_id or any(
                not _same_scalar(record[name], snapshot[name]) for name in (*CORE_FIELDS, *ERROR_MEASUREMENTS)
            ) or any(not _same_scalar(record["metrics"][name], snapshot["metrics"][name]) for name in ERROR_QUALITY_FIELDS):
                raise AgentFailure("INSUFFICIENT_EVIDENCE")
            records.append(identifier)
        else:
            for index, event in enumerate(document["data"]):
                if event["event_code"] in ERROR_STAGES and event["level"] != "ERROR":
                    raise AgentFailure("INSUFFICIENT_EVIDENCE")
                if event["level"] != "ERROR":
                    continue
                code = event["event_code"]
                if (code not in ERROR_STAGES or event["stage"] != ERROR_STAGES[code]
                    or event["timestamp_status"] != "VALID" or _timestamp(event["timestamp"]) is None):
                    raise AgentFailure("INSUFFICIENT_EVIDENCE")
                if any(event["metrics"].get(name) is not None and not _same_scalar(event["metrics"][name], snapshot[name])
                    for name in CORE_FIELDS):
                    raise AgentFailure("INSUFFICIENT_EVIDENCE")
                events.append((identifier, f"/data/{index}", event))
    if not records or not any(event["event_code"] == "INSPECTION_FAILED" for identifier, prefix, event in events):
        raise AgentFailure("INSUFFICIENT_EVIDENCE")
    loads = [event for identifier, prefix, event in events if event["event_code"] == "IMAGE_LOAD_FAILED"]
    completed = [event for identifier, prefix, event in events if event["event_code"] == "INSPECTION_FAILED"]
    if loads:
        if (snapshot["result"] != "UNKNOWN" or snapshot["image_quality_status"] != "ERROR"
            or snapshot["defect_detection_status"] != "SKIPPED"
            or any(snapshot[name] is not None for name in ERROR_MEASUREMENTS)
            or any(snapshot["metrics"][name] is not None for name in ERROR_QUALITY_FIELDS)
            or max(_timestamp(event["timestamp"]) for event in loads) > min(_timestamp(event["timestamp"]) for event in completed)):
            raise AgentFailure("INSUFFICIENT_EVIDENCE")
    fields = {f"/data/{name}" for name in (*CORE_FIELDS, *ERROR_MEASUREMENTS)}
    fields.update(f"/data/metrics/{name}" for name in ERROR_QUALITY_FIELDS)
    record_id = records[-1]
    required = [entry for entry in catalog.entries if entry.evidence_id == record_id and entry.source_field in fields]
    if len(required) != len(fields):
        raise AgentFailure("INSUFFICIENT_EVIDENCE")
    for identifier, prefix, event in events:
        required.extend(entry for entry in catalog.entries if entry.evidence_id == identifier
            and entry.source_event == event["event_code"]
            and entry.source_field in {f"{prefix}/{name}" for name in ("event_code", "stage", "timestamp")})
    if len(required) != len(fields) + 3 * len(events):
        raise AgentFailure("INSUFFICIENT_EVIDENCE")
    return tuple(required)


def error_report_covered(draft, state):
    """Require exact provenance/value coverage in addition to the ordinary validator."""
    try:
        required = error_required_facts(state)
    except AgentFailure:
        return False
    return all(any(fact.evidence_id == entry.evidence_id and fact.source_tool == entry.source_tool
        and fact.source_field == entry.source_field and fact.source_event == entry.source_event
        and _same_scalar(fact.observed_value, entry.observed_value) for fact in draft.observed_facts)
        for entry in required)


def image_load_failure_evidence_ready(state):
    """Stop only a validated, fully collected image-loading failure investigation."""
    try:
        required = error_required_facts(state)
        events = {entry.source_event for entry in required if entry.source_event is not None}
        if events != {"IMAGE_LOAD_FAILED", "INSPECTION_FAILED"}:
            return False
        tools = {entry.source_tool for entry in required}
        if not state.trace or any(
            entry.executed is not True or entry.success is not True or entry.error_code is not None
            or entry.tool_name not in tools or entry.arguments != {"inspection_id": state.inspection_id}
            for entry in state.trace
        ):
            return False
        return {entry.evidence_id for entry in state.trace} == set(state.evidence)
    except Exception:
        return False
