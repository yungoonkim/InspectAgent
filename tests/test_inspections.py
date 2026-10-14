"""Tests for Day 1 inspection execution and ID assignment."""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.inspection import get_image_registry
from backend.storage import EventCode, StorageWriteError, get_inspection_storage


@pytest.fixture
def client() -> TestClient:
    """Fixture providing TestClient for FastAPI app."""
    return TestClient(app)


def test_health_check_day1(client: TestClient):
    """Verify GET /health returns status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_inspection_images_neutral_ids(client: TestClient):
    """Verify GET /inspections/images returns neutral image IDs without leaking raw labels."""
    response = client.get("/inspections/images")
    assert response.status_code == 200
    data = response.json()

    assert data["total_images"] > 0
    assert "image_ids" in data
    # Check that IDs are neutral (e.g. IMG-BOTTLE-0001)
    sample_id = data["image_ids"][0]
    assert sample_id.startswith("IMG-BOTTLE-")

    # Verify no raw ground truth labels or directory names are leaked in the ID strings
    for img_id in data["image_ids"][:20]:
        assert "broken" not in img_id.lower()
        assert "contamination" not in img_id.lower()
        assert "good" not in img_id.lower()


def test_post_inspections_success(client: TestClient):
    """Verify POST /inspections loads image, returns inspection_id, and marks result as UNKNOWN."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    if not sample_ids:
        pytest.skip("No dataset images registered, skipping inspection test.")

    target_image_id = sample_ids[0]
    payload = {
        "product_id": "ABCD1541",
        "image_id": target_image_id,
    }

    response = client.post("/inspections", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["product_id"] == "ABCD1541"
    assert data["image_id"] == target_image_id
    assert data["inspection_id"].startswith("INSP-")
    assert data["status"] == "COMPLETED"
    assert data["result"] in ("OK", "NG", "UNKNOWN")
    assert "timestamp" in data
    assert "+09:00" in data["timestamp"] or "T" in data["timestamp"]

    # Image metadata loaded via OpenCV
    assert "image_metadata" in data
    assert data["image_metadata"]["width"] > 0
    assert data["image_metadata"]["height"] > 0
    assert data["image_metadata"]["channels"] == 3


def test_post_inspections_generates_distinct_ids_for_consecutive_requests(client: TestClient):
    """Verify two consecutive inspection requests receive different, unique inspection_ids."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    if not sample_ids:
        pytest.skip("No dataset images registered, skipping distinction test.")

    target_image_id = sample_ids[0]
    payload = {
        "product_id": "ABCD1541",
        "image_id": target_image_id,
    }

    resp1 = client.post("/inspections", json=payload)
    assert resp1.status_code == 201
    id1 = resp1.json()["inspection_id"]

    # Second request with SAME product_id (re-inspection scenario)
    resp2 = client.post("/inspections", json=payload)
    assert resp2.status_code == 201
    id2 = resp2.json()["inspection_id"]

    # IDs must be strictly distinct
    assert id1 != id2
    assert id1.startswith("INSP-")
    assert id2.startswith("INSP-")


def test_post_inspections_rejects_unregistered_or_arbitrary_path(client: TestClient):
    """Verify POST /inspections rejects unregistered IDs or arbitrary file path injections."""
    # Attempt 1: Arbitrary path traversal string
    payload_hack = {
        "product_id": "ABCD1541",
        "image_id": "../../../etc/passwd",
    }
    resp1 = client.post("/inspections", json=payload_hack)
    assert resp1.status_code == 400
    assert "not registered" in resp1.json()["detail"].lower()

    # Attempt 2: Non-existent image ID
    payload_fake = {
        "product_id": "ABCD1541",
        "image_id": "IMG-BOTTLE-999999",
    }
    resp2 = client.post("/inspections", json=payload_fake)
    assert resp2.status_code == 400


def test_post_inspections_persists_to_jsonl_and_links_logs(client: TestClient):
    """Verify POST /inspections persists both result and event logs connected by inspection_id."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    if not sample_ids:
        pytest.skip("No dataset images registered, skipping test.")

    target_image_id = sample_ids[0]
    payload = {
        "product_id": "ABCD1541",
        "image_id": target_image_id,
    }

    response = client.post("/inspections", json=payload)
    assert response.status_code == 201
    data = response.json()

    inspection_id = data["inspection_id"]
    assert data["image_quality_status"] == "NORMAL"
    assert "mean" in data["metrics"]
    assert "std" in data["metrics"]
    assert data["result"] in ("OK", "NG", "UNKNOWN")

    # Verify storage contains the record in inspections.jsonl
    storage = get_inspection_storage()
    saved_record = storage.get_inspection(inspection_id)
    assert saved_record is not None
    assert saved_record.inspection_id == inspection_id
    assert saved_record.product_id == "ABCD1541"
    assert saved_record.image_quality_status == "NORMAL"
    assert saved_record.status == "COMPLETED"

    # Verify execution logs in inspection_logs.jsonl
    saved_logs = storage.get_logs(inspection_id)
    assert len(saved_logs) in (4, 6)
    for log in saved_logs:
        assert log.inspection_id == inspection_id

    event_codes = [log.event_code for log in saved_logs]
    for expected_code in [
        EventCode.INSPECTION_STARTED,
        EventCode.IMAGE_LOADED,
        EventCode.ANALYSIS_COMPLETED,
        EventCode.INSPECTION_COMPLETED,
    ]:
        assert expected_code in event_codes


def test_post_inspections_load_failure_logs_events(client: TestClient):
    """Verify that an image load failure logs failure events in storage before returning 400."""
    payload_fake = {
        "product_id": "PROD-ERR-01",
        "image_id": "IMG-BOTTLE-INVALID-999",
    }
    response = client.post("/inspections", json=payload_fake)
    assert response.status_code == 400

    storage = get_inspection_storage()
    recent_inspections = storage.list_inspections(limit=1, product_id="PROD-ERR-01")
    assert len(recent_inspections) == 1

    failed_rec = recent_inspections[0]
    assert failed_rec.status == "FAILED"
    assert failed_rec.image_quality_status == "ERROR"

    failed_logs = storage.get_logs(failed_rec.inspection_id)
    events = [l.event_code for l in failed_logs]
    assert EventCode.IMAGE_LOAD_FAILED in events
    assert EventCode.INSPECTION_FAILED in events
    # ANALYSIS_COMPLETED must NEVER be logged on load failure
    assert EventCode.ANALYSIS_COMPLETED not in events


def test_post_inspections_storage_write_failure_returns_500(client: TestClient):
    """Verify that when storage write fails, HTTP 500 is returned rather than a false positive completed status."""
    registry = get_image_registry()
    sample_ids = registry.list_image_ids()
    if not sample_ids:
        pytest.skip("No dataset images registered, skipping test.")

    payload = {
        "product_id": "ABCD1541",
        "image_id": sample_ids[0],
    }

    with patch("backend.storage.JsonlInspectionStorage.save_inspection", side_effect=StorageWriteError("Disk full")):
        response = client.post("/inspections", json=payload)
        assert response.status_code == 500
        assert "storage" in response.json()["detail"].lower()

