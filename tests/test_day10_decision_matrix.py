import pytest

from backend.decision import FinalReasonCode, FinalResult, determine_final_verdict


@pytest.mark.parametrize(
    ("status", "quality", "model_status", "result", "expected"),
    [
        ("COMPLETED", "NORMAL", "COMPLETED", "OK", (FinalResult.OK, FinalReasonCode.ALL_CHECKS_PASSED)),
        ("COMPLETED", "NORMAL", "COMPLETED", "NG", (FinalResult.NG, FinalReasonCode.PRODUCT_ANOMALY_DETECTED)),
        ("COMPLETED", "WARNING_LOW_BRIGHTNESS", "COMPLETED", "OK", (FinalResult.REINSPECT, FinalReasonCode.IMAGE_QUALITY_WARNING)),
        ("COMPLETED", "WARNING_LOW_BRIGHTNESS", "COMPLETED", "NG", (FinalResult.REINSPECT, FinalReasonCode.IMAGE_QUALITY_WARNING)),
        ("COMPLETED", "NORMAL", "SKIPPED", "UNKNOWN", (FinalResult.REINSPECT, FinalReasonCode.DEFECT_DETECTION_UNAVAILABLE)),
        ("COMPLETED", "NORMAL", "FAILED", "UNKNOWN", (FinalResult.REINSPECT, FinalReasonCode.DEFECT_DETECTION_UNAVAILABLE)),
        ("FAILED", "NORMAL", "FAILED", "UNKNOWN", (FinalResult.ERROR, FinalReasonCode.INSPECTION_FAILED)),
        ("COMPLETED", "NORMAL", "COMPLETED", "UNEXPECTED", (FinalResult.REINSPECT, FinalReasonCode.UNKNOWN_STATE_COMBINATION)),
    ],
)
def test_authoritative_decision_matrix(status, quality, model_status, result, expected):
    assert determine_final_verdict(status, quality, model_status, result) == expected
