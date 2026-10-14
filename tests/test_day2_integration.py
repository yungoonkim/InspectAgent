"""Day 2 - Step 4 Comprehensive Integration Verification Test Suite.

Validates end-to-end functionality across FastAPI, OpenCV brightness analysis,
and JSONL record and execution log persistence according to the 12 required items:
1. GET /health response ok
2. Normal Bottle POST /inspections success
3. Mean brightness and std returned with actual numeric values
4. inspections.jsonl record successfully persisted
5. inspection_logs.jsonl event logs successfully persisted
6. Matching inspection_id confirmed across both JSONL files
7. Two consecutive inspections of identical image yield distinct inspection_ids
8. Simulated server restart generates non-colliding new IDs continuing from storage
9. Image load failure produces HTTP error and failure logs without spurious events
10. All lines across generated JSONL files parse validly as standalone JSON
11. Product defect result (UNKNOWN) decoupled from environmental image_quality_status
12. Concurrent inspection requests maintain thread-safety without line corruption or interleaving
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import get_settings
from backend.inspection import (
    InspectionIdGenerator,
    get_image_registry,
    get_inspection_id_generator,
)
from backend.storage import (
    EventCode,
    JsonlInspectionStorage,
    get_inspection_storage,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing TestClient for InspectAgent FastAPI service."""
    return TestClient(app)


