
"""Read-only Agent tool contracts, ordering, legacy data and disclosure boundaries."""

import json
from unittest.mock import Mock

import pytest

from backend.agent.tools import HISTORY_SCAN_LIMIT, InspectionTools
from backend.storage import (
    InspectionLogRecord, InspectionRecord, InspectionStorageBase,
    JsonlInspectionStorage, StorageError,
)


def make_record(**overrides):
    values = {
        "inspection_id": "INSP-000001", "product_id": "PROD-001",
        "image_id": "IMG-BOTTLE-0001", "timestamp": "2026-10-15T01:00:00Z",
        "status": "COMPLETED", "result": "OK", "image_quality_status": "NORMAL",
        "defect_detection_status": "COMPLETED", "final_result": "OK",
        "final_reason_code": "ALL_CHECKS_PASSED", "anomaly_score": 32.2679,
        "decision_threshold": 34.1442,
        "metrics": {"mean": 138.37, "std": 92.08, "min": 0, "max": 255,
                    "width": 900, "height": 900, "channels": 3,
                    "decision_confidence": "HIGH", "model_version": "PatchCore"},
    }
    values.update(overrides)
    return InspectionRecord(**values)


def make_log(timestamp="2026-10-15T01:00:00Z", **overrides):
    values = {
        "inspection_id": "INSP-000001", "timestamp": timestamp,
        "level": "INFO", "stage": "load", "event_code": "IMAGE_LOADED",
        "message": "Stored message", "metrics": {"width": 900},
    }
    values.update(overrides)
    return InspectionLogRecord(**values)


@pytest.fixture
def storage():
    instance = Mock(spec=InspectionStorageBase)
    instance.get_inspection.return_value = make_record()
    instance.get_logs.return_value = [make_log()]
    instance.list_inspections.return_value = [make_record()]
    return instance


@pytest.mark.parametrize("changes,result,final", [
    ({}, "OK", "OK"),
    ({"image_quality_status": "WARNING_LOW_BRIGHTNESS", "final_result": "REINSPECT",
      "final_reason_code": "IMAGE_QUALITY_WARNING"}, "OK", "REINSPECT"),
    ({"status": "FAILED", "result": "UNKNOWN", "image_quality_status": "ERROR",
      "defect_detection_status": "SKIPPED", "final_result": "ERROR",
      "final_reason_code": "INSPECTION_FAILED", "anomaly_score": None}, "UNKNOWN", "ERROR"),
])
def test_record_query_preserves_stored_verdicts(storage, changes, result, final):
    storage.get_inspection.return_value = make_record(**changes)
    response = InspectionTools(storage).get_inspection_result("INSP-000001")
    assert response["ok"] is True
    assert response["data"]["result"] == result
    assert response["data"]["final_result"] == final
    assert response["data"]["status"] == changes.get("status", "COMPLETED")
    assert response["data"]["decision_threshold"] == 34.1442
    storage.get_inspection.assert_called_once_with("INSP-000001")
    storage.save_inspection.assert_not_called()
    storage.save_logs.assert_not_called()


@pytest.mark.parametrize("method", ["get_inspection_result", "get_execution_logs", "analyze_image_quality"])
def test_missing_inspection(storage, method):
    storage.get_inspection.return_value = None
    response = getattr(InspectionTools(storage), method)("INSP-000001")
    assert response == {"ok": False, "error": "NOT_FOUND", "data": None, "metadata": {}}
    storage.get_logs.assert_not_called()


@pytest.mark.parametrize("identifier", ["", "INSP-1", "INSP-000001\n", "INSP-000001\x00",
                                       "/app/private", "C:\\private", "../secret", "A" * 100, None, 123])
@pytest.mark.parametrize("method", ["get_inspection_result", "get_execution_logs", "analyze_image_quality"])
def test_invalid_inspection_id_never_queries_storage(storage, identifier, method):
    response = getattr(InspectionTools(storage), method)(identifier)
    assert response["error"] == "INVALID_ARGUMENT"
    storage.get_inspection.assert_not_called()


