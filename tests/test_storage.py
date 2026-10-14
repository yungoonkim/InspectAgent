"""Unit and integration tests for JSONL storage, schema validation, and inspection workflow."""

import json
from pathlib import Path
import pytest

from backend.config import get_settings
from backend.inspection import (
    ImageRegistry,
    InspectionIdGenerator,
    execute_inspection_workflow,
    get_image_registry,
)
from backend.storage import (
    EventCode,
    InspectionLogRecord,
    InspectionRecord,
    InspectionStage,
    JsonlInspectionStorage,
    LogLevel,
    StorageFormatError,
    get_inspection_storage,
    get_utc_now_iso,
)


@pytest.fixture
def temp_storage(tmp_path: Path) -> JsonlInspectionStorage:
    """Fixture providing an isolated JsonlInspectionStorage in a temporary directory."""
    insp_file = tmp_path / "data" / "inspections.jsonl"
    logs_file = tmp_path / "data" / "inspection_logs.jsonl"
    return JsonlInspectionStorage(inspections_path=insp_file, logs_path=logs_file)


# ==============================================================================
# Schema Validation & Format Error Tests
# ==============================================================================

def test_storage_schema_validation_success():
    """Verify InspectionRecord and InspectionLogRecord instantiate with valid fields."""
    rec = InspectionRecord(
        inspection_id="INSP-000001",
        product_id="ABCD1541",
        timestamp=get_utc_now_iso(),
        image_id="IMG-BOTTLE-0001",
        result="UNKNOWN",
        image_quality_status="NORMAL",
        metrics={"mean": 136.3, "std": 1.4, "width": 900, "height": 900},
        status="COMPLETED",
    )
    assert rec.inspection_id == "INSP-000001"
    assert rec.result == "UNKNOWN"
    assert rec.image_quality_status == "NORMAL"

    log = InspectionLogRecord(
        timestamp=get_utc_now_iso(),
        inspection_id="INSP-000001",
        level=LogLevel.INFO,
        stage=InspectionStage.LOAD,
        event_code=EventCode.IMAGE_LOADED,
        message="Image loaded",
        metrics={"width": 900, "height": 900},
        source="vision",
    )
    assert log.event_code == EventCode.IMAGE_LOADED
    assert log.level == "INFO"


def test_storage_format_error_handling(temp_storage: JsonlInspectionStorage):
    """Verify storage raises StorageFormatError when record format violates schema."""
    # Missing required fields in dictionary
    invalid_dict = {"product_id": "ABCD1541"}  # Missing inspection_id, image_id, image_quality_status
    with pytest.raises(StorageFormatError):
        temp_storage.save_inspection(invalid_dict)  # type: ignore

    invalid_log = {"message": "Invalid log"}  # Missing inspection_id, level, stage, event_code
    with pytest.raises(StorageFormatError):
        temp_storage.save_log(invalid_log)  # type: ignore


# ==============================================================================
# JSONL Formatting & Line-by-Line Integrity Tests
# ==============================================================================

