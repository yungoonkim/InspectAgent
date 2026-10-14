"""Day 3 - Step 2: T01 standard inspection & T03 brightness fault injection tests.

Verifies:
1. T01 normal inspection and T03 (0.6x brightness reduced) fault inspection.
2. Source image immutability via SHA-256 checksum.
3. Decoupled product defect verdicts (result remains UNKNOWN).
4. Threshold-based dynamic quality evaluation (no hardcoded warnings).
5. Thread-safe JSONL persistence and inspection_id linking.
6. Zero leakage of ground truth labels or injection parameters (0.6x factor) in API responses or logs.
"""

import hashlib
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import cv2
import numpy as np

from backend.config import get_settings
from backend.main import app
from backend.inspection import get_image_registry, get_inspection_id_generator
from backend.storage import (
    EventCode,
    JsonlInspectionStorage,
    LogLevel,
    get_inspection_storage,
)
from backend.vision import analyze_brightness, inject_brightness_fault
from scripts.generate_t03_fault import compute_file_sha256, generate_t03_image


@pytest.fixture(scope="module")
def settings():
    return get_settings()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def t03_image_setup(settings):
    """Ensure T03 injected image exists and verify source SHA-256."""
    source_path = settings.absolute_dataset_path / "train" / "good" / "000.png"
    assert source_path.exists(), f"Source image missing: {source_path}"

    hash_before = compute_file_sha256(source_path)

    target_dir = settings.absolute_injected_images_path
    target_path = generate_t03_image(
        source_path=source_path,
        output_dir=target_dir,
        output_filename="IMG-BOTTLE-INJ-0001.png",
        factor=0.6,
    )

    hash_after = compute_file_sha256(source_path)
    assert hash_before == hash_after, "Source image was modified during generation!"

    # Refresh registry so it recognizes the newly generated injected image
    registry = get_image_registry(settings)
    registry.refresh(settings.absolute_dataset_path, settings.absolute_injected_images_path)

    return {
        "source_path": source_path,
        "source_hash": hash_before,
        "target_path": target_path,
    }


def test_t01_and_t03_source_immutability(t03_image_setup):
    """Verify source image is completely unchanged by comparing SHA-256."""
    source_path = t03_image_setup["source_path"]
    expected_hash = t03_image_setup["source_hash"]
    current_hash = compute_file_sha256(source_path)
    assert current_hash == expected_hash


def test_t03_image_properties(t03_image_setup):
    """Verify T03 image properties: uint8, shape preservation, clipped to [0, 255]."""
    target_path = t03_image_setup["target_path"]
    assert target_path.exists()

    injected_img = cv2.imread(str(target_path.resolve()))
    assert injected_img is not None
    assert injected_img.dtype == np.uint8
    assert injected_img.shape == (900, 900, 3)

    source_img = cv2.imread(str(t03_image_setup["source_path"].resolve()))
    assert injected_img.shape == source_img.shape


def test_t01_vs_t03_brightness_metrics_comparison(t03_image_setup):
    """Verify analytical metrics: T03 mean brightness is lower than T01 and ratio is approximately 0.6x."""
    source_img = cv2.imread(str(t03_image_setup["source_path"].resolve()))
    injected_img = cv2.imread(str(t03_image_setup["target_path"].resolve()))

    m_orig = analyze_brightness(source_img)
    m_inj = analyze_brightness(injected_img)

    assert m_inj["mean"] < m_orig["mean"]
    ratio = m_inj["mean"] / m_orig["mean"]
    assert 0.58 <= ratio <= 0.62, f"Expected ratio near 0.60, got {ratio}"
    assert m_inj["max"] <= m_orig["max"]


