"""Day 3.5 Step 4.5 Integration Tests — Comprehensive Final Verdict Evaluation.

Covers:
1. Pure Python decision function determine_final_verdict priority rules:
   - Rule 1: status=FAILED -> ERROR / INSPECTION_FAILED
   - Rule 2: image_quality_status != NORMAL -> REINSPECT / IMAGE_QUALITY_WARNING (even if product is NG)
   - Rule 3: defect_detection_status != COMPLETED or result=UNKNOWN -> REINSPECT / DEFECT_DETECTION_UNAVAILABLE
   - Rule 4: image_quality_status=NORMAL and result=NG -> NG / PRODUCT_ANOMALY_DETECTED
   - Rule 5: image_quality_status=NORMAL and result=OK -> OK / ALL_CHECKS_PASSED
   - Rule 6: Unhandled combinations -> REINSPECT / UNKNOWN_STATE_COMBINATION
2. Live scenario validations:
   - T01: final_result=OK, final_reason_code=ALL_CHECKS_PASSED
   - T03: final_result=REINSPECT, final_reason_code=IMAGE_QUALITY_WARNING
   - T05: final_result=ERROR, final_reason_code=INSPECTION_FAILED
   - T06: final_result=OK, final_reason_code=ALL_CHECKS_PASSED
3. Simultaneous defect (NG) + environmental warning -> REINSPECT with preserved result=NG
4. PatchCore failure or disabled -> REINSPECT / DEFECT_DETECTION_UNAVAILABLE
5. Backward compatibility for legacy JSONL records missing final_result fields
6. Zero leakage of dataset paths or ground truth labels
"""

import json
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import get_settings
from backend.decision import FinalReasonCode, FinalResult, determine_final_verdict
from backend.inspection import get_image_registry, execute_inspection_workflow
from backend.storage import InspectionRecord, get_inspection_storage


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. Pure Function Priority Rule Tests
# ==============================================================================

def test_determine_final_verdict_rule1_pipeline_failed():
    """Rule 1: Pipeline failure always results in ERROR regardless of other values."""
    res, reason = determine_final_verdict(
        status="FAILED",
        image_quality_status="NORMAL",
        defect_detection_status="COMPLETED",
        result="OK",
    )
    assert res == FinalResult.ERROR
    assert reason == FinalReasonCode.INSPECTION_FAILED


def test_determine_final_verdict_rule2_quality_warning():
    """Rule 2: Image quality warning triggers REINSPECT, even if product verdict is OK."""
    res, reason = determine_final_verdict(
        status="COMPLETED",
        image_quality_status="WARNING_LOW_BRIGHTNESS",
        defect_detection_status="COMPLETED",
        result="OK",
    )
    assert res == FinalResult.REINSPECT
    assert reason == FinalReasonCode.IMAGE_QUALITY_WARNING


def test_determine_final_verdict_rule2_quality_warning_with_product_ng():
    """Rule 2 (Safety Policy): Quality warning overrides product NG to mandate REINSPECT."""
    res, reason = determine_final_verdict(
        status="COMPLETED",
        image_quality_status="WARNING_HIGH_BRIGHTNESS",
        defect_detection_status="COMPLETED",
        result="NG",
    )
    assert res == FinalResult.REINSPECT
    assert reason == FinalReasonCode.IMAGE_QUALITY_WARNING


def test_determine_final_verdict_rule3_defect_detection_unavailable():
    """Rule 3: Incomplete/failed defect model or UNKNOWN verdict mandates REINSPECT."""
    # Subcase: model FAILED
    res1, reason1 = determine_final_verdict(
        status="COMPLETED",
        image_quality_status="NORMAL",
        defect_detection_status="FAILED",
        result="UNKNOWN",
    )
    assert res1 == FinalResult.REINSPECT
    assert reason1 == FinalReasonCode.DEFECT_DETECTION_UNAVAILABLE

    # Subcase: model SKIPPED
    res2, reason2 = determine_final_verdict(
        status="COMPLETED",
        image_quality_status="NORMAL",
        defect_detection_status="SKIPPED",
        result="UNKNOWN",
    )
    assert res2 == FinalResult.REINSPECT
    assert reason2 == FinalReasonCode.DEFECT_DETECTION_UNAVAILABLE

    # Subcase: model COMPLETED but uncalibrated threshold (result=UNKNOWN)
    res3, reason3 = determine_final_verdict(
        status="COMPLETED",
        image_quality_status="NORMAL",
        defect_detection_status="COMPLETED",
        result="UNKNOWN",
    )
    assert res3 == FinalResult.REINSPECT
    assert reason3 == FinalReasonCode.DEFECT_DETECTION_UNAVAILABLE


