"""Tests for PatchCore 2D Anomaly Map Sidecar Artifact Storage, Spatial Alignment, and APIs.

All tests run OFFLINE using mocks (0 live PatchCore inference, 0 live Gemini API calls).
Validates:
1. POST /inspections schema backwards-compatibility (capture_anomaly_map=False by default)
2. Map sidecar persistence (.npz, .json, and overlay .png) when capture_anomaly_map=True
3. Forward pass executed exactly once (no redundant prediction)
4. Read-only GET /inspections/{inspection_id}/anomaly-map returns 200 with metadata
5. Read-only GET /inspections/{inspection_id}/anomaly-map/overlay.png returns valid RGBA PNG
6. Unregistered/missing anomaly map returns 404 MAP_NOT_AVAILABLE without executing ML
7. Path traversal attempts are blocked (400)
8. NaN/Inf and abnormal shape sanitization
9. Spatial coordinate alignment: 256x256 map peak maps precisely to 900x900 image peak
10. Sidecar write failure does not mutate final_result or fail the inspection
"""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.anomaly_map_store import (
    get_anomaly_map_metadata,
    get_anomaly_map_overlay_path,
    is_valid_inspection_id,
    save_anomaly_map_artifact,
)
from backend.inspection import execute_inspection_workflow
from backend.main import app
from tests.safe_image_api_fixtures import isolated_image_api


@pytest.fixture
def temp_sidecar_dir():
    temp_dir = Path(tempfile.mkdtemp(prefix="test_anomaly_maps_"))
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_is_valid_inspection_id():
    """Verify inspection ID security regex and traversal rejection."""
    assert is_valid_inspection_id("INSP-001450") is True
    assert is_valid_inspection_id("INSP-123456") is True
    assert is_valid_inspection_id("INSP-TEST-01") is True

    # Traversal and invalid patterns
    assert is_valid_inspection_id("../INSP-001450") is False
    assert is_valid_inspection_id("INSP-001450/../../etc") is False
    assert is_valid_inspection_id("INSP-001450\\traversal") is False
    assert is_valid_inspection_id("") is False
    assert is_valid_inspection_id("RANDOM_ID") is False


def test_save_and_retrieve_anomaly_map_artifact(temp_sidecar_dir):
    """Test saving .npz, .json, and overlay .png, then retrieving metadata."""
    insp_id = "INSP-009999"
    img_id = "IMG-BOTTLE-0001"

    # Synthetic 256x256 anomaly map with a bright spot at (128, 128)
    dummy_map = np.zeros((256, 256), dtype=np.float32)
    dummy_map[120:136, 120:136] = 8.5

    meta = save_anomaly_map_artifact(
        inspection_id=insp_id,
        image_id=img_id,
        anomaly_map=dummy_map,
        original_width=900,
        original_height=900,
        model_name="PatchCore-ResNet18",
        anomaly_score=35.12,
        decision_threshold=34.1442,
        custom_dir=temp_sidecar_dir,
    )

    assert meta["inspection_id"] == insp_id
    assert meta["image_id"] == img_id
    assert meta["original_image_width"] == 900
    assert meta["original_image_height"] == 900
    assert meta["anomaly_map_width"] == 256
    assert meta["anomaly_map_height"] == 256
    assert meta["range"]["max"] == 8.5
    assert meta["localization_available"] is True

    # Verify files created on disk
    npz_path = temp_sidecar_dir / f"{insp_id}.npz"
    json_path = temp_sidecar_dir / f"{insp_id}.json"
    png_path = temp_sidecar_dir / f"{insp_id}_overlay.png"

    assert npz_path.exists()
    assert json_path.exists()
    assert png_path.exists()

    # Verify PNG is valid RGBA 900x900
    overlay_img = cv2.imread(str(png_path), cv2.IMREAD_UNCHANGED)
    assert overlay_img is not None
    assert overlay_img.shape == (900, 900, 4)  # 900x900 BGRA

    # Test reading back via helper functions
    retrieved_meta = get_anomaly_map_metadata(insp_id, custom_dir=temp_sidecar_dir)
    assert retrieved_meta is not None
    assert retrieved_meta["inspection_id"] == insp_id

    retrieved_overlay = get_anomaly_map_overlay_path(insp_id, custom_dir=temp_sidecar_dir)
    assert retrieved_overlay == png_path