# ==============================================================================
# Item 1: GET /health 정상 응답
# ==============================================================================
def test_01_health_check_endpoint(client: TestClient):
    """Item 1: Verify GET /health returns HTTP 200 and status ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"status": "ok"}


# ==============================================================================
# Item 2: 정상 Bottle 이미지의 POST /inspections 성공
# ==============================================================================
def test_02_post_inspections_success(client: TestClient):
    """Item 2: Verify POST /inspections executes successfully for normal bottle sample."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    if not sample_ids:
        pytest.skip("No dataset images found in registry.")

    payload = {
        "product_id": "PROD-VERIFY-001",
        "image_id": sample_ids[0],
    }
    resp = client.post("/inspections", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["product_id"] == "PROD-VERIFY-001"
    assert data["image_id"] == sample_ids[0]
    assert data["status"] == "COMPLETED"
    assert data["inspection_id"].startswith("INSP-")


# ==============================================================================
# Item 3: 평균 밝기와 표준편차가 실제 측정값으로 반환
# ==============================================================================
def test_03_brightness_and_std_metrics_returned(client: TestClient):
    """Item 3: Verify mean brightness and std dev are returned with real measured numbers."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    if not sample_ids:
        pytest.skip("No dataset images found in registry.")

    payload = {"product_id": "PROD-METRIC-01", "image_id": sample_ids[0]}
    resp = client.post("/inspections", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    metrics = data.get("metrics", {})
    assert "mean" in metrics
    assert "std" in metrics

    # Real bottle image mean brightness is ~136.3 and std is ~92.0
    mean_val = metrics["mean"]
    std_val = metrics["std"]
    assert isinstance(mean_val, (int, float))
    assert isinstance(std_val, (int, float))
    assert 120.0 <= mean_val <= 150.0
    assert 70.0 <= std_val <= 110.0


# ==============================================================================
# Item 4: inspections.jsonl 저장 성공
# ==============================================================================
def test_04_inspections_jsonl_record_saved(client: TestClient):
    """Item 4: Verify inspection outcome is persisted in inspections.jsonl."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    if not sample_ids:
        pytest.skip("No dataset images found in registry.")

    payload = {"product_id": "PROD-SAVED-01", "image_id": sample_ids[0]}
    resp = client.post("/inspections", json=payload)
    assert resp.status_code == 201
    target_id = resp.json()["inspection_id"]

    storage = get_inspection_storage()
    record = storage.get_inspection(target_id)
    assert record is not None
    assert record.inspection_id == target_id
    assert record.product_id == "PROD-SAVED-01"
    assert record.status == "COMPLETED"


# ==============================================================================
# Item 5: inspection_logs.jsonl 저장 성공
# ==============================================================================
def test_05_inspection_logs_jsonl_events_saved(client: TestClient):
    """Item 5: Verify execution lifecycle event logs are persisted in inspection_logs.jsonl."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    if not sample_ids:
        pytest.skip("No dataset images found in registry.")

    payload = {"product_id": "PROD-LOGS-01", "image_id": sample_ids[0]}
    resp = client.post("/inspections", json=payload)
    assert resp.status_code == 201
    target_id = resp.json()["inspection_id"]

    storage = get_inspection_storage()
    logs = storage.get_logs(target_id)
    assert len(logs) == 4
    event_codes = [l.event_code for l in logs]
    assert event_codes == [
        EventCode.INSPECTION_STARTED,
        EventCode.IMAGE_LOADED,
        EventCode.ANALYSIS_COMPLETED,
        EventCode.INSPECTION_COMPLETED,
    ]


# ==============================================================================
# Item 6: 두 파일에서 동일한 inspection_id 확인
# ==============================================================================
def test_06_matching_inspection_id_across_both_files(client: TestClient):
    """Item 6: Verify exact inspection_id match between inspections.jsonl and inspection_logs.jsonl."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    if not sample_ids:
        pytest.skip("No dataset images found in registry.")

    payload = {"product_id": "PROD-MATCH-01", "image_id": sample_ids[0]}
    resp = client.post("/inspections", json=payload)
    assert resp.status_code == 201
    target_id = resp.json()["inspection_id"]

    storage = get_inspection_storage()
    record = storage.get_inspection(target_id)
    logs = storage.get_logs(target_id)

    assert record is not None
    assert record.inspection_id == target_id
    assert len(logs) > 0
    for log_item in logs:
        assert log_item.inspection_id == target_id
        assert log_item.inspection_id == record.inspection_id


# ==============================================================================
# Item 7: 같은 이미지를 두 번 검사했을 때 서로 다른 inspection_id 생성
# ==============================================================================
def test_07_consecutive_inspections_generate_distinct_ids(client: TestClient):
    """Item 7: Verify two consecutive inspection requests of same image yield different IDs."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    if not sample_ids:
        pytest.skip("No dataset images found in registry.")

    payload = {"product_id": "PROD-REINSP-01", "image_id": sample_ids[0]}
    resp1 = client.post("/inspections", json=payload)
    resp2 = client.post("/inspections", json=payload)

    id1 = resp1.json()["inspection_id"]
    id2 = resp2.json()["inspection_id"]

    assert id1 != id2
    assert id1.startswith("INSP-")
    assert id2.startswith("INSP-")


# ==============================================================================
# Item 8: 서버 재시작 후에도 검사 ID 중복 없음
# ==============================================================================
def test_08_restart_preserves_unique_ids_without_collision(client: TestClient):
    """Item 8: Verify simulated server restart initializes counter past highest stored ID."""
    # 1. Execute an inspection to advance storage
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    if not sample_ids:
        pytest.skip("No dataset images found in registry.")

    resp_before = client.post("/inspections", json={"product_id": "PROD-PRE", "image_id": sample_ids[0]})
    id_before = resp_before.json()["inspection_id"]
    idx_before = int(id_before.split("-")[1])

    # 2. Simulate server restart: re-instantiate InspectionIdGenerator and sync from storage
    settings = get_settings()
    restarted_gen = InspectionIdGenerator(start_idx=1)
    restarted_gen.sync_with_storage(settings.absolute_inspections_path)

    next_id_after_restart = restarted_gen.next_id()
    idx_after = int(next_id_after_restart.split("-")[1])

    # Next index must strictly be greater than the last stored index
    assert idx_after > idx_before


# ==============================================================================
# Item 9: 이미지 로드 실패 시 적절한 오류와 실패 로그 생성
# ==============================================================================
def test_09_image_load_failure_logs_and_returns_error(client: TestClient):
    """Item 9: Verify load failure returns HTTP 400 and persists failure log without spurious events."""
    payload_fake = {
        "product_id": "PROD-FAIL-01",
        "image_id": "IMG-BOTTLE-DOES-NOT-EXIST",
    }
    resp = client.post("/inspections", json=payload_fake)
    assert resp.status_code == 400

    storage = get_inspection_storage()
    recent_failed = storage.list_inspections(limit=1, product_id="PROD-FAIL-01")
    assert len(recent_failed) == 1

    failed_rec = recent_failed[0]
    assert failed_rec.status == "FAILED"
    assert failed_rec.image_quality_status == "ERROR"

    failed_logs = storage.get_logs(failed_rec.inspection_id)
    codes = [l.event_code for l in failed_logs]
    assert EventCode.IMAGE_LOAD_FAILED in codes
    assert EventCode.INSPECTION_FAILED in codes
    # CRITICAL: Analysis completed must NEVER be logged when load fails
    assert EventCode.ANALYSIS_COMPLETED not in codes
    assert EventCode.IMAGE_LOADED not in codes


# ==============================================================================
# Item 10: 생성된 JSONL 모든 줄의 파싱 성공
# ==============================================================================
def test_10_all_jsonl_lines_valid_json():
    """Item 10: Verify every single line in inspections.jsonl and inspection_logs.jsonl is valid JSON."""
    settings = get_settings()
    insp_path = settings.absolute_inspections_path
    logs_path = settings.absolute_inspection_logs_path

    assert insp_path.exists(), "inspections.jsonl must exist"
    assert logs_path.exists(), "inspection_logs.jsonl must exist"

    # Verify inspections.jsonl lines
    with open(insp_path, "r", encoding="utf-8") as f:
        insp_lines = [l.strip() for l in f if l.strip()]

    assert len(insp_lines) > 0
    for line in insp_lines:
        obj = json.loads(line)
        assert "inspection_id" in obj
        assert "timestamp" in obj
        assert "status" in obj

    # Verify inspection_logs.jsonl lines
    with open(logs_path, "r", encoding="utf-8") as f:
        log_lines = [l.strip() for l in f if l.strip()]

    assert len(log_lines) > 0
    for line in log_lines:
        obj = json.loads(line)
        assert "inspection_id" in obj
        assert "event_code" in obj
        assert "level" in obj
        assert "stage" in obj


# ==============================================================================
# Item 11: 제품 result와 image_quality_status가 분리되어 기록
# ==============================================================================
def test_11_product_result_and_quality_status_decoupled(client: TestClient):
    """Item 11: Verify product verdict (UNKNOWN) is strictly decoupled from image_quality_status."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    if not sample_ids:
        pytest.skip("No dataset images found in registry.")

    payload = {"product_id": "PROD-DECOUPLED-01", "image_id": sample_ids[0]}
    resp = client.post("/inspections", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    # Product defect result must be UNKNOWN (no classifier attached yet)
    assert data["result"] == "UNKNOWN"
    # Environmental quality must be NORMAL
    assert data["image_quality_status"] == "NORMAL"

    storage = get_inspection_storage()
    rec = storage.get_inspection(data["inspection_id"])
    assert rec is not None
    assert rec.result == "UNKNOWN"
    assert rec.image_quality_status == "NORMAL"


# ==============================================================================
# Item 12: 여러 요청이 동시에 들어왔을 때 저장 데이터 손상/섞임 검증 (Thread Safety)
# ==============================================================================
def test_12_concurrent_requests_thread_safety(client: TestClient):
    """Item 12: Verify concurrent requests do not corrupt JSONL lines or mix records."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    if not sample_ids:
        pytest.skip("No dataset images found in registry.")

    concurrency_count = 10
    target_id = sample_ids[0]

    def send_inspection_request(idx: int):
        req_payload = {
            "product_id": f"CONCURRENT-PROD-{idx:03d}",
            "image_id": target_id,
        }
        res = client.post("/inspections", json=req_payload)
        return idx, res.status_code, res.json()

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(send_inspection_request, i) for i in range(concurrency_count)]
        for fut in as_completed(futures):
            results.append(fut.result())

    # All requests must succeed with HTTP 201
    assert len(results) == concurrency_count
    assigned_ids = set()
    for idx, status, body in results:
        assert status == 201
        assigned_ids.add(body["inspection_id"])

    # All assigned inspection IDs must be strictly unique
    assert len(assigned_ids) == concurrency_count

    # Storage integrity check: Every assigned ID must have valid record and 4 logs
    storage = get_inspection_storage()
    for insp_id in assigned_ids:
        rec = storage.get_inspection(insp_id)
        assert rec is not None
        assert rec.inspection_id == insp_id
        assert rec.status == "COMPLETED"

        logs = storage.get_logs(insp_id)
        assert len(logs) == 4
        assert [l.event_code for l in logs] == [
            EventCode.INSPECTION_STARTED,
            EventCode.IMAGE_LOADED,
            EventCode.ANALYSIS_COMPLETED,
            EventCode.INSPECTION_COMPLETED,
        ]

    # Verify underlying JSONL file line formatting remains fully intact
    settings = get_settings()
    with open(settings.absolute_inspections_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                json.loads(line.strip())

    with open(settings.absolute_inspection_logs_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                json.loads(line.strip())
