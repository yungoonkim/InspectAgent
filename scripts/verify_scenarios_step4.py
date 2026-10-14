import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from backend.main import app

def verify_scenarios():
    client = TestClient(app)

    scenarios = [
        ("T01 (Normal Image)", "PROD-BOTTLE-T01", "IMG-BOTTLE-0084"),
        ("T03 (Illumination Warning)", "PROD-BOTTLE-T03", "IMG-BOTTLE-INJ-0001"),
        ("T05 (Image Load Failure)", "PROD-BOTTLE-T05", "IMG-BOTTLE-NONEXISTENT"),
        ("T06 (Raw Defect Image)", "PROD-BOTTLE-T06", "IMG-BOTTLE-0001"),
    ]

    for name, prod_id, img_id in scenarios:
        resp = client.post("/inspections", json={"product_id": prod_id, "image_id": img_id})
        print(f"\n========================================================")
        print(f"Scenario: {name}")
        print(f"Status Code: {resp.status_code}")
        print(f"========================================================")
        if resp.status_code == 201:
            data = resp.json()
            print(f"  Inspection ID:           {data.get('inspection_id')}")
            print(f"  Product ID:              {data.get('product_id')}")
            print(f"  Image ID:                {data.get('image_id')}")
            print(f"  Product Result:          {data.get('result')}")
            print(f"  Image Quality Status:    {data.get('image_quality_status')}")
            print(f"  Defect Detection Status: {data.get('defect_detection_status')}")
            print(f"  Anomaly Score:           {data.get('anomaly_score')}")
            print(f"  Decision Threshold:      {data.get('decision_threshold')}")
            print(f"  Inference Latency:       {data.get('inference_time_ms')} ms")
            print(f"  Decision Confidence:     {data.get('metrics', {}).get('decision_confidence')}")
            print(f"  Filename Masked:         {data.get('metrics', {}).get('filename')}")
        else:
            print(f"  Error Detail:            {resp.json()}")

if __name__ == "__main__":
    verify_scenarios()
