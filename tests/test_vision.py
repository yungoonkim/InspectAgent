"""Unit and integration tests for OpenCV brightness analysis and fault injection."""

from pathlib import Path
import hashlib
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import get_settings
from backend.vision import (
    analyze_brightness,
    compute_baseline_statistics,
    inject_brightness_fault,
    save_modified_image,
    evaluate_image_quality,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing TestClient for FastAPI app."""
    return TestClient(app)


def test_analyze_brightness_basic():
    """Verify analyze_brightness accurately calculates grayscale statistics."""
    # Create synthetic test image (100x100 BGR with uniform value 100)
    synthetic_bgr = np.full((100, 100, 3), 100, dtype=np.uint8)
    metrics = analyze_brightness(synthetic_bgr)

    assert metrics["mean"] == 100.0
    assert metrics["std"] == 0.0
    assert metrics["min"] == 100.0
    assert metrics["max"] == 100.0


def test_inject_brightness_fault_preserves_original():
    """Verify 0.6x fault injection scales pixel brightness and keeps original array immutable."""
    original = np.full((50, 50, 3), 200, dtype=np.uint8)
    original_copy = original.copy()

    faulty = inject_brightness_fault(original, factor=0.6)

    # 1. Verify original array was not mutated
    np.testing.assert_array_equal(original, original_copy)

    # 2. Verify faulty array scaled by 0.6 (200 * 0.6 = 120)
    assert faulty.shape == original.shape
    assert faulty.dtype == np.uint8
    np.testing.assert_array_equal(faulty, np.full((50, 50, 3), 120, dtype=np.uint8))


def test_fault_image_save_does_not_overwrite_original(tmp_path: Path):
    """Verify saved fault image is written to designated output folder without touching original file."""
    # Create fake original file in mock dataset
    orig_dir = tmp_path / "dataset" / "train" / "good"
    orig_dir.mkdir(parents=True)
    orig_file = orig_dir / "test_sample.png"
    fake_data = b"Original dummy PNG content"
    orig_file.write_bytes(fake_data)
    orig_hash = hashlib.sha256(orig_file.read_bytes()).hexdigest()

    # Save fault-injected image to distinct output folder
    output_dir = tmp_path / "data" / "outputs" / "injected"
    dummy_img = np.zeros((10, 10, 3), dtype=np.uint8)
    saved_path = save_modified_image(dummy_img, output_dir=output_dir, filename="fault_test_sample.png")

    # Verify paths are completely different
    assert saved_path != orig_file
    assert saved_path.exists()

    # Verify original file content was untouched
    assert hashlib.sha256(orig_file.read_bytes()).hexdigest() == orig_hash


def test_quality_evaluation_decoupled_from_defect_inspection():
    """Verify image quality status is evaluated and decoupled from product defect inspection."""
    low_thresh = 125.0
    high_thresh = 150.0

    # 1. Normal brightness case (~136.3)
    normal_eval = evaluate_image_quality(
        metrics={"mean": 136.3, "std": 58.0, "min": 0.0, "max": 255.0},
        low_threshold=low_thresh,
        high_threshold=high_thresh,
    )
    assert normal_eval["quality_status"] == "NORMAL"
    assert normal_eval["warning_triggered"] is False
    assert normal_eval["product_defect_inspection"]["status"] == "UNINSPECTED"

    # 2. Low brightness case (81.8 after 0.6x fault injection)
    low_eval = evaluate_image_quality(
        metrics={"mean": 81.8, "std": 34.8, "min": 0.0, "max": 153.0},
        low_threshold=low_thresh,
        high_threshold=high_thresh,
    )
    assert low_eval["quality_status"] == "WARNING_LOW_BRIGHTNESS"
    assert low_eval["warning_triggered"] is True
    # Product anomaly verdict must remain decoupled!
    assert low_eval["product_defect_inspection"]["status"] == "UNINSPECTED"
    # Warning text must not conclude hardware failure
    assert "hardware failure not confirmed" in low_eval["description"]


def test_baseline_statistics_on_actual_dataset():
    """Verify compute_baseline_statistics processes actual train/good images if present."""
    settings = get_settings()
    train_good_dir = settings.absolute_dataset_path / "train" / "good"

    if not train_good_dir.exists():
        pytest.skip("Dataset train/good not present, skipping dataset-dependent test.")

    baseline = compute_baseline_statistics(train_good_dir)
    assert baseline["status"] == "ready"
    assert baseline["sample_count"] > 0
    assert 130.0 <= baseline["mean_of_means"] <= 142.0
    assert "percentiles" in baseline
    assert "p1" in baseline["percentiles"]
    assert "p99" in baseline["percentiles"]


def test_api_analyze_and_compare_fault(client: TestClient):
    """Verify /analyze-brightness and /test-image/compare-fault endpoints."""
    settings = get_settings()
    train_good_dir = settings.absolute_dataset_path / "train" / "good"

    if not train_good_dir.exists():
        pytest.skip("Dataset train/good not present, skipping endpoint integration test.")

    # 1. Test /baseline/brightness
    base_resp = client.get("/baseline/brightness")
    assert base_resp.status_code == 200
    base_data = base_resp.json()
    assert base_data["status"] == "ready"

    # 2. Test /analyze-brightness
    analyze_resp = client.get("/analyze-brightness")
    assert analyze_resp.status_code == 200
    analyze_data = analyze_resp.json()
    assert "metrics" in analyze_data
    assert analyze_data["evaluation"]["quality_status"] == "NORMAL"
    assert analyze_data["evaluation"]["warning_triggered"] is False
    assert analyze_data["evaluation"]["product_defect_inspection"]["status"] == "UNINSPECTED"

    # 3. Test /test-image/compare-fault
    compare_resp = client.get("/test-image/compare-fault")
    assert compare_resp.status_code == 200
    compare_data = compare_resp.json()

    orig_item = compare_data["original"]
    fault_item = compare_data["fault_injected"]

    # Original must be normal
    assert orig_item["quality_status"] == "NORMAL"
    assert orig_item["warning_triggered"] is False

    # Fault-injected must trigger warning
    assert fault_item["quality_status"] == "WARNING_LOW_BRIGHTNESS"
    assert fault_item["warning_triggered"] is True

    # Comparison metrics
    assert compare_data["comparison"]["measured_ratio"] < 0.65
    assert compare_data["comparison"]["warning_escalated"] is True

    # Check saved image exists in injected output folder
    assert Path(fault_item["saved_path"]).exists()