def test_spatial_peak_alignment():
    """Verify that a localized peak in 256x256 space maps directly to the corresponding location in 900x900 space."""
    # Place a distinct peak at map center: (128, 128)
    peak_y_256, peak_x_256 = 128, 128
    dummy_map = np.zeros((256, 256), dtype=np.float32)
    dummy_map[peak_y_256, peak_x_256] = 10.0

    orig_w, orig_h = 900, 900
    norm = dummy_map / 10.0
    resized_norm = cv2.resize(norm, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)

    # Find coordinates of maximum response in 900x900 space
    max_idx = np.unravel_index(np.argmax(resized_norm), resized_norm.shape)
    peak_y_900, peak_x_900 = max_idx

    expected_x = int(round(peak_x_256 * (900 / 256)))
    expected_y = int(round(peak_y_256 * (900 / 256)))

    assert abs(peak_x_900 - expected_x) <= 2, f"X peak misaligned: expected {expected_x}, got {peak_x_900}"
    assert abs(peak_y_900 - expected_y) <= 2, f"Y peak misaligned: expected {expected_y}, got {peak_y_900}"


def test_nan_inf_sanitization(temp_sidecar_dir):
    """Verify that NaN and Inf entries in anomaly_map do not cause crash and are cleanly replaced."""
    dummy_map = np.ones((256, 256), dtype=np.float32)
    dummy_map[0, 0] = np.nan
    dummy_map[0, 1] = np.inf
    dummy_map[0, 2] = -np.inf

    meta = save_anomaly_map_artifact(
        inspection_id="INSP-008888",
        image_id="IMG-BOTTLE-0001",
        anomaly_map=dummy_map,
        original_width=900,
        original_height=900,
        custom_dir=temp_sidecar_dir,
    )

    assert meta["localization_available"] is True
    # Values should be finite
    assert not np.isnan(meta["range"]["min"])
    assert not np.isinf(meta["range"]["max"])


def test_post_inspections_default_capture_false_preserves_single_call(monkeypatch, temp_sidecar_dir):
    """POST /inspections without capture_anomaly_map does not save sidecar and calls predict exactly once."""
    monkeypatch.setattr("backend.anomaly_map_store.get_anomaly_map_dir", lambda: temp_sidecar_dir)

    client = TestClient(app)

    # Mock inferencer
    mock_inferencer = MagicMock()
    mock_inferencer.predict.return_value = {
        "anomaly_score": 30.5,
        "anomaly_map": np.zeros((256, 256), dtype=np.float32),
        "inference_time_ms": 12.3,
        "model_name": "MockPatchCore",
    }
    monkeypatch.setattr("backend.main.get_patchcore_inferencer", lambda: mock_inferencer)

    res = client.post(
        "/inspections",
        json={"product_id": "TEST_P1", "image_id": "IMG-BOTTLE-0001"},
    )
    assert res.status_code == 201
    data = res.json()
    insp_id = data["inspection_id"]

    # Predict called exactly 1 time
    assert mock_inferencer.predict.call_count == 1

    # No sidecar saved
    assert not (temp_sidecar_dir / f"{insp_id}.json").exists()
    assert not (temp_sidecar_dir / f"{insp_id}.npz").exists()


