"""Synthetic failure records and token selections independent of production policy."""

from tests.test_agent_tools import make_log, make_record


def error_record(**changes):
    values = dict(status="FAILED", result="UNKNOWN", image_quality_status="ERROR",
        defect_detection_status="SKIPPED", final_result="ERROR", final_reason_code="INSPECTION_FAILED",
        anomaly_score=None, decision_threshold=None, inference_time_ms=None, metrics={})
    values.update(changes)
    return make_record(**values)


def error_logs():
    return [make_log(event_code="IMAGE_LOAD_FAILED", stage="load", level="ERROR", metrics={}),
        make_log(event_code="INSPECTION_FAILED", stage="complete", level="ERROR", metrics={})]


def error_tokens(entries):
    record_fields = {"/data/anomaly_score", "/data/decision_threshold", "/data/inference_time_ms",
        "/data/metrics/mean", "/data/metrics/std"}
    return [entry["token"] for entry in entries if (
        entry["source_tool"] == "get_inspection_result" and entry["source_field"] in record_fields
        or entry["source_tool"] == "get_execution_logs" and entry["source_event"] in {
            "IMAGE_LOAD_FAILED", "INFERENCE_FAILED", "INSPECTION_FAILED"}
        and entry["source_field"].rsplit("/", 1)[-1] in {"event_code", "stage", "timestamp"})]


def with_error_facts(payload, record, logs=None):
    observations = [("get_inspection_result", "E0001", f"/data/{name}", None, getattr(record, name))
        for name in ("anomaly_score", "decision_threshold", "inference_time_ms")]
    observations.extend(("get_inspection_result", "E0001", f"/data/metrics/{name}", None, record.metrics.get(name))
        for name in ("mean", "std"))
    for index, event in enumerate(logs or error_logs()):
        observations.extend(("get_execution_logs", "E0002", f"/data/{index}/{name}", event.event_code, getattr(event, name))
            for name in ("event_code", "stage", "timestamp"))
    for tool, identifier, pointer, event, value in observations:
        if any(fact["source_tool"] == tool and fact["evidence_id"] == identifier and fact["source_field"] == pointer
            for fact in payload["observed_facts"]):
            continue
        if pointer.endswith("/timestamp"):
            value = value.replace("Z", "+00:00")
        payload["observed_facts"].append(dict(fact_id=f"F{len(payload['observed_facts']) + 1:04d}",
            evidence_id=identifier, source_tool=tool, source_field=pointer, source_event=event, observed_value=value))
    return payload
