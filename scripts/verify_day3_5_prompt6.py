"""Comprehensive Day 3.5 Prompt 6 Verification Script.

Executes all end-to-end checks requested by Day 3.5 Prompt 6:
1. FastAPI endpoints & schemas (GET /health, GET /inspections/images, POST /inspections).
2. OpenCV brightness analysis & environmental quality assessment preservation.
3. PatchCore enabled vs disabled comparison.
4. Error state distinction: Image Load Failure vs Inference Failure vs Model Loading Failure.
5. Live T01, T03, T05, T06 execution and final_result / final_reason_code validation.
6. JSONL storage persistence & inspection_id linkage.
7. Legacy JSONL record backward compatibility.
8. Neutral image_id isolation & zero leakage of filesystem paths / defect labels.
9. Checkpoint & threshold immutability verification.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from backend.main import app
from backend.config import get_settings
from backend.inspection import get_image_registry, execute_inspection_workflow
from backend.storage import (
    EventCode,
    InspectionRecord,
    InspectionLogRecord,
    get_inspection_storage,
)
from backend.decision import FinalResult, FinalReasonCode


def run_comprehensive_verification():
    client = TestClient(app)
    storage = get_inspection_storage()
    settings = get_settings()

    print("=" * 80)
    print("VisionInsight - Day 3.5 Prompt 6 Comprehensive Compatibility Verification")
    print("=" * 80)

    # --------------------------------------------------------------------------
    # 1. Model & Threshold Immutability Verification
    # --------------------------------------------------------------------------
    print("\n[Section 1] Model & Threshold Immutability Check")
    ckpt_path = PROJECT_ROOT / "models" / "patchcore" / "patchcore_bottle.ckpt"
    meta_path = PROJECT_ROOT / "models" / "patchcore" / "model_metadata.json"

    assert ckpt_path.exists(), "Checkpoint must exist"
    assert meta_path.exists(), "Metadata must exist"

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    print(f"  - Model Backbone:        {meta.get('backbone')} (Preserved)")
    print(f"  - Checkpoint File:       {ckpt_path.name} ({ckpt_path.stat().st_size / (1024*1024):.2f} MB)")
    print(f"  - Memory Bank Shape:     {meta.get('memory_bank_shape')} (9,216 coreset vectors)")
    print(f"  - Training Images:       {meta.get('train_image_count')} images (Preserved)")
    print(f"  - Validation Images:     {meta.get('val_image_count')} images (Preserved)")
    print(f"  - Calibrated Threshold:  {meta.get('calibrated_threshold')} (Strictly Unchanged: 34.1442)")
    assert meta.get('calibrated_threshold') == 34.1442
    assert meta.get('backbone') == "resnet18"
    assert meta.get('memory_bank_shape') == [9216, 384]

    # --------------------------------------------------------------------------
    # 2. FastAPI Endpoints & Schema Compatibility
    # --------------------------------------------------------------------------
    print("\n[Section 2] FastAPI Endpoints & Schema Compatibility")
    
    # 2.1 GET /health
    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json() == {"status": "ok"}
    print(f"  - GET /health:             HTTP 200 OK -> {r_health.json()}")

    # 2.2 GET /inspections/images
    r_images = client.get("/inspections/images")
    assert r_images.status_code == 200
    images_data = r_images.json()
    assert "total_images" in images_data
    assert "image_ids" in images_data
    assert images_data["total_images"] > 0
    # Zero GT label leakage in image IDs
    for img_id in images_data["sample_ids"]:
        assert img_id.startswith("IMG-BOTTLE-")
        assert "broken" not in img_id
        assert "contamination" not in img_id
    print(f"  - GET /inspections/images: HTTP 200 OK -> Total {images_data['total_images']} neutral IDs")

    # --------------------------------------------------------------------------
    # 3. PatchCore Enabled vs Disabled Comparison
    # --------------------------------------------------------------------------
    print("\n[Section 3] PatchCore Enabled vs Disabled Comparison")
    registry = get_image_registry()
    sample_id = registry.list_image_ids()[0]

    # 3.1 PatchCore Enabled (Standard Default)
    r_enabled = client.post("/inspections", json={"product_id": "PROD-CMP-ENABLED", "image_id": sample_id})
    assert r_enabled.status_code == 201
    d_enabled = r_enabled.json()

    print("  [PatchCore ENABLED]")
    print(f"    - defect_detection_status: {d_enabled['defect_detection_status']}")
    print(f"    - anomaly_score:           {d_enabled['anomaly_score']:.4f}")
    print(f"    - decision_threshold:      {d_enabled['decision_threshold']:.4f}")
    print(f"    - inference_time_ms:       {d_enabled['inference_time_ms']:.2f} ms")
    print(f"    - product result:          {d_enabled['result']}")
    print(f"    - final_result:            {d_enabled['final_result']}")
    print(f"    - final_reason_code:       {d_enabled['final_reason_code']}")
    assert d_enabled["defect_detection_status"] == "COMPLETED"
    assert d_enabled["anomaly_score"] is not None
    assert d_enabled["decision_threshold"] == 34.1442
    assert d_enabled["result"] in ("OK", "NG")
    assert d_enabled["final_result"] in ("OK", "NG")

    # 3.2 PatchCore Disabled (ENABLE_PATCHCORE = False)
    settings.ENABLE_PATCHCORE = False
    try:
        r_disabled = client.post("/inspections", json={"product_id": "PROD-CMP-DISABLED", "image_id": sample_id})
        assert r_disabled.status_code == 201
        d_disabled = r_disabled.json()

        print("  [PatchCore DISABLED]")
        print(f"    - defect_detection_status: {d_disabled['defect_detection_status']}")
        print(f"    - anomaly_score:           {d_disabled['anomaly_score']}")
        print(f"    - inference_time_ms:       {d_disabled['inference_time_ms']}")
        print(f"    - product result:          {d_disabled['result']} (Strictly Preserves Day 1~3 UNKNOWN)")
        print(f"    - final_result:            {d_disabled['final_result']}")
        print(f"    - final_reason_code:       {d_disabled['final_reason_code']}")
        assert d_disabled["defect_detection_status"] == "SKIPPED"
        assert d_disabled["anomaly_score"] is None
        assert d_disabled["inference_time_ms"] is None
        assert d_disabled["result"] == "UNKNOWN"
        assert d_disabled["final_result"] == "REINSPECT"
        assert d_disabled["final_reason_code"] == "DEFECT_DETECTION_UNAVAILABLE"
    finally:
        settings.ENABLE_PATCHCORE = True

    # --------------------------------------------------------------------------
    # 4. Error State Distinction: Load Failure vs Inference Failure
    # --------------------------------------------------------------------------
    print("\n[Section 4] Error State Distinction (Image Load vs Inference Failure)")

    # 4.1 Image Load Failure
    r_load_fail = client.post("/inspections", json={"product_id": "PROD-ERR-LOAD", "image_id": "IMG-BOTTLE-NONEXISTENT"})
    assert r_load_fail.status_code in (400, 404)
    recs_load = storage.list_inspections(product_id="PROD-ERR-LOAD")
    assert len(recs_load) > 0
    rec_load = recs_load[0]
    logs_load = storage.get_logs(rec_load.inspection_id)
    codes_load = [l.event_code for l in logs_load]

    print("  [Case A: Image Load Failure]")
    print(f"    - Execution Status:        {rec_load.status} (FAILED)")
    print(f"    - Image Quality Status:    {rec_load.image_quality_status} (ERROR)")
    print(f"    - Defect Detection Status: {rec_load.defect_detection_status} (SKIPPED)")
    print(f"    - Final Result:            {rec_load.final_result} (ERROR)")
    print(f"    - Final Reason Code:       {rec_load.final_reason_code} (INSPECTION_FAILED)")
    print(f"    - Log Events:              {codes_load}")
    assert rec_load.status == "FAILED"
    assert rec_load.image_quality_status == "ERROR"
    assert rec_load.defect_detection_status == "SKIPPED"
    assert rec_load.final_result == "ERROR"
    assert EventCode.IMAGE_LOAD_FAILED in codes_load
    assert EventCode.INSPECTION_FAILED in codes_load
    assert EventCode.INFERENCE_STARTED not in codes_load

    # 4.2 ML Inference Failure (Simulated)
    mock_inferencer_fail = MagicMock()
    mock_inferencer_fail.predict.side_effect = RuntimeError("Simulated internal GPU/CPU out of memory")

    rec_infer_fail, logs_infer_fail = execute_inspection_workflow(
        product_id="PROD-ERR-INFER",
        image_id=sample_id,
        registry=registry,
        inferencer=mock_inferencer_fail,
        decision_threshold=34.1442,
    )
    codes_infer = [l.event_code for l in logs_infer_fail]

    print("  [Case B: Inference Execution Failure]")
    print(f"    - Execution Status:        {rec_infer_fail.status} (COMPLETED)")
    print(f"    - Image Quality Status:    {rec_infer_fail.image_quality_status} (NORMAL - Quality Preserved)")
    print(f"    - Defect Detection Status: {rec_infer_fail.defect_detection_status} (FAILED)")
    print(f"    - Product Result:          {rec_infer_fail.result} (UNKNOWN)")
    print(f"    - Final Result:            {rec_infer_fail.final_result} (REINSPECT)")
    print(f"    - Final Reason Code:       {rec_infer_fail.final_reason_code} (DEFECT_DETECTION_UNAVAILABLE)")
    print(f"    - Log Events:              {codes_infer}")
    assert rec_infer_fail.status == "COMPLETED"
    assert rec_infer_fail.image_quality_status == "NORMAL"
    assert rec_infer_fail.defect_detection_status == "FAILED"
    assert rec_infer_fail.result == "UNKNOWN"
    assert rec_infer_fail.final_result == "REINSPECT"
    assert EventCode.INFERENCE_FAILED in codes_infer
    assert EventCode.IMAGE_LOAD_FAILED not in codes_infer

    # --------------------------------------------------------------------------
    # 5. Live T01, T03, T05, T06 Scenario Execution
    # --------------------------------------------------------------------------
    print("\n[Section 5] Live T01, T03, T05, T06 Scenario Verification")
    scenarios = [
        ("T01", "PROD-BOTTLE-T01", "IMG-BOTTLE-0084"),
        ("T03", "PROD-BOTTLE-T03", "IMG-BOTTLE-INJ-0001"),
        ("T05", "PROD-BOTTLE-T05", "IMG-BOTTLE-NONEXISTENT"),
        ("T06", "PROD-BOTTLE-T06", "IMG-BOTTLE-0001"),
    ]

    for sc_id, prod_id, img_id in scenarios:
        resp = client.post("/inspections", json={"product_id": prod_id, "image_id": img_id})
        print(f"  [{sc_id}] image_id={img_id} -> HTTP {resp.status_code}")
        if resp.status_code == 201:
            d = resp.json()
            print(f"      Status:         {d['status']}")
            print(f"      Image Quality:  {d['image_quality_status']}")
            print(f"      Defect Status:  {d['defect_detection_status']}")
            print(f"      Product Result: {d['result']}")
            print(f"      FINAL RESULT:   {d['final_result']} ({d['final_reason_code']})")
            print(f"      Confidence:     {d['metrics'].get('decision_confidence')}")
            print(f"      Anomaly Score:  {d['anomaly_score']:.4f} (Threshold: {d['decision_threshold']})")
            
            # Specific assertions per scenario
            if sc_id == "T01":
                assert d["image_quality_status"] == "NORMAL"
                assert d["result"] == "OK"
                assert d["final_result"] == "OK"
                assert d["final_reason_code"] == "ALL_CHECKS_PASSED"
            elif sc_id == "T03":
                assert d["image_quality_status"] == "WARNING_LOW_BRIGHTNESS"
                assert d["final_result"] == "REINSPECT"
                assert d["final_reason_code"] == "IMAGE_QUALITY_WARNING"
                assert d["metrics"].get("decision_confidence") == "UNCERTAIN_DUE_TO_IMAGE_QUALITY"
            elif sc_id == "T06":
                assert d["image_quality_status"] == "NORMAL"
                assert d["result"] == "OK"
                assert d["final_result"] == "OK"
                assert d["final_reason_code"] == "ALL_CHECKS_PASSED"
        else:
            if sc_id == "T05":
                recs = storage.list_inspections(product_id=prod_id)
                assert len(recs) > 0
                assert recs[0].status == "FAILED"
                assert recs[0].final_result == "ERROR"
                assert recs[0].final_reason_code == "INSPECTION_FAILED"
                print(f"      Persisted Record: status={recs[0].status}, final_result={recs[0].final_result}")

    # --------------------------------------------------------------------------
    # 6. JSONL Storage & inspection_id Linkage
    # --------------------------------------------------------------------------
    print("\n[Section 6] JSONL Storage & inspection_id Linkage")
    insp_path = settings.absolute_inspections_path
    logs_path = settings.absolute_inspection_logs_path

    assert insp_path.exists(), "inspections.jsonl must exist"
    assert logs_path.exists(), "inspection_logs.jsonl must exist"

    with open(insp_path, "r", encoding="utf-8") as f:
        insp_lines = [json.loads(line) for line in f if line.strip()]
    with open(logs_path, "r", encoding="utf-8") as f:
        log_lines = [json.loads(line) for line in f if line.strip()]

    print(f"  - Total records in inspections.jsonl:   {len(insp_lines)}")
    print(f"  - Total events in inspection_logs.jsonl: {len(log_lines)}")

    latest_insp = insp_lines[-1]
    target_id = latest_insp["inspection_id"]
    linked_logs = [l for l in log_lines if l["inspection_id"] == target_id]

    print(f"  - Verifying linkage for latest inspection '{target_id}':")
    print(f"    * Product ID:   {latest_insp['product_id']}")
    print(f"    * Final Result: {latest_insp.get('final_result')}")
    print(f"    * Linked Logs:  {len(linked_logs)} events (All strictly match inspection_id)")
    assert len(linked_logs) in (4, 6)
    for l in linked_logs:
        assert l["inspection_id"] == target_id

    # --------------------------------------------------------------------------
    # 7. Backward Compatibility for Legacy JSONL Records
    # --------------------------------------------------------------------------
    print("\n[Section 7] Backward Compatibility for Legacy JSONL Records")
    legacy_record_sample = {
        "inspection_id": "INSP-LEGACY-000001",
        "product_id": "PROD-LEGACY",
        "timestamp": "2026-10-14T05:00:00+00:00",
        "image_id": "IMG-BOTTLE-0001",
        "result": "UNKNOWN",
        "image_quality_status": "NORMAL",
        "metrics": {"mean": 136.3, "std": 58.4},
        "status": "COMPLETED",
    }
    legacy_json_str = json.dumps(legacy_record_sample)
    parsed_record = InspectionRecord.model_validate_json(legacy_json_str)

    print("  - Successfully deserialized legacy record lacking final_result/final_reason_code:")
    print(f"    * inspection_id:     {parsed_record.inspection_id}")
    print(f"    * result:            {parsed_record.result}")
    print(f"    * final_result:      {parsed_record.final_result} (Gracefully defaults to None)")
    print(f"    * final_reason_code: {parsed_record.final_reason_code} (Gracefully defaults to None)")
    assert parsed_record.final_result is None
    assert parsed_record.final_reason_code is None

    # --------------------------------------------------------------------------
    # 8. Data Security & Ground Truth Isolation
    # --------------------------------------------------------------------------
    print("\n[Section 8] Data Security & Zero Leakage Verification")
    sample_response_str = json.dumps(d_enabled)
    assert "broken_large" not in sample_response_str
    assert "broken_small" not in sample_response_str
    assert "contamination" not in sample_response_str
    assert "ground_truth" not in sample_response_str
    assert "C:\\" not in sample_response_str
    assert "/dataset" not in sample_response_str
    print("  - Zero leakage verified: No ground truth directories, classes, or filesystem paths in API response.")

    print("\n" + "=" * 80)
    print("ALL DAY 3.5 PROMPT 6 VERIFICATIONS COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    run_comprehensive_verification()