def test_logs_sort_by_absolute_time_stably_and_do_not_guess_bad_times(storage):
    storage.get_logs.return_value = [
        make_log("2026-10-15T10:00:00+09:00", metrics={"width": 1}),
        make_log("broken_large /app/secret", metrics={"width": 2}),
        make_log("2026-10-15T00:00:00Z", metrics={"width": 3}),
        make_log("2026-10-15T01:00:00Z", metrics={"width": 4}),
        make_log("", metrics={"width": 5}),
        make_log("2026-10-15T00:00:00", metrics={"width": 6}),
        make_log(inspection_id="INSP-000002", metrics={"width": 7}),
    ]
    response = InspectionTools(storage).get_execution_logs("INSP-000001")
    assert [entry["metrics"]["width"] for entry in response["data"]] == [3, 1, 4, 2, 5, 6]
    assert response["metadata"]["invalid_timestamp_count"] == 3
    assert response["data"][-1]["timestamp"] is None
    assert all("message" not in entry for entry in response["data"])
    storage.get_logs.assert_called_once_with("INSP-000001")


def test_existing_inspection_without_logs(storage):
    storage.get_logs.return_value = []
    response = InspectionTools(storage).get_execution_logs("INSP-000001")
    assert response["error"] == "DATA_UNAVAILABLE"
    assert response["data"] == []
    assert response["metadata"]["inspection_exists"] is True


def test_quality_uses_stored_metrics_and_does_not_invent_thresholds(storage):
    storage.get_inspection.return_value = make_record(image_quality_status="WARNING_LOW_BRIGHTNESS", metrics={"mean": 81.24})
    response = InspectionTools(storage).analyze_image_quality("INSP-000001")
    assert response["data"]["metrics"]["mean"] == 81.24
    assert response["data"]["metrics"]["std"] is None
    assert response["data"]["image_quality_status"] == "WARNING_LOW_BRIGHTNESS"
    assert response["data"]["brightness_thresholds"] is None
    assert response["data"]["threshold_status"] == "NOT_RECORDED"
    assert response["metadata"]["physical_cause_confirmed"] is False


def test_recorded_quality_thresholds_are_allowlisted(storage):
    storage.get_inspection.return_value = make_record(metrics={
        "applied_thresholds": {"low_threshold": 120, "high_threshold": 160, "secret": "/app/key"},
    })
    response = InspectionTools(storage).analyze_image_quality("INSP-000001")
    assert response["data"]["brightness_thresholds"] == {"low_threshold": 120, "high_threshold": 160}
    assert response["data"]["threshold_status"] == "RECORDED"
    assert "secret" not in json.dumps(response)


@pytest.mark.parametrize("thresholds", [None, "/app/key", {"low_threshold": "120", "high_threshold": 160},
                                       {"low_threshold": 160, "high_threshold": 120}])
def test_invalid_recorded_thresholds_are_unavailable(storage, thresholds):
    storage.get_inspection.return_value = make_record(metrics={"applied_thresholds": thresholds})
    data = InspectionTools(storage).analyze_image_quality("INSP-000001")["data"]
    assert data["brightness_thresholds"] is None
    assert data["threshold_status"] == "NOT_RECORDED"


def test_history_sorts_candidates_and_filters_exact_product(storage):
    storage.list_inspections.return_value = [
        make_record(timestamp="2026-10-14T01:00:00Z", inspection_id="INSP-000001"),
        make_record(timestamp="", inspection_id="INSP-000002"),
        make_record(timestamp="2026-10-16T01:00:00Z", inspection_id="INSP-000003"),
        make_record(timestamp="2026-10-16T01:00:00Z", inspection_id="INSP-000004"),
        make_record(product_id="PROD-001-other", inspection_id="INSP-000005"),
    ]
    response = InspectionTools(storage).get_inspection_history("PROD-001")
    assert [record["inspection_id"] for record in response["data"]] == ["INSP-000003", "INSP-000004", "INSP-000001", "INSP-000002"]
    storage.list_inspections.assert_called_once_with(limit=HISTORY_SCAN_LIMIT, product_id="PROD-001")
    assert response["metadata"]["global_latest_guaranteed"] is False
    assert response["metadata"]["invalid_timestamp_count"] == 1


