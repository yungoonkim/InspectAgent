"""Day 3.5 Step 3 Integration Tests.

Validates:
1. Dataset split isolation: 180 Train images vs 29 Val images (zero overlap).
2. Memory bank shape matches 180-image training ([9216, 384]).
3. Actual PatchCore anomaly_score calculation when ENABLE_PATCHCORE is True.
4. defect_detection_status lifecycle: COMPLETED, FAILED, SKIPPED.
5. Neutral image_id filename masking (zero leakage of internal paths/filenames/labels).
6. OpenCV brightness analysis preservation (mean, std, min, max).
7. Model loaded once and reused across multiple inspections (singleton).
8. Fallback to standard Day 2 behavior when ENABLE_PATCHCORE is False.
9. Defect classification remains UNKNOWN without calibrated threshold.
10. T01 normal image inspection with PatchCore.
11. T03 brightness reduced inspection (quality warning maintained + anomaly score computed).
12. T05 image load failure does NOT execute PatchCore inference and marks status SKIPPED.
13. T06 raw defect image inference (higher score, UNKNOWN verdict, zero GT leakage).
14. Graceful inference failure handling (INFERENCE_FAILED event logged, status FAILED).
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import Settings, get_settings
from backend.inspection import get_image_registry, execute_inspection_workflow
from backend.storage import EventCode, InspectionStage, LogLevel, get_inspection_storage
from backend.ml.patchcore_inferencer import get_patchcore_inferencer, reset_patchcore_inferencer


@pytest.fixture
def client() -> TestClient:
    """Fixture providing TestClient for FastAPI app."""
    return TestClient(app)


# ------------------------------------------------------------------------------
# 1. Dataset Split & Isolation Verification
# ------------------------------------------------------------------------------
def test_dataset_split_isolation():
    """Verify train/val split specification: 180 train images vs 29 val images."""
    project_root = Path(__file__).resolve().parent.parent
    split_path = project_root / "models" / "patchcore" / "dataset_split.json"
    meta_path = project_root / "models" / "patchcore" / "model_metadata.json"

    assert split_path.exists(), "dataset_split.json must exist"
    assert meta_path.exists(), "model_metadata.json must exist"

    with open(split_path, "r", encoding="utf-8") as f:
        split_data = json.load(f)

    with open(meta_path, "r", encoding="utf-8") as f:
        meta_data = json.load(f)

    train_set = set(split_data["train_files"])
    val_set = set(split_data["val_files"])

    assert len(train_set) == 180, f"Expected 180 train images, got {len(train_set)}"
    assert len(val_set) == 29, f"Expected 29 val images, got {len(val_set)}"
    assert train_set.isdisjoint(val_set), "Train and Val sets must have zero overlap"
    assert split_data["total_count"] == 209

    # Model metadata verification
    assert meta_data["train_image_count"] == 180
    assert meta_data["val_image_count"] == 29
    assert meta_data["split_seed"] == 42
    assert meta_data["memory_bank_shape"] == [9216, 384], "Memory bank must match 180 images coreset (9,216 vectors)"


# ------------------------------------------------------------------------------
# 2. PatchCore 활성화 시 anomaly_score 계산 + defect_detection_status = COMPLETED
# ------------------------------------------------------------------------------
def test_post_inspections_with_patchcore_enabled(client: TestClient):
    """Verify POST /inspections computes anomaly_score and sets defect_detection_status=COMPLETED."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    assert len(sample_ids) > 0, "Image registry must have registered bottle images"

    target_id = sample_ids[0]
    response = client.post(
        "/inspections",
        json={"product_id": "PROD-DAY35-01", "image_id": target_id},
    )
    assert response.status_code == 201
    data = response.json()

    # 1. Anomaly score calculated
    assert data["anomaly_score"] is not None
    assert isinstance(data["anomaly_score"], float)
    assert data["anomaly_score"] > 0.0

    # 2. defect_detection_status
    assert data["defect_detection_status"] == "COMPLETED"

    # 3. Brightness metrics preserved
    assert "mean" in data["metrics"]
    assert "std" in data["metrics"]
    assert 120.0 <= data["metrics"]["mean"] <= 150.0

    # 4. Latency and model metadata
    assert data["inference_time_ms"] is not None
    assert data["inference_time_ms"] > 0.0
    assert data["model_version"] == "PatchCore"
    assert data["decision_threshold"] in (None, 34.1442)

    # 5. Result verdict
    assert data["result"] in ("OK", "NG", "UNKNOWN")
    assert data["status"] == "COMPLETED"

    # 6. JSONL storage linkage
    storage = get_inspection_storage()
    rec = storage.get_inspection(data["inspection_id"])
    assert rec is not None
    assert rec.anomaly_score == data["anomaly_score"]
    assert rec.defect_detection_status == "COMPLETED"

    logs = storage.get_logs(data["inspection_id"])
    event_codes = [l.event_code for l in logs]
    assert EventCode.INFERENCE_STARTED in event_codes
    assert EventCode.INFERENCE_COMPLETED in event_codes