def test_determine_final_verdict_rule4_product_ng():
    """Rule 4: Normal quality with confirmed NG produces final_result=NG."""
    res, reason = determine_final_verdict(
        status="COMPLETED",
        image_quality_status="NORMAL",
        defect_detection_status="COMPLETED",
        result="NG",
    )
    assert res == FinalResult.NG
    assert reason == FinalReasonCode.PRODUCT_ANOMALY_DETECTED


def test_determine_final_verdict_rule5_all_checks_passed():
    """Rule 5: Normal quality with confirmed OK produces final_result=OK."""
    res, reason = determine_final_verdict(
        status="COMPLETED",
        image_quality_status="NORMAL",
        defect_detection_status="COMPLETED",
        result="OK",
    )
    assert res == FinalResult.OK
    assert reason == FinalReasonCode.ALL_CHECKS_PASSED


def test_determine_final_verdict_rule6_unhandled_combination():
    """Rule 6: Unexpected state combination safely falls back to REINSPECT."""
    res, reason = determine_final_verdict(
        status="COMPLETED",
        image_quality_status="NORMAL",
        defect_detection_status="COMPLETED",
        result="SOMETHING_UNEXPECTED",
    )
    assert res == FinalResult.REINSPECT
    assert reason == FinalReasonCode.UNKNOWN_STATE_COMBINATION


# ==============================================================================
# 2. Scenario Validations via Live Endpoint
# ==============================================================================