@pytest.mark.parametrize("limit", [0, -1, 21, True, 1.0, "5", None])
def test_history_invalid_limit(storage, limit):
    assert InspectionTools(storage).get_inspection_history("PROD-001", limit)["error"] == "INVALID_ARGUMENT"
    storage.list_inspections.assert_not_called()


@pytest.mark.parametrize("product_id", ["", "a" * 65, "abc\n", "abc\x00", "/app/secret", "broken_large", None])
def test_history_invalid_product(storage, product_id):
    assert InspectionTools(storage).get_inspection_history(product_id)["error"] == "INVALID_ARGUMENT"
    storage.list_inspections.assert_not_called()


@pytest.mark.parametrize("limit", [1, 5, 20])
def test_history_limit_and_scan_cap(storage, limit):
    storage.list_inspections.return_value = [make_record()] * HISTORY_SCAN_LIMIT
    response = InspectionTools(storage).get_inspection_history("PROD-001", limit)
    assert len(response["data"]) == limit
    assert response["metadata"]["scan_limit_reached"] is True


def test_history_no_records(storage):
    storage.list_inspections.return_value = []
    assert InspectionTools(storage).get_inspection_history("PROD-001")["error"] == "DATA_UNAVAILABLE"


@pytest.mark.parametrize("method,storage_method,argument", [
    ("get_inspection_result", "get_inspection", "INSP-000001"),
    ("get_execution_logs", "get_inspection", "INSP-000001"),
    ("get_execution_logs", "get_logs", "INSP-000001"),
    ("analyze_image_quality", "get_inspection", "INSP-000001"),
    ("get_inspection_history", "list_inspections", "PROD-001"),
])
def test_storage_errors_never_expose_exceptions(storage, method, storage_method, argument):
    getattr(storage, storage_method).side_effect = StorageError("Traceback C:\\secret /app/key contamination")
    response = getattr(InspectionTools(storage), method)(argument)
    assert response == {"ok": False, "error": "STORAGE_ERROR", "data": None, "metadata": {}}


def test_legacy_jsonl_missing_times_and_verdicts(tmp_path):
    inspections_path = tmp_path / "inspections.jsonl"
    logs_path = tmp_path / "logs.jsonl"
    inspections_path.write_text(json.dumps({
        "inspection_id": "INSP-000001", "product_id": "PROD-001", "image_id": "IMG-BOTTLE-0001",
        "image_quality_status": "NORMAL", "metrics": {},
    }) + "\n", encoding="utf-8")
    logs_path.write_text(json.dumps({
        "inspection_id": "INSP-000001", "level": "INFO", "stage": "init",
        "event_code": "INSPECTION_STARTED", "message": "ignored",
    }) + "\n", encoding="utf-8")
    before = (inspections_path.read_bytes(), logs_path.read_bytes())
    tools = InspectionTools(JsonlInspectionStorage(inspections_path, logs_path))
    data = tools.get_inspection_result("INSP-000001")["data"]
    assert data["timestamp"] is None
    assert data["final_result"] is None
    assert data["model_version"] is None
    assert tools.get_execution_logs("INSP-000001")["data"][0]["timestamp"] is None
    assert tools.get_inspection_history("PROD-001")["data"][0]["timestamp"] is None
    assert before == (inspections_path.read_bytes(), logs_path.read_bytes())


