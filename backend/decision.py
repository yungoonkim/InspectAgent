"""Comprehensive industrial vision inspection decision logic.

Decouples and aggregates workflow execution status, environmental image quality,
and machine learning anomaly classification into a single authoritative final verdict.
"""

from typing import Optional, Tuple


class FinalResult:
    """Authoritative decision outcomes for industrial vision inspection."""
    OK = "OK"
    NG = "NG"
    REINSPECT = "REINSPECT"
    ERROR = "ERROR"


class FinalReasonCode:
    """Standardized root-cause reason codes for the final verdict."""
    INSPECTION_FAILED = "INSPECTION_FAILED"
    IMAGE_QUALITY_WARNING = "IMAGE_QUALITY_WARNING"
    DEFECT_DETECTION_UNAVAILABLE = "DEFECT_DETECTION_UNAVAILABLE"
    PRODUCT_ANOMALY_DETECTED = "PRODUCT_ANOMALY_DETECTED"
    ALL_CHECKS_PASSED = "ALL_CHECKS_PASSED"
    UNKNOWN_STATE_COMBINATION = "UNKNOWN_STATE_COMBINATION"


def determine_final_verdict(
    status: str,
    image_quality_status: str,
    defect_detection_status: Optional[str],
    result: str,
) -> Tuple[str, str]:
    """Pure decision function evaluating comprehensive inspection outcome.

    Priority Hierarchy:
    -------------------
    1. Pipeline Failure:
       status == "FAILED"
       -> final_result = ERROR, final_reason_code = INSPECTION_FAILED

    2. Environmental Acquisition Warning / Degradation:
       image_quality_status != "NORMAL"
       -> final_result = REINSPECT, final_reason_code = IMAGE_QUALITY_WARNING
       * MVP Safety Policy: If image quality is compromised, even a defect (NG) verdict
         must trigger REINSPECT to re-acquire clear imagery under standard lighting,
         while strictly preserving the original raw result="NG" and anomaly_score.

    3. ML Defect Detection Model Unavailable or Uncalibrated:
       defect_detection_status != "COMPLETED" or result == "UNKNOWN"
       -> final_result = REINSPECT, final_reason_code = DEFECT_DETECTION_UNAVAILABLE

    4. Confirmed Product Anomaly under Normal Environmental Quality:
       image_quality_status == "NORMAL" and result == "NG"
       -> final_result = NG, final_reason_code = PRODUCT_ANOMALY_DETECTED

    5. All Environmental and ML Checks Passed:
       image_quality_status == "NORMAL" and result == "OK"
       -> final_result = OK, final_reason_code = ALL_CHECKS_PASSED

    6. Undefined / Unhandled State Combination Fallback:
       -> final_result = REINSPECT, final_reason_code = UNKNOWN_STATE_COMBINATION
    """
    # Priority 1: System execution error or abort
    if status == "FAILED":
        return FinalResult.ERROR, FinalReasonCode.INSPECTION_FAILED

    # Priority 2: Environmental image acquisition warning (illumination, blur, etc.)
    if image_quality_status != "NORMAL":
        return FinalResult.REINSPECT, FinalReasonCode.IMAGE_QUALITY_WARNING

    # Priority 3: Defect model skipped, failed, or uncalibrated UNKNOWN
    if defect_detection_status != "COMPLETED" or result == "UNKNOWN":
        return FinalResult.REINSPECT, FinalReasonCode.DEFECT_DETECTION_UNAVAILABLE

    # Priority 4: Verified defect under normal image quality
    if result == "NG":
        return FinalResult.NG, FinalReasonCode.PRODUCT_ANOMALY_DETECTED

    # Priority 5: Full verification success
    if result == "OK":
        return FinalResult.OK, FinalReasonCode.ALL_CHECKS_PASSED

    # Priority 6: Defensive fallback
    return FinalResult.REINSPECT, FinalReasonCode.UNKNOWN_STATE_COMBINATION