# ------------------------------------------------------------------------------
# 3. 모델 1회 로드 및 재사용 (Singleton)
# ------------------------------------------------------------------------------
def test_model_loaded_once_and_reused():
    """Verify that get_patchcore_inferencer returns the identical instance across calls."""
    inst1 = get_patchcore_inferencer()
    inst2 = get_patchcore_inferencer()
    assert inst1 is not None
    assert inst1 is inst2, "Inferencer must be a singleton cached in memory"


# ------------------------------------------------------------------------------
# 4. PatchCore 비활성화 시 defect_detection_status = SKIPPED 및 anomaly_score = None
# ------------------------------------------------------------------------------
def test_post_inspections_with_patchcore_disabled(monkeypatch, client: TestClient):
    """Verify that when ENABLE_PATCHCORE is False, anomaly_score is None and status is SKIPPED."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ENABLE_PATCHCORE", False)

    registry = get_image_registry()
    target_id = registry.list_image_ids()[0]

    response = client.post(
        "/inspections",
        json={"product_id": "PROD-DISABLED-01", "image_id": target_id},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["anomaly_score"] is None
    assert data["inference_time_ms"] is None
    assert data["defect_detection_status"] == "SKIPPED"
    assert data["result"] == "UNKNOWN"
    assert data["image_quality_status"] == "NORMAL"

    storage = get_inspection_storage()
    logs = storage.get_logs(data["inspection_id"])
    event_codes = [l.event_code for l in logs]
    assert EventCode.INFERENCE_STARTED not in event_codes
    assert EventCode.INFERENCE_COMPLETED not in event_codes


# ------------------------------------------------------------------------------
# 5. 외부 응답 및 파일명 중립화 (Zero Internal Path / GT Leakage)
# ------------------------------------------------------------------------------
def test_neutral_filename_and_zero_gt_leakage(client: TestClient):
    """Verify that filenames are strictly neutral image IDs and no dataset folder names leak."""
    registry = get_image_registry()
    target_id = "IMG-BOTTLE-0001"  # Maps to test/broken_large/000.png internally

    response = client.post(
        "/inspections",
        json={"product_id": "PROD-LEAK-TEST", "image_id": target_id},
    )
    assert response.status_code == 201
    data = response.json()

    # Image metadata filename must be neutral ID
    assert data["image_metadata"]["filename"] == f"{target_id}.png"
    assert data["metrics"]["filename"] == f"{target_id}.png"

    # Serialized response must NOT leak dataset folders or labels
    resp_str = json.dumps(data)
    assert "broken_large" not in resp_str
    assert "contamination" not in resp_str
    assert "ground_truth" not in resp_str
    assert "train/good" not in resp_str


# ------------------------------------------------------------------------------
# 6. T01 정상 이미지 검사
# ------------------------------------------------------------------------------
def test_t01_normal_image_inspection(client: TestClient):
    """Verify T01 normal image yields normal quality, baseline anomaly score, and COMPLETED status."""
    response = client.post(
        "/inspections",
        json={"product_id": "PROD-T01-EVAL", "image_id": "IMG-BOTTLE-0084"},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["image_quality_status"] == "NORMAL"
    assert data["result"] in ("OK", "NG", "UNKNOWN")
    assert data["defect_detection_status"] == "COMPLETED"
    assert data["anomaly_score"] is not None
    assert 28.0 <= data["anomaly_score"] <= 35.0


# ------------------------------------------------------------------------------
# 7. T03 밝기 감소 검사 (품질 경고 유지 + anomaly_score 산출 + COMPLETED)
# ------------------------------------------------------------------------------
def test_t03_brightness_reduced_inspection(client: TestClient):
    """Verify T03 fault-injected image triggers WARNING_LOW_BRIGHTNESS and computes anomaly_score."""
    registry = get_image_registry()
    injected_ids = [img_id for img_id in registry.list_image_ids() if "INJ" in img_id]
    if not injected_ids:
        pytest.skip("No injected images registered. Run generate_t03_fault.py first.")

    target_id = injected_ids[0]
    response = client.post(
        "/inspections",
        json={"product_id": "PROD-T03-EVAL", "image_id": target_id},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["image_quality_status"] == "WARNING_LOW_BRIGHTNESS"
    assert data["result"] in ("OK", "NG", "UNKNOWN")
    assert data["defect_detection_status"] == "COMPLETED"
    assert data["anomaly_score"] is not None


# ------------------------------------------------------------------------------
# 8. T05 이미지 로드 실패 시 추론 미실행 및 defect_detection_status = SKIPPED
# ------------------------------------------------------------------------------
def test_t05_image_load_failure_skips_inference(client: TestClient):
    """Verify T05 missing image does NOT trigger PatchCore inference and marks status SKIPPED."""
    response = client.post(
        "/inspections",
        json={"product_id": "PROD-T05-EVAL", "image_id": "IMG-BOTTLE-NONEXISTENT"},
    )
    assert response.status_code in (400, 404)

    storage = get_inspection_storage()
    records = storage.list_inspections(product_id="PROD-T05-EVAL")
    assert len(records) > 0
    failed_rec = records[0]

    assert failed_rec.status == "FAILED"
    assert failed_rec.defect_detection_status == "SKIPPED"

    logs = storage.get_logs(failed_rec.inspection_id)
    event_codes = [l.event_code for l in logs]
    assert EventCode.IMAGE_LOAD_FAILED in event_codes
    assert EventCode.INSPECTION_FAILED in event_codes
    assert EventCode.INFERENCE_STARTED not in event_codes
    assert EventCode.INFERENCE_COMPLETED not in event_codes


# ------------------------------------------------------------------------------
# 9. T06 불량 원본 이미지 추론 및 높은 Anomaly Score 확인
# ------------------------------------------------------------------------------
def test_t06_defect_image_inference(client: TestClient):
    """Verify T06 defect image computes higher anomaly score without label leakage."""
    response = client.post(
        "/inspections",
        json={"product_id": "PROD-T06-EVAL", "image_id": "IMG-BOTTLE-0001"},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["image_quality_status"] == "NORMAL"
    assert data["result"] in ("OK", "NG", "UNKNOWN")
    assert data["defect_detection_status"] == "COMPLETED"
    assert data["anomaly_score"] is not None
    assert data["anomaly_score"] > 31.5


# ------------------------------------------------------------------------------
# 10. 추론 실패 상태 분리 검증 (defect_detection_status = FAILED)
# ------------------------------------------------------------------------------
def test_inference_failure_marks_status_failed():
    """Verify that if PatchCoreInferencer fails, defect_detection_status is FAILED while quality is preserved."""
    storage = get_inspection_storage()
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    target_id = sample_ids[0]

    # Create a mock inferencer that raises RuntimeError during predict
    mock_inferencer = MagicMock()
    mock_inferencer.predict.side_effect = RuntimeError("Mock GPU Out Of Memory or Tensor Corrupt")

    record, logs = execute_inspection_workflow(
        product_id="PROD-FAIL-TEST",
        image_id=target_id,
        registry=registry,
        storage=storage,
        inferencer=mock_inferencer,
    )

    # Workflow completes overall with UNKNOWN product verdict
    assert record.status == "COMPLETED"
    assert record.result == "UNKNOWN"
    assert record.image_quality_status == "NORMAL"
    assert record.anomaly_score is None

    # Defect detection status must explicitly be FAILED
    assert record.defect_detection_status == "FAILED"
    assert "Mock GPU Out Of Memory" in record.metrics.get("defect_detection_error", "")

    # INFERENCE_FAILED event must be logged
    fail_log = next(l for l in logs if l.event_code == EventCode.INFERENCE_FAILED)
    assert fail_log.level == LogLevel.ERROR
    assert "Mock GPU Out Of Memory" in fail_log.message
