"""Synthetic measurement tests; no model, provider, inspection or operating image writes."""

import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.vision import analyze_brightness, evaluate_image_quality


SPEC = importlib.util.spec_from_file_location("quality_baseline", Path(__file__).parents[1] / "scripts/experiments/analyze_quality_baseline.py")
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)


@pytest.mark.parametrize("level", [0, 125, 150, 255])
def test_constant_images_have_finite_metrics_and_match_existing_gv(level):
    image = np.full((32, 48, 3), level, np.uint8)
    measured = analysis.metrics(image)
    assert measured["mean_gv"] == analyze_brightness(image)["mean"] == level
    assert measured["std_gv"] == measured["laplacian_variance_ksize3"] == measured["tenengrad_mean_squared_ksize3"] == 0
    assert sum(measured["histogram"]) == 32 * 48
    json.dumps(measured, allow_nan=False)


def test_known_pixel_partitions_reconstruct_mean_without_claiming_a_bottle_mask():
    image = np.full((80, 80, 3), 240, np.uint8)
    image[20:60, 20:60] = 60
    results, masks = analysis.partitions(image)
    for name in masks:
        first, second = results[name]["foreground"], results[name]["background"]
        assert first is not None and second is not None
        assert first["mean_gv"] == 60 and second["mean_gv"] == 240
        assert first["area_fraction"] == 0.25
        assert first["area_fraction"] * first["mean_gv"] + second["area_fraction"] * second["mean_gv"] == 195
        assert results[name]["confidence"] == "NOT_CALIBRATED_NO_SEGMENTATION_GROUND_TRUTH"


@pytest.mark.parametrize("level,expected", [(124, "WARNING_LOW_BRIGHTNESS"), (125, "NORMAL"),
                                           (150, "NORMAL"), (151, "WARNING_HIGH_BRIGHTNESS")])
def test_existing_brightness_bounds_are_reused_without_a_new_policy(level, expected):
    assert evaluate_image_quality({"mean": level}, 125, 150)["quality_status"] == expected


def test_border_touch_and_blank_images_do_not_invent_closed_masks():
    image = np.full((80, 80, 3), 240, np.uint8)
    image[:50, :50] = 60
    results, masks = analysis.partitions(image)
    assert results["closed_gray207_contour"]["status"] == "UNAVAILABLE_BORDER_TOUCH_NOT_COMPLETED"
    assert "closed_gray207_contour" not in masks
    assert results["closed_gray207_contour"]["foreground"] is None
    blank, _ = analysis.partitions(np.full_like(image, 255))
    assert blank["closed_gray207_contour"]["status"] == "UNAVAILABLE_NO_CONTOUR"
    json.dumps(blank, allow_nan=False)


def test_sharpness_metrics_respond_to_synthetic_blur_not_defect_labels():
    image = np.full((96, 96, 3), 220, np.uint8)
    image[24:72, 24:72] = 40
    blurred = cv2.GaussianBlur(image, (0, 0), 2)
    first, second = analysis.metrics(image), analysis.metrics(blurred)
    assert second["laplacian_variance_ksize3"] < first["laplacian_variance_ksize3"]
    assert second["tenengrad_mean_squared_ksize3"] < first["tenengrad_mean_squared_ksize3"]


def test_exact_pair_and_changed_pair_have_safe_psnr_ssim_and_shape_validation():
    image = np.full((40, 40, 3), 100, np.uint8)
    equal = analysis.paired_loss(image, image)
    assert equal["psnr_status"] == "EXACT_PIXELS_INFINITE_PSNR" and equal["psnr_db"] is None
    assert equal["ssim_gray_window11_sigma1_5"] == pytest.approx(1)
    changed = analysis.paired_loss(image, image + 10)
    assert changed["gray_mse"] == 100
    assert changed["psnr_db"] == pytest.approx(28.1308, abs=0.001)
    assert 0 < changed["ssim_gray_window11_sigma1_5"] < 1
    json.dumps(equal, allow_nan=False)
    with pytest.raises(ValueError, match="EXACTLY_ALIGNED_PAIR_REQUIRED"):
        analysis.paired_loss(image, image[:20])