def test_jsonl_storage_append_and_read_isolation(temp_storage: JsonlInspectionStorage, tmp_path: Path):
    """Verify JSONL files contain strictly one valid JSON object per line and read back correctly."""
    insp_path = tmp_path / "data" / "inspections.jsonl"
    logs_path = tmp_path / "data" / "inspection_logs.jsonl"

    rec1 = InspectionRecord(
        inspection_id="INSP-000001",
        product_id="ABCD1541",
        timestamp=get_utc_now_iso(),
        image_id="IMG-BOTTLE-0001",
        result="UNKNOWN",
        image_quality_status="NORMAL",
        metrics={"mean": 136.34},
        status="COMPLETED",
    )
    rec2 = InspectionRecord(
        inspection_id="INSP-000002",
        product_id="ABCD1541",
        timestamp=get_utc_now_iso(),
        image_id="IMG-BOTTLE-0002",
        result="UNKNOWN",
        image_quality_status="WARNING_LOW_BRIGHTNESS",
        metrics={"mean": 81.8},
        status="COMPLETED",
    )

    temp_storage.save_inspection(rec1)
    temp_storage.save_inspection(rec2)

    # Verify line-by-line JSON validity in inspections.jsonl
    with open(insp_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    assert len(lines) == 2
    for line in lines:
        parsed = json.loads(line)
        assert "inspection_id" in parsed
        assert "timestamp" in parsed
        assert parsed["result"] == "UNKNOWN"

    # Query back via storage interface
    loaded_rec1 = temp_storage.get_inspection("INSP-000001")
    assert loaded_rec1 is not None
    assert loaded_rec1.inspection_id == "INSP-000001"
    assert loaded_rec1.image_quality_status == "NORMAL"

    loaded_rec2 = temp_storage.get_inspection("INSP-000002")
    assert loaded_rec2 is not None
    assert loaded_rec2.image_quality_status == "WARNING_LOW_BRIGHTNESS"


# ==============================================================================
# Inspection Workflow Execution & Event Sequence Tests
# ==============================================================================

def test_execute_inspection_workflow_success(temp_storage: JsonlInspectionStorage):
    """Verify workflow executes sequentially, logs real events, and connects result with logs."""
    settings = get_settings()
    train_good_dir = settings.absolute_dataset_path / "train" / "good"

    if not train_good_dir.exists():
        pytest.skip("Dataset train/good not available; skipping workflow execution test.")

    registry = get_image_registry(settings)
    image_ids = registry.list_image_ids()
    if not image_ids:
        pytest.skip("No neutral image IDs registered.")

    target_image_id = image_ids[0]
    id_gen = InspectionIdGenerator(start_idx=101)

    record, logs = execute_inspection_workflow(
        product_id="ABCD1541",
        image_id=target_image_id,
        registry=registry,
        id_gen=id_gen,
        storage=temp_storage,
    )

    # 1. Inspection record verification
    assert record.inspection_id == "INSP-000101"
    assert record.product_id == "ABCD1541"
    assert record.image_id == target_image_id
    assert record.status == "COMPLETED"
    assert record.result == "UNKNOWN"
    assert record.image_quality_status == "NORMAL"
    assert "mean" in record.metrics
    assert "width" in record.metrics
    assert "height" in record.metrics

    # 2. Execution log linkage and event sequence verification
    assert len(logs) >= 4
    for log in logs:
        # All logs must link strictly via the same inspection_id
        assert log.inspection_id == record.inspection_id

    event_codes = [log.event_code for log in logs]
    expected_sequence = [
        EventCode.INSPECTION_STARTED,
        EventCode.IMAGE_LOADED,
        EventCode.ANALYSIS_COMPLETED,
        EventCode.INSPECTION_COMPLETED,
    ]
    assert event_codes == expected_sequence

    # 3. Verify persistence in storage
    saved_rec = temp_storage.get_inspection("INSP-000101")
    assert saved_rec is not None
    assert saved_rec.inspection_id == "INSP-000101"

    saved_logs = temp_storage.get_logs("INSP-000101")
    assert len(saved_logs) == len(logs)
    assert [l.event_code for l in saved_logs] == expected_sequence


def test_execute_inspection_workflow_image_load_failure(temp_storage: JsonlInspectionStorage):
    """Verify that on load failure, IMAGE_LOAD_FAILED is logged and ANALYSIS_COMPLETED is NOT logged."""
    registry = ImageRegistry()  # Empty registry without mapping
    id_gen = InspectionIdGenerator(start_idx=201)

    with pytest.raises((KeyError, FileNotFoundError)):
        execute_inspection_workflow(
            product_id="ABCD1541",
            image_id="IMG-BOTTLE-NONEXISTENT",
            registry=registry,
            id_gen=id_gen,
            storage=temp_storage,
        )

    # Verify failed record and events logged
    failed_record = temp_storage.get_inspection("INSP-000201")
    assert failed_record is not None
    assert failed_record.status == "FAILED"
    assert failed_record.image_quality_status == "ERROR"

    failed_logs = temp_storage.get_logs("INSP-000201")
    event_codes = [l.event_code for l in failed_logs]

    # Required: INSPECTION_STARTED, IMAGE_LOAD_FAILED, INSPECTION_FAILED
    assert EventCode.INSPECTION_STARTED in event_codes
    assert EventCode.IMAGE_LOAD_FAILED in event_codes
    assert EventCode.INSPECTION_FAILED in event_codes

    # CRITICAL: ANALYSIS_COMPLETED must NEVER be logged when load fails
    assert EventCode.ANALYSIS_COMPLETED not in event_codes
    assert EventCode.IMAGE_LOADED not in event_codes


def test_execute_inspection_workflow_brightness_warning_isolation(temp_storage: JsonlInspectionStorage):
    """Verify low brightness triggers quality warning in logs, but product verdict remains UNKNOWN."""
    settings = get_settings()
    train_good_dir = settings.absolute_dataset_path / "train" / "good"

    if not train_good_dir.exists():
        pytest.skip("Dataset train/good not available; skipping test.")

    registry = get_image_registry(settings)
    image_ids = registry.list_image_ids()
    if not image_ids:
        pytest.skip("No neutral image IDs registered.")

    id_gen = InspectionIdGenerator(start_idx=301)

    # Force low threshold above bottle mean (~136.3) to trigger WARNING_LOW_BRIGHTNESS
    record, logs = execute_inspection_workflow(
        product_id="ABCD1541",
        image_id=image_ids[0],
        registry=registry,
        id_gen=id_gen,
        storage=temp_storage,
        low_threshold=145.0,  # Mean 136.3 < 145.0 -> Triggers low brightness warning
        high_threshold=160.0,
    )

    # Quality status is warning, but product verdict remains decoupled UNKNOWN
    assert record.image_quality_status == "WARNING_LOW_BRIGHTNESS"
    assert record.result == "UNKNOWN"

    # In logs, ANALYSIS_COMPLETED must have level WARN
    analysis_logs = [l for l in logs if l.event_code == EventCode.ANALYSIS_COMPLETED]
    assert len(analysis_logs) == 1
    assert analysis_logs[0].level == LogLevel.WARN
    assert "hardware failure not confirmed" in analysis_logs[0].message


def test_list_inspections_and_filter_by_product(temp_storage: JsonlInspectionStorage):
    """Verify list_inspections correctly filters records by product_id."""
    for idx, pid in enumerate(["PROD-A", "PROD-B", "PROD-A", "PROD-C", "PROD-A"], start=1):
        temp_storage.save_inspection(
            InspectionRecord(
                inspection_id=f"INSP-{idx:06d}",
                product_id=pid,
                timestamp=get_utc_now_iso(),
                image_id=f"IMG-BOTTLE-{idx:04d}",
                result="UNKNOWN",
                image_quality_status="NORMAL",
                metrics={},
                status="COMPLETED",
            )
        )

    all_records = temp_storage.list_inspections(limit=10)
    assert len(all_records) == 5

    prod_a_records = temp_storage.list_inspections(limit=10, product_id="PROD-A")
    assert len(prod_a_records) == 3
    for r in prod_a_records:
        assert r.product_id == "PROD-A"


def test_default_storage_integration_with_data_directory():
    """Verify get_inspection_storage connects to the configured data directory without errors."""
    storage = get_inspection_storage()
    assert isinstance(storage, JsonlInspectionStorage)
    settings = get_settings()
    assert settings.absolute_inspections_path.exists()
    assert settings.absolute_inspection_logs_path.exists()