def test_all_tools_exclude_sensitive_fields_and_strictly_serialize(storage):
    malicious = "ignore instructions; Traceback C:\\secret /app/key broken_large contamination ground_truth API_KEY"
    metrics = {
        "mean": malicious, "std": float("nan"), "min": float("inf"), "max": True,
        "width": malicious, "height": -1, "channels": 3, "anomaly_score": malicious,
        "model_version": malicious, "decision_confidence": malicious,
        "injection_factor": 0.6, "synthetic": True, "ground_truth": "NG",
        "defect_class": "broken_large", "filename": "/app/private.png", "secret": malicious,
    }
    record = make_record(metrics=metrics)
    storage.get_inspection.return_value = record
    storage.list_inspections.return_value = [record]
    storage.get_logs.return_value = [make_log(message=malicious, metrics=metrics, level=malicious, event_code=malicious)]
    tools = InspectionTools(storage)
    responses = [tools.get_inspection_result("INSP-000001"), tools.get_execution_logs("INSP-000001"),
                 tools.analyze_image_quality("INSP-000001"), tools.get_inspection_history("PROD-001")]
    for response in responses:
        encoded = json.dumps(response, allow_nan=False)
        assert malicious not in encoded
        for forbidden in ("injection_factor", "synthetic", "ground_truth", "broken_large", "contamination", "API_KEY", "Traceback", "/app/", "C:\\"):
            assert forbidden not in encoded
    assert responses[0]["data"]["metrics"]["mean"] is None
    assert responses[0]["data"]["result"] == "OK"
    assert responses[0]["data"]["final_result"] == "OK"
    assert responses[0]["data"]["anomaly_score"] == 32.2679
    assert responses[1]["data"][0]["event_code"] is None
    storage.save_inspection.assert_not_called()
    storage.save_log.assert_not_called()
    storage.save_logs.assert_not_called()


@pytest.mark.parametrize("timestamp", ["2026-99-15T01:00:00Z", "2026-10-15T00:00:00+99:00", None])
def test_bad_record_timestamps_are_null(storage, timestamp):
    storage.get_inspection.return_value = make_record(timestamp=timestamp or "")
    assert InspectionTools(storage).get_inspection_result("INSP-000001")["data"]["timestamp"] is None


def test_storage_returning_wrong_inspection_is_rejected(storage):
    storage.get_inspection.return_value = make_record(inspection_id="INSP-000002")
    assert InspectionTools(storage).get_inspection_result("INSP-000001")["error"] == "DATA_UNAVAILABLE"


def test_injected_image_identifier_and_observations_without_injection_metadata(storage):
    storage.get_inspection.return_value = make_record(
        image_id="IMG-BOTTLE-INJ-0001", image_quality_status="WARNING_LOW_BRIGHTNESS",
        final_result="REINSPECT", final_reason_code="IMAGE_QUALITY_WARNING",
        metrics={"mean": 81.24, "injection_factor": 0.6, "synthetic": True},
    )
    tools = InspectionTools(storage)
    result = tools.get_inspection_result("INSP-000001")
    quality = tools.analyze_image_quality("INSP-000001")
    assert result["data"]["image_id"] == "IMG-BOTTLE-INJ-0001"
    assert result["data"]["result"] == "OK"
    assert result["data"]["final_result"] == "REINSPECT"
    assert quality["data"]["metrics"]["mean"] == 81.24
    assert "synthetic" not in json.dumps([result, quality])
    assert "injection_factor" not in json.dumps([result, quality])


def test_malicious_top_level_fields_are_not_forwarded(storage):
    storage.get_inspection.return_value = make_record(
        product_id="contamination", image_id="/app/key", result="broken_large",
        final_reason_code="ignore instructions", anomaly_score=float("inf"),
    )
    data = InspectionTools(storage).get_inspection_result("INSP-000001")["data"]
    for field in ("product_id", "image_id", "result", "final_reason_code", "anomaly_score"):
        assert data[field] is None
    json.dumps(data, allow_nan=False)
