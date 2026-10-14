"""Unit and integration tests for OpenCV brightness analysis and fault injection."""

from pathlib import Path
import hashlib
import json
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import get_settings
from backend.vision import (
    analyze_brightness,
    analyze_image_size,
    analyze_image,
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


def test_analyze_image_size():
    """Verify analyze_image_size correctly extracts dimensions and channels."""
    # 3-channel color image
    color_img = np.zeros((480, 640, 3), dtype=np.uint8)
    size_info = analyze_image_size(color_img)
    assert size_info["width"] == 640
    assert size_info["height"] == 480
    assert size_info["channels"] == 3

    # 1-channel grayscale image
    gray_img = np.zeros((300, 400), dtype=np.uint8)
    gray_size = analyze_image_size(gray_img)
    assert gray_size["width"] == 400
    assert gray_size["height"] == 300
    assert gray_size["channels"] == 1

    # Invalid input
    with pytest.raises(ValueError):
        analyze_image_size(None)  # type: ignore

    with pytest.raises(ValueError):
        analyze_image_size(np.array([]))


def test_analyze_image_returns_json_serializable():
    """Verify analyze_image returns a structured dictionary that is directly JSON serializable."""
    sample_img = np.full((100, 100, 3), 136, dtype=np.uint8)
    result = analyze_image(sample_img, filename="sample.png")

    # Must be JSON-serializable without errors
    serialized = json.dumps(result)
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)

    assert "image_size" in deserialized
    assert deserialized["image_size"]["width"] == 100
    assert deserialized["image_size"]["height"] == 100
    assert deserialized["image_size"]["channels"] == 3

    assert "brightness_metrics" in deserialized
    assert deserialized["brightness_metrics"]["mean"] == 136.0

    assert "quality_evaluation" in deserialized
    assert deserialized["quality_evaluation"]["quality_status"] == "NORMAL"
    assert deserialized["quality_evaluation"]["warning_triggered"] is False

    # Product defect inspection must be decoupled
    assert "product_defect_inspection" in deserialized
    assert deserialized["product_defect_inspection"]["status"] == "UNINSPECTED"


def test_analyze_image_normal_vs_brightness_reduced():
    """Verify analyze_image correctly distinguishes normal and brightness-reduced images."""
    settings = get_settings()
    # Baseline bottle brightness is ~136.3
    normal_img = np.full((100, 100, 3), 136, dtype=np.uint8)
    normal_res = analyze_image(normal_img)

    assert normal_res["quality_evaluation"]["quality_status"] == "NORMAL"
    assert normal_res["quality_evaluation"]["warning_triggered"] is False
    assert normal_res["product_defect_inspection"]["status"] == "UNINSPECTED"

    # Injected brightness reduction (0.6x factor -> 136 * 0.6 = 81.6)
    reduced_img = inject_brightness_fault(normal_img, factor=settings.FAULT_INJECTION_FACTOR)
    reduced_res = analyze_image(reduced_img)

    assert reduced_res["brightness_metrics"]["mean"] < settings.BRIGHTNESS_LOW_THRESHOLD
    assert reduced_res["quality_evaluation"]["quality_status"] == "WARNING_LOW_BRIGHTNESS"
    assert reduced_res["quality_evaluation"]["warning_triggered"] is True
    # Product defect status must remain UNINSPECTED even when quality warning is active
    assert reduced_res["product_defect_inspection"]["status"] == "UNINSPECTED"


def test_configurable_brightness_thresholds():
    """Verify that brightness warning evaluation responds dynamically to custom/configured thresholds."""
    # Test image with mean brightness 136.0
    img = np.full((100, 100, 3), 136, dtype=np.uint8)

    # 1. Under standard thresholds [125.0, 150.0] -> NORMAL
    res_default = analyze_image(img, low_threshold=125.0, high_threshold=150.0)
    assert res_default["quality_evaluation"]["quality_status"] == "NORMAL"
    assert res_default["quality_evaluation"]["warning_triggered"] is False

    # 2. Adjust low_threshold up to 140.0 -> Triggers WARNING_LOW_BRIGHTNESS
    res_tight_low = analyze_image(img, low_threshold=140.0, high_threshold=150.0)
    assert res_tight_low["quality_evaluation"]["quality_status"] == "WARNING_LOW_BRIGHTNESS"
    assert res_tight_low["quality_evaluation"]["warning_triggered"] is True
    assert res_tight_low["quality_evaluation"]["applied_thresholds"]["low_threshold"] == 140.0

    # 3. Adjust high_threshold down to 130.0 -> Triggers WARNING_HIGH_BRIGHTNESS
    res_tight_high = analyze_image(img, low_threshold=100.0, high_threshold=130.0)
    assert res_tight_high["quality_evaluation"]["quality_status"] == "WARNING_HIGH_BRIGHTNESS"
    assert res_tight_high["quality_evaluation"]["warning_triggered"] is True
    assert res_tight_high["quality_evaluation"]["applied_thresholds"]["high_threshold"] == 130.0


def test_persisted_baseline_brightness_json():
    """Verify data/baseline_brightness.json accurately records the calculated Bottle baseline statistics."""
    from backend.config import PROJECT_ROOT

    json_path = PROJECT_ROOT / "data" / "baseline_brightness.json"
    assert json_path.exists(), "data/baseline_brightness.json must be created and persisted"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["status"] == "ready"
    assert data["sample_count"] == 209
    assert data["mean_of_means"] == 136.34
    assert data["std_of_means"] == 1.38
    assert data["min_mean"] == 133.37
    assert data["max_mean"] == 139.55
    assert data["average_internal_std"] == 92.89

    percentiles = data["percentiles"]
    assert percentiles["p1"] == 133.54
    assert percentiles["p5"] == 134.16
    assert percentiles["p50"] == 136.17
    assert percentiles["p95"] == 138.7
    assert percentiles["p99"] == 139.48

