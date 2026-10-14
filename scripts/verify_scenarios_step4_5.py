"""Verify T01, T03, T05, T06 final_result and JSONL persistence."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from backend.main import app
from backend.storage import get_inspection_storage

def verify_step4_5():
    client = TestClient(app)
    storage = get_inspection_storage()

    scenarios = [
        ("T01 (Normal Image)", "PROD-BOTTLE-T01", "IMG-BOTTLE-0084"),
        ("T03 (Illumination Warning)", "PROD-BOTTLE-T03", "IMG-BOTTLE-INJ-0001"),
        ("T05 (Image Load Failure)", "PROD-BOTTLE-T05", "IMG-BOTTLE-NONEXISTENT"),
        ("T06 (Raw Defect Image)", "PROD-BOTTLE-T06", "IMG-BOTTLE-0001"),
    ]

    print("=" * 80)
    print("Step 4.5 Scenario Verification (final_result & final_reason_code)")
    print("=" * 80)

    for name, prod_id, img_id in scenarios:
        resp = client.post("/inspections", json={"product_id": prod_id, "image_id": img_id})
        print(f"\n[Scenario: {name}] (HTTP Status: {resp.status_code})")
        if resp.status_code == 201:
            data = resp.json()
            insp_id = data["inspection_id"]
            print(f"  Inspection ID:           {insp_id}")
            print(f"  Execution Status:        {data.get('status')}")
            print(f"  Image Quality Status:    {data.get('image_quality_status')}")
            print(f"  Defect Detection Status: {data.get('defect_detection_status')}")
            print(f"  Product Result:          {data.get('result')}")
            print(f"  FINAL RESULT:            {data.get('final_result')}")
            print(f"  FINAL REASON CODE:       {data.get('final_reason_code')}")
            print(f"  Decision Confidence:     {data.get('metrics', {}).get('decision_confidence')}")
            print(f"  Anomaly Score:           {data.get('anomaly_score')}")

            # Verify storage record
            rec = storage.get_inspection(insp_id)
            assert rec is not None
            assert rec.final_result == data.get("final_result")
            assert rec.final_reason_code == data.get("final_reason_code")
            print(f"  Storage JSONL Record:    MATCH (final_result={rec.final_result})")
        else:
            print(f"  Error Detail:            {resp.json()}")
            records = storage.list_inspections(product_id=prod_id)
            if records:
                rec = records[0]
                print(f"  Persisted Failure Record:")
                print(f"    Inspection ID:         {rec.inspection_id}")
                print(f"    Execution Status:      {rec.status}")
                print(f"    Image Quality Status:  {rec.image_quality_status}")
                print(f"    Product Result:        {rec.result}")
                print(f"    FINAL RESULT:          {rec.final_result}")
                print(f"    FINAL REASON CODE:     {rec.final_reason_code}")

if __name__ == "__main__":
    verify_step4_5()
