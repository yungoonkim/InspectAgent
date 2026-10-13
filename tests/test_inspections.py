"""Tests for Day 1 inspection execution and ID assignment."""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.inspection import get_image_registry


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
    assert data["result"] == "UNKNOWN"
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