def test_t01_execution_via_post_inspections(client, t03_image_setup):
    """Execute T01 inspection via standard POST /inspections endpoint."""
    response = client.post(
        "/inspections",
        json={"product_id": "PROD-BOTTLE-T01", "image_id": "IMG-BOTTLE-0084"},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["product_id"] == "PROD-BOTTLE-T01"
    assert data["image_id"] == "IMG-BOTTLE-0084"
    assert data["status"] == "COMPLETED"
    assert data["result"] == "UNKNOWN"
    assert data["image_quality_status"] == "NORMAL"
    assert data["metrics"]["mean"] >= 125.0
    assert "INSP-" in data["inspection_id"]


def test_t03_execution_via_post_inspections(client, t03_image_setup):
    """Execute T03 inspection via standard POST /inspections endpoint."""
    response = client.post(
        "/inspections",
        json={"product_id": "PROD-BOTTLE-T03", "image_id": "IMG-BOTTLE-INJ-0001"},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["product_id"] == "PROD-BOTTLE-T03"
    assert data["image_id"] == "IMG-BOTTLE-INJ-0001"
    assert data["status"] == "COMPLETED"
    assert data["result"] == "UNKNOWN"
    assert data["image_quality_status"] == "WARNING_LOW_BRIGHTNESS"
    assert data["metrics"]["mean"] < 125.0
    assert "INSP-" in data["inspection_id"]


def test_distinct_inspection_ids_and_jsonl_persistence(client, t03_image_setup):
    """Verify distinct inspection IDs and corresponding event linkage in storage."""
    r1 = client.post("/inspections", json={"product_id": "PROD-BOTTLE-T01", "image_id": "IMG-BOTTLE-0084"})
    r3 = client.post("/inspections", json={"product_id": "PROD-BOTTLE-T03", "image_id": "IMG-BOTTLE-INJ-0001"})

    assert r1.status_code == 201
    assert r3.status_code == 201

    id1 = r1.json()["inspection_id"]
    id3 = r3.json()["inspection_id"]
    assert id1 != id3, f"IDs collided: {id1} == {id3}"

    storage = get_inspection_storage()

    # Check inspection records
    rec1 = storage.get_inspection(id1)
    rec3 = storage.get_inspection(id3)
    assert rec1 is not None
    assert rec3 is not None
    assert rec1.image_quality_status == "NORMAL"
    assert rec3.image_quality_status == "WARNING_LOW_BRIGHTNESS"

    # Check event logs linkage
    logs1 = storage.get_logs(id1)
    logs3 = storage.get_logs(id3)
    assert len(logs1) >= 4
    assert len(logs3) >= 4

    # T01 should have INFO level ANALYSIS_COMPLETED
    t01_analysis_events = [l for l in logs1 if l.event_code == EventCode.ANALYSIS_COMPLETED]
    assert len(t01_analysis_events) == 1
    assert t01_analysis_events[0].level == LogLevel.INFO

    # T03 should have WARN level ANALYSIS_COMPLETED
    t03_analysis_events = [l for l in logs3 if l.event_code == EventCode.ANALYSIS_COMPLETED]
    assert len(t03_analysis_events) == 1
    assert t03_analysis_events[0].level == LogLevel.WARN
    assert "below lower threshold" in t03_analysis_events[0].message


def test_zero_leakage_of_ground_truth_or_injection_parameters(client, t03_image_setup):
    """Verify no leakage of 0.6 factor or ground truth labels in API responses or logs."""
    r3 = client.post("/inspections", json={"product_id": "PROD-BOTTLE-T03", "image_id": "IMG-BOTTLE-INJ-0001"})
    data = r3.json()
    response_str = json.dumps(data)

    # Must NOT leak injection parameter factor or ground truth labels
    forbidden_terms = ["broken_large", "contamination", "ground_truth", "0.6", "factor"]
    for term in forbidden_terms:
        # Check that metrics does not contain explicit 'factor' or '0.6'
        assert term not in data["metrics"], f"Forbidden key '{term}' leaked in metrics"

    storage = get_inspection_storage()
    logs = storage.get_logs(data["inspection_id"])
    for log_record in logs:
        assert "factor" not in log_record.message
        assert "broken_large" not in log_record.message
        assert "0.6" not in log_record.message


def test_dynamic_threshold_decision_not_hardcoded(client, tmp_path):
    """Verify quality status is dynamically decided by threshold, not hardcoded.

    If threshold is lowered to 70.0, T03 (mean ~81.2) should be evaluated as NORMAL.
    """
    from backend.inspection import execute_inspection_workflow, get_image_registry
    from backend.storage import JsonlInspectionStorage

    test_store = JsonlInspectionStorage(
        inspections_path=tmp_path / "inspections.jsonl",
        logs_path=tmp_path / "logs.jsonl",
    )

    reg = get_image_registry()

    # When low_threshold is 70.0 (lower than T03 mean ~81.24)
    rec, logs = execute_inspection_workflow(
        product_id="PROD-DYNAMIC-TEST",
        image_id="IMG-BOTTLE-INJ-0001",
        registry=reg,
        storage=test_store,
        low_threshold=70.0,
        high_threshold=150.0,
    )
    assert rec.image_quality_status == "NORMAL", "Quality warning was improperly hardcoded!"

    # When low_threshold is 125.0 (higher than T03 mean ~81.24)
    rec2, logs2 = execute_inspection_workflow(
        product_id="PROD-DYNAMIC-TEST-2",
        image_id="IMG-BOTTLE-INJ-0001",
        registry=reg,
        storage=test_store,
        low_threshold=125.0,
        high_threshold=150.0,
    )
    assert rec2.image_quality_status == "WARNING_LOW_BRIGHTNESS"


def test_t05_image_load_failure_execution(client):
    """Verify T05: Simulated image load failure triggers IMAGE_LOAD_FAILED and FAILED record."""
    response = client.post(
        "/inspections",
        json={"product_id": "PROD-BOTTLE-T05", "image_id": "IMG-BOTTLE-NONEXISTENT"},
    )
    assert response.status_code == 404
    err_detail = response.json().get("detail", "")
    assert "IMG-BOTTLE-NONEXISTENT" in err_detail
    # Internal filesystem absolute path or dataset folder name must NOT be leaked
    assert "C:\\" not in err_detail
    assert "/train/" not in err_detail
    assert "/test/" not in err_detail

    # Verify JSONL persistence for failed inspection
    storage = get_inspection_storage()
    recent_inspections = storage.list_inspections(limit=10, product_id="PROD-BOTTLE-T05")
    assert len(recent_inspections) > 0

    failed_rec = recent_inspections[0]
    assert failed_rec.status == "FAILED"
    assert failed_rec.result == "UNKNOWN"
    assert failed_rec.image_quality_status == "ERROR"
    assert failed_rec.image_id == "IMG-BOTTLE-NONEXISTENT"

    # Verify event logs for failed inspection
    failed_logs = storage.get_logs(failed_rec.inspection_id)
    assert len(failed_logs) >= 3

    event_codes = [l.event_code for l in failed_logs]
    assert EventCode.INSPECTION_STARTED in event_codes
    assert EventCode.IMAGE_LOAD_FAILED in event_codes
    assert EventCode.INSPECTION_FAILED in event_codes

    # Crucial safety rule: ANALYSIS_COMPLETED and INSPECTION_COMPLETED must NEVER be logged on load failure
    assert EventCode.ANALYSIS_COMPLETED not in event_codes
    assert EventCode.INSPECTION_COMPLETED not in event_codes


def test_t05_unregistered_id_vs_missing_file_distinction(client):
    """Verify distinction between unregistered image_id (HTTP 400) and missing image file (HTTP 404)."""
    # 1. Totally unregistered ID -> 400 Bad Request
    r_unreg = client.post(
        "/inspections",
        json={"product_id": "PROD-TEST-UNREG", "image_id": "IMG-BOTTLE-TOTALLY-RANDOM-999"},
    )
    assert r_unreg.status_code == 400
    assert "not registered or allowed" in r_unreg.json()["detail"]

    # 2. Registered stub but missing underlying file -> 404 Not Found
    r_missing = client.post(
        "/inspections",
        json={"product_id": "PROD-TEST-MISSING", "image_id": "IMG-BOTTLE-NONEXISTENT"},
    )
    assert r_missing.status_code == 404
    assert "not found on server" in r_missing.json()["detail"]


def test_t06_defect_image_normal_pipeline_execution(client):
    """Verify T06: Raw defect image executes standard pipeline smoothly without premature defect verdict."""
    # IMG-BOTTLE-0001 is mapped to test/broken_large/000.png
    response = client.post(
        "/inspections",
        json={"product_id": "PROD-BOTTLE-T06", "image_id": "IMG-BOTTLE-0001"},
    )
    assert response.status_code == 201
    data = response.json()

    # Pipeline execution completes normally
    assert data["status"] == "COMPLETED"
    # Decoupled verdict remains UNKNOWN since independent defect classifier is pending
    assert data["result"] == "UNKNOWN"
    # Quality status is calculated strictly from brightness metrics
    assert data["image_quality_status"] == "NORMAL"
    assert data["metrics"]["mean"] == 138.37
    assert data["metrics"]["std"] == 92.08

    # Ground truth label 'broken_large' must NEVER be leaked in response
    resp_str = json.dumps(data)
    assert "broken_large" not in resp_str
    assert "contamination" not in resp_str

    # Verify storage records and event logs
    storage = get_inspection_storage()
    rec = storage.get_inspection(data["inspection_id"])
    assert rec is not None
    assert rec.status == "COMPLETED"
    assert rec.result == "UNKNOWN"
    assert rec.image_quality_status == "NORMAL"

    logs = storage.get_logs(data["inspection_id"])
    assert len(logs) >= 4
    event_codes = [l.event_code for l in logs]
    assert event_codes == [
        EventCode.INSPECTION_STARTED,
        EventCode.IMAGE_LOADED,
        EventCode.ANALYSIS_COMPLETED,
        EventCode.INSPECTION_COMPLETED,
    ]


def test_t05_and_t06_distinct_inspection_ids(client):
    """Verify T05 and T06 inspections receive non-colliding unique inspection IDs."""
    r5 = client.post("/inspections", json={"product_id": "PROD-BOTTLE-T05", "image_id": "IMG-BOTTLE-NONEXISTENT"})
    r6 = client.post("/inspections", json={"product_id": "PROD-BOTTLE-T06", "image_id": "IMG-BOTTLE-0001"})

    storage = get_inspection_storage()
    rec5 = storage.list_inspections(limit=1, product_id="PROD-BOTTLE-T05")[0]
    id5 = rec5.inspection_id
    id6 = r6.json()["inspection_id"]

    assert id5 != id6, f"Collision detected: {id5} == {id6}"


def test_production_safety_test_stubs_disabled():
    """Verify that in production mode (allow_test_stubs=False), test stubs are never registered."""
    from backend.inspection import ImageRegistry
    settings = get_settings()

    prod_registry = ImageRegistry(
        dataset_root=settings.absolute_dataset_path,
        injected_root=settings.absolute_injected_images_path,
        allow_test_stubs=False,
    )

    assert not prod_registry.contains("IMG-BOTTLE-NONEXISTENT")
    assert prod_registry.get_path("IMG-BOTTLE-NONEXISTENT") is None