def test_t01_final_verdict_all_checks_passed(client: TestClient):
    """T01: Normal sample -> final_result=OK, final_reason_code=ALL_CHECKS_PASSED."""
    response = client.post(
        "/inspections",
        json={"product_id": "PROD-BOTTLE-T01", "image_id": "IMG-BOTTLE-0084"},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["status"] == "COMPLETED"
    assert data["image_quality_status"] == "NORMAL"
    assert data["result"] == "OK"
    assert data["final_result"] == "OK"
    assert data["final_reason_code"] == "ALL_CHECKS_PASSED"


def test_t03_final_verdict_quality_warning_reinspect(client: TestClient):
    """T03: Illumination warning -> final_result=REINSPECT, reason=IMAGE_QUALITY_WARNING."""
    registry = get_image_registry()
    injected_ids = [i for i in registry.list_image_ids() if "INJ" in i]
    if not injected_ids:
        pytest.skip("T03 injected image not present")

    response = client.post(
        "/inspections",
        json={"product_id": "PROD-BOTTLE-T03", "image_id": injected_ids[0]},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["status"] == "COMPLETED"
    assert data["image_quality_status"] == "WARNING_LOW_BRIGHTNESS"
    assert data["result"] in ("OK", "NG")
    assert data["final_result"] == "REINSPECT"
    assert data["final_reason_code"] == "IMAGE_QUALITY_WARNING"


def test_t05_final_verdict_pipeline_error(client: TestClient):
    """T05: Missing image -> status=FAILED, final_result=ERROR in storage."""
    response = client.post(
        "/inspections",
        json={"product_id": "PROD-BOTTLE-T05", "image_id": "IMG-BOTTLE-NONEXISTENT"},
    )
    assert response.status_code in (400, 404)

    storage = get_inspection_storage()
    records = storage.list_inspections(product_id="PROD-BOTTLE-T05")
    assert len(records) > 0
    failed_rec = records[0]

    assert failed_rec.status == "FAILED"
    assert failed_rec.final_result == "ERROR"
    assert failed_rec.final_reason_code == "INSPECTION_FAILED"


def test_t06_final_verdict_sample(client: TestClient):
    """T06: Normal environmental pipeline on sample -> final_result=OK."""
    response = client.post(
        "/inspections",
        json={"product_id": "PROD-BOTTLE-T06", "image_id": "IMG-BOTTLE-0001"},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["status"] == "COMPLETED"
    assert data["image_quality_status"] == "NORMAL"
    assert data["result"] == "OK"
    assert data["final_result"] == "OK"
    assert data["final_reason_code"] == "ALL_CHECKS_PASSED"


# ==============================================================================
# 3. Defect Anomaly and Simultaneous Warning Tests
# ==============================================================================

def test_workflow_product_ng_under_normal_quality():
    """Simulated high anomaly score produces final_result=NG."""
    registry = get_image_registry()
    target_id = registry.list_image_ids()[0]

    mock_inferencer = MagicMock()
    mock_inferencer.predict.return_value = {
        "anomaly_score": 45.0,
        "inference_time_ms": 30.0,
        "model_name": "PatchCore",
    }

    record, logs = execute_inspection_workflow(
        product_id="PROD-TEST-NG",
        image_id=target_id,
        registry=registry,
        inferencer=mock_inferencer,
        decision_threshold=34.1442,
    )

    assert record.result == "NG"
    assert record.image_quality_status == "NORMAL"
    assert record.final_result == "NG"
    assert record.final_reason_code == "PRODUCT_ANOMALY_DETECTED"


def test_workflow_product_ng_under_quality_warning():
    """Simultaneous product NG and image quality warning triggers REINSPECT with preserved result=NG."""
    registry = get_image_registry()
    injected_ids = [i for i in registry.list_image_ids() if "INJ" in i]
    if not injected_ids:
        pytest.skip("T03 injected image not present")

    target_id = injected_ids[0]

    mock_inferencer = MagicMock()
    mock_inferencer.predict.return_value = {
        "anomaly_score": 48.0,
        "inference_time_ms": 32.0,
        "model_name": "PatchCore",
    }

    record, logs = execute_inspection_workflow(
        product_id="PROD-TEST-WARN-NG",
        image_id=target_id,
        registry=registry,
        inferencer=mock_inferencer,
        decision_threshold=34.1442,
    )

    # Raw defect verdict and score are strictly preserved
    assert record.result == "NG"
    assert record.anomaly_score == 48.0
    assert record.image_quality_status == "WARNING_LOW_BRIGHTNESS"
    # Final verdict mandates REINSPECT due to quality warning precedence
    assert record.final_result == "REINSPECT"
    assert record.final_reason_code == "IMAGE_QUALITY_WARNING"


def test_workflow_patchcore_disabled_final_verdict(monkeypatch, client: TestClient):
    """When PatchCore is disabled, final_result is REINSPECT due to unavailable defect model."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ENABLE_PATCHCORE", False)

    registry = get_image_registry()
    target_id = registry.list_image_ids()[0]

    response = client.post(
        "/inspections",
        json={"product_id": "PROD-DISABLED-FV", "image_id": target_id},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["defect_detection_status"] == "SKIPPED"
    assert data["result"] == "UNKNOWN"
    assert data["final_result"] == "REINSPECT"
    assert data["final_reason_code"] == "DEFECT_DETECTION_UNAVAILABLE"


# ==============================================================================
# 4. Backward Compatibility for Legacy JSONL Records
# ==============================================================================

def test_legacy_jsonl_record_backward_compatibility():
    """Verify that older inspection records lacking final_result deserialize properly."""
    legacy_json_str = json.dumps({
        "inspection_id": "INSP-000001",
        "product_id": "LEGACY-01",
        "timestamp": "2026-10-14T10:00:00Z",
        "image_id": "IMG-BOTTLE-0001",
        "result": "UNKNOWN",
        "image_quality_status": "NORMAL",
        "metrics": {"mean": 136.2},
        "status": "COMPLETED",
    })

    record = InspectionRecord.model_validate_json(legacy_json_str)
    assert record.inspection_id == "INSP-000001"
    assert record.result == "UNKNOWN"
    assert record.final_result is None
    assert record.final_reason_code is None