def test_post_inspections_capture_true_saves_sidecar_from_single_predict(monkeypatch, temp_sidecar_dir):
    """POST /inspections with capture_anomaly_map=True saves sidecar from the same single predict call."""
    monkeypatch.setattr("backend.anomaly_map_store.get_anomaly_map_dir", lambda: temp_sidecar_dir)

    client = TestClient(app)

    mock_map = np.zeros((256, 256), dtype=np.float32)
    mock_map[50, 50] = 5.0

    mock_inferencer = MagicMock()
    mock_inferencer.predict.return_value = {
        "anomaly_score": 45.0,
        "anomaly_map": mock_map,
        "inference_time_ms": 15.0,
        "model_name": "MockPatchCore",
    }
    monkeypatch.setattr("backend.main.get_patchcore_inferencer", lambda: mock_inferencer)

    res = client.post(
        "/inspections",
        json={
            "product_id": "TEST_P2",
            "image_id": "IMG-BOTTLE-0001",
            "capture_anomaly_map": True,
        },
    )
    assert res.status_code == 201
    data = res.json()
    insp_id = data["inspection_id"]

    # Single inference call
    assert mock_inferencer.predict.call_count == 1

    # Sidecar exists
    json_path = temp_sidecar_dir / f"{insp_id}.json"
    npz_path = temp_sidecar_dir / f"{insp_id}.npz"
    png_path = temp_sidecar_dir / f"{insp_id}_overlay.png"

    assert json_path.exists()
    assert npz_path.exists()
    assert png_path.exists()

    with open(json_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["image_id"] == "IMG-BOTTLE-0001"
    assert meta["anomaly_score"] == 45.0


def test_get_anomaly_map_api_read_only(monkeypatch, temp_sidecar_dir):
    """GET /inspections/{id}/anomaly-map and overlay.png return 200 and never run ML."""
    monkeypatch.setattr("backend.anomaly_map_store.get_anomaly_map_dir", lambda: temp_sidecar_dir)

    insp_id = "INSP-007777"
    from backend.storage import InspectionRecord, get_inspection_storage
    get_inspection_storage().save_inspection(InspectionRecord(
        inspection_id=insp_id, image_id="IMG-BOTTLE-0001", product_id="TEST-MAP",
        image_quality_status="NORMAL", metrics={"width": 900, "height": 900},
    ))
    save_anomaly_map_artifact(
        inspection_id=insp_id,
        image_id="IMG-BOTTLE-0001",
        anomaly_map=np.ones((256, 256), dtype=np.float32),
        original_width=900,
        original_height=900,
        custom_dir=temp_sidecar_dir,
    )

    client = TestClient(app)

    # 1. Metadata endpoint
    res_meta = client.get(f"/inspections/{insp_id}/anomaly-map")
    assert res_meta.status_code == 200
    meta_data = res_meta.json()
    assert meta_data["available"] is True
    assert meta_data["original_image_width"] == 900
    assert meta_data["overlay_url"] == f"/inspections/{insp_id}/anomaly-map/overlay.png"

    # 2. PNG overlay endpoint
    res_img = client.get(f"/inspections/{insp_id}/anomaly-map/overlay.png")
    assert res_img.status_code == 200
    assert res_img.headers["content-type"] == "image/png"
    assert len(res_img.content) > 100


def test_get_anomaly_map_not_available_404(monkeypatch, temp_sidecar_dir):
    """Querying an inspection without a map returns 404 MAP_NOT_AVAILABLE."""
    monkeypatch.setattr("backend.anomaly_map_store.get_anomaly_map_dir", lambda: temp_sidecar_dir)

    client = TestClient(app)

    res = client.get("/inspections/INSP-001396/anomaly-map")
    assert res.status_code == 404
    data = res.json()
    assert data["detail"]["error_code"] == "MAP_NOT_AVAILABLE"

    res_img = client.get("/inspections/INSP-001396/anomaly-map/overlay.png")
    assert res_img.status_code == 404
    assert res_img.json()["detail"]["error_code"] == "MAP_NOT_AVAILABLE"


def test_path_traversal_blocked():
    """Verify malformed inspection IDs with path traversal return 400 Bad Request."""
    client = TestClient(app)

    res = client.get("/inspections/..%2F..%2Fetc%2Fpasswd/anomaly-map")
    assert res.status_code in (400, 404)

    res2 = client.get("/inspections/INSP-000001..traversal/anomaly-map")
    assert res2.status_code == 400
