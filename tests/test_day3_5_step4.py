"""Day 3.5 Step 4 Tests — Threshold Calibration, Product Verdict (OK/NG/UNKNOWN),

and Test Dataset Quantitative Evaluation Verification.

Covers:
1. 29 validation images anomaly_score statistics and calibrated threshold (34.1442).
2. Product OK/NG decision logic: score > threshold -> NG, score <= threshold -> OK.
3. Fallback to UNKNOWN when DECISION_THRESHOLD is None or PatchCore is disabled.
4. Image quality WARNING decision policy (confidence: UNCERTAIN_DUE_TO_IMAGE_QUALITY).
5. Neutral image_id filename masking and sanitized error messages (zero path leakage).
6. Test evaluation metrics persistence in JSON and Markdown.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import get_settings
from backend.inspection import get_image_registry, _sanitize_error_message, execute_inspection_workflow
from backend.storage import EventCode, LogLevel, get_inspection_storage


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_validation_statistics_and_calibrated_threshold():
    """Verify calibrated threshold (34.1442) and statistics from 29 validation images."""
    project_root = Path(__file__).resolve().parent.parent
    meta_path = project_root / "models" / "patchcore" / "model_metadata.json"
    assert meta_path.exists(), "model_metadata.json must exist"

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["train_image_count"] == 180
    assert meta["val_image_count"] == 29
    assert meta["calibrated_threshold"] == pytest.approx(34.1442, rel=1e-3)

    calib = meta.get("calibration", {})
    assert calib["selected_threshold"] == pytest.approx(34.1442, rel=1e-3)
    val_stats = calib.get("score_distribution", {})
    assert 30.5 <= val_stats["mean"] <= 31.5
    assert 0.8 <= val_stats["std"] <= 1.3
    assert val_stats["min"] < val_stats["mean"] < val_stats["max"]
    assert "statistical_limitations" in calib


def test_product_verdict_ok_when_score_below_threshold(client: TestClient):
    """Verify product result is OK when anomaly_score <= decision_threshold."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    target_id = sample_ids[0]

    response = client.post(
        "/inspections",
        json={"product_id": "PROD-STEP4-OK", "image_id": target_id},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["defect_detection_status"] == "COMPLETED"
    assert data["decision_threshold"] == pytest.approx(34.1442, rel=1e-3)
    assert data["anomaly_score"] <= data["decision_threshold"]
    assert data["result"] == "OK"
    assert data["metrics"]["decision_confidence"] == "HIGH"


def test_product_verdict_ng_when_score_exceeds_threshold():
    """Verify simulated high anomaly score produces NG verdict."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    target_id = sample_ids[0]

    # Mock inferencer that returns a high anomaly score
    mock_inferencer = MagicMock()
    mock_inferencer.predict.return_value = {
        "anomaly_score": 42.50,
        "inference_time_ms": 35.0,
        "model_name": "PatchCore_ResNet18",
    }

    record, logs = execute_inspection_workflow(
        product_id="PROD-SIMULATE-NG",
        image_id=target_id,
        registry=registry,
        inferencer=mock_inferencer,
        decision_threshold=34.1442,
    )

    assert record.result == "NG"
    assert record.anomaly_score == 42.50
    assert record.metrics["decision_confidence"] == "HIGH"
    assert record.metrics["defect_detection_status"] == "COMPLETED"


def test_fallback_to_unknown_when_threshold_is_none(monkeypatch, client: TestClient):
    """Verify result falls back to UNKNOWN when DECISION_THRESHOLD is None."""
    settings = get_settings()
    monkeypatch.setattr(settings, "DECISION_THRESHOLD", None)

    registry = get_image_registry()
    target_id = registry.list_image_ids()[0]

    response = client.post(
        "/inspections",
        json={"product_id": "PROD-NONE-THRESH", "image_id": target_id},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["defect_detection_status"] == "COMPLETED"
    assert data["decision_threshold"] is None
    assert data["result"] == "UNKNOWN"
    assert data["metrics"]["decision_confidence"] == "NOT_APPLICABLE"


def test_fallback_to_unknown_when_patchcore_disabled(monkeypatch, client: TestClient):
    """Verify result remains UNKNOWN when ENABLE_PATCHCORE is False."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ENABLE_PATCHCORE", False)

    registry = get_image_registry()
    target_id = registry.list_image_ids()[0]

    response = client.post(
        "/inspections",
        json={"product_id": "PROD-DISABLED", "image_id": target_id},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["defect_detection_status"] == "SKIPPED"
    assert data["anomaly_score"] is None
    assert data["result"] == "UNKNOWN"


def test_image_quality_warning_decision_confidence_policy(client: TestClient):
    """Verify that quality warning marks decision_confidence as UNCERTAIN_DUE_TO_IMAGE_QUALITY."""
    registry = get_image_registry()
    injected_ids = [i for i in registry.list_image_ids() if "INJ" in i]
    if not injected_ids:
        pytest.skip("No fault-injected images found")

    target_id = injected_ids[0]
    response = client.post(
        "/inspections",
        json={"product_id": "PROD-QUALITY-WARN", "image_id": target_id},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["image_quality_status"] == "WARNING_LOW_BRIGHTNESS"
    assert data["result"] in ("OK", "NG")
    assert data["metrics"]["decision_confidence"] == "UNCERTAIN_DUE_TO_IMAGE_QUALITY"

    # Verify log record has WARN level for inspection completion
    storage = get_inspection_storage()
    logs = storage.get_logs(data["inspection_id"])
    comp_logs = [l for l in logs if l.event_code == EventCode.INSPECTION_COMPLETED]
    assert len(comp_logs) == 1
    assert comp_logs[0].level == LogLevel.WARN


def test_error_message_sanitization():
    """Verify _sanitize_error_message strips local file paths and internal ground truth paths."""
    sensitive_err1 = Exception("Failed at C:\\Users\\USER\\dataset\\bottle\\ground_truth\\broken_large\\000_mask.png")
    sanitized1 = _sanitize_error_message(sensitive_err1)
    assert "C:\\Users" not in sanitized1
    assert "ground_truth" not in sanitized1
    assert "broken_large" not in sanitized1
    assert "Exception: An internal error occurred during ML inference processing." == sanitized1

    safe_err = ValueError("Invalid tensor dimension")
    sanitized2 = _sanitize_error_message(safe_err)
    assert sanitized2 == "ValueError: Invalid tensor dimension"


def test_evaluation_artifacts_exist_and_consistent():
    """Verify 83-sample evaluation metrics JSON and Markdown reports are generated properly."""
    project_root = Path(__file__).resolve().parent.parent
    json_path = project_root / "models" / "patchcore" / "evaluation_metrics.json"
    md_path = project_root / "docs" / "evaluation-results.md"

    assert json_path.exists(), "evaluation_metrics.json must exist"
    assert md_path.exists(), "docs/evaluation-results.md must exist"

    with open(json_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert metrics["test_image_count"] == 83
    assert metrics["confusion_matrix"]["TN"] == 20
    assert metrics["confusion_matrix"]["FP"] == 0
    assert metrics["confusion_matrix"]["FN"] == 31
    assert metrics["confusion_matrix"]["TP"] == 32
    assert metrics["performance"]["image_auroc"] == pytest.approx(0.8286, rel=1e-3)
    assert metrics["performance"]["precision"] == 1.0
    assert metrics["performance"]["specificity"] == 1.0
    assert metrics["performance"]["recall"] == pytest.approx(0.5079, rel=1e-3)
    assert metrics["performance"]["f1_score"] == pytest.approx(0.6737, rel=1e-3)
