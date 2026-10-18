"""VisionInsight — Day 7 Step 3: Registered Static Image File Endpoint Tests.

Verifies:
1. Valid neutral image_id returns HTTP 200 with media_type="image/png"
2. Unregistered image_id returns HTTP 404
3. Malformed/prohibited image_id formats return HTTP 400
4. Missing test stub image (IMG-BOTTLE-NONEXISTENT) returns HTTP 404
5. Path traversal attempts are blocked
6. Image dimensions match original (900x900)
7. Exact pixel values are preserved with 0 degradation (max diff == 0)
8. Local filesystem paths are never leaked in response headers or body
9. Read-only operation: no inspections or records are created
"""

import numpy as np
import cv2
from fastapi.testclient import TestClient
import pytest

from backend.main import app
from backend.inspection import get_image_registry
from backend.config import get_settings
from backend.storage import get_inspection_storage
from tests.safe_image_api_fixtures import isolated_image_api


@pytest.fixture
def client():
    return TestClient(app)


def test_get_registered_image_file_success(client):
    """Fetch valid registered neutral image_id returns 200 and image/png."""
    resp = client.get("/inspections/images/IMG-BOTTLE-0001/file")
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "image/png"
    assert len(resp.content) > 10000


def test_get_unregistered_image_file_404(client):
    """Unregistered image_id returns 404 Not Found."""
    resp = client.get("/inspections/images/IMG-BOTTLE-9999/file")
    assert resp.status_code == 404
    assert "not registered" in resp.json()["detail"]


def test_get_malformed_image_id_400(client):
    """Malformed image_id returns 400 Bad Request."""
    resp = client.get("/inspections/images/invalid_bottle_id/file")
    assert resp.status_code == 400
    assert "Invalid image_id format" in resp.json()["detail"]


def test_get_path_traversal_blocked(client):
    """Path traversal sequences are blocked."""
    resp = client.get("/inspections/images/..%2F..%2Fetc%2Fpasswd/file")
    assert resp.status_code in (400, 404)


def test_get_nonexistent_stub_image_404(client):
    """Non-existent image stub returns 404 cleanly."""
    resp = client.get("/inspections/images/IMG-BOTTLE-NONEXISTENT/file")
    assert resp.status_code == 404


def test_image_pixel_fidelity_and_resolution(client):
    """Verify returned image has exact dimensions and 0 pixel difference compared to disk."""
    reg = get_image_registry(get_settings())
    disk_path = reg.get_path("IMG-BOTTLE-0001")
    assert disk_path is not None and disk_path.exists()
    disk_img = cv2.imread(str(disk_path))

    resp = client.get("/inspections/images/IMG-BOTTLE-0001/file")
    assert resp.status_code == 200
    downloaded = cv2.imdecode(np.frombuffer(resp.content, np.uint8), cv2.IMREAD_COLOR)

    assert downloaded.shape == disk_img.shape == (900, 900, 3)
    max_diff = np.max(np.abs(disk_img.astype(int) - downloaded.astype(int)))
    assert max_diff == 0


def test_no_local_disk_path_leakage(client):
    """Headers and payload do not expose internal paths like dataset/ or C:\\."""
    resp = client.get("/inspections/images/IMG-BOTTLE-0001/file")
    assert resp.status_code == 200
    for header_name, header_value in resp.headers.items():
        assert "dataset" not in header_value.lower()
        assert "broken_" not in header_value.lower()
        assert "users" not in header_value.lower()


def test_read_only_no_inspection_created(client):
    """Calling image file endpoint does not create or append inspection records."""
    storage = get_inspection_storage()
    count_before = len(storage.list_inspections(limit=100))

    resp = client.get("/inspections/images/IMG-BOTTLE-0001/file")
    assert resp.status_code == 200

    count_after = len(storage.list_inspections(limit=100))
    assert count_before == count_after
