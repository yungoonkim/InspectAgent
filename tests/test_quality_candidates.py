"""A-2 synthetic unit tests only; never load operating inspections or models."""

import ast
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from scripts.experiments.quality_candidates import crop_region, measure, variants
from scripts.experiments.run_quality_experiments import benchmark_components, grouped_split


def synthetic_image():
    image = np.full((160, 160, 3), 245, np.uint8)
    cv2.circle(image, (80, 80), 50, (60, 60, 60), -1)
    cv2.circle(image, (80, 80), 28, (90, 90, 90), -1)
    return image


def test_same_input_is_reproducible_and_does_not_mutate_the_array():
    image = synthetic_image()
    original = image.copy()
    first, second = measure(image), measure(image)
    assert first == second
    assert np.array_equal(image, original)
    json.dumps(first, allow_nan=False)
    assert not {"final_result", "quality_status", "judge_verdict"}.intersection(first)


def test_png_file_and_memory_remain_unchanged_after_all_transforms(tmp_path):
    path = tmp_path / "SYNTHETIC-source.png"
    image = synthetic_image()
    assert cv2.imwrite(str(path), image)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    before = image.copy()
    first, second = variants(image), variants(image)
    for name in first:
        assert np.array_equal(first[name], second[name])
        json.dumps(measure(first[name]), allow_nan=False)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum
    assert np.array_equal(image, before)
    assert first["half_resolution"].shape == (80, 80, 3)


@pytest.mark.parametrize("image", [None, [], np.empty((0, 0, 3), np.uint8), np.ones((2, 2, 3), np.uint8),
                                  np.ones((10, 10, 4), np.uint8), np.full((10, 10, 3), np.nan),
                                  np.full((10, 10, 3), np.inf), np.ones((10, 10, 3), np.float32)])
def test_invalid_inputs_fail_explicitly(image):
    with pytest.raises(ValueError):
        measure(image)


@pytest.mark.parametrize("level", [0, 125, 255])
def test_small_and_constant_inputs_have_no_nan_or_infinite_results(level):
    measured = measure(np.full((3, 3, 3), level, np.uint8))
    assert measured["mean_gv"] == level
    assert measured["sharpness"]["status"] == "UNAVAILABLE_ZERO_CONTRAST"
    assert measured["sharpness"]["laplacian_over_gray_variance"] is None
    assert measured["segmentation"]["foreground"] is None
    json.dumps(measured, allow_nan=False)


@pytest.mark.parametrize("roi", [{"x": -1, "y": 0, "width": 20, "height": 20},
                                 {"x": 0, "y": 0, "width": 161, "height": 20},
                                 {"x": 0, "y": 0, "width": 2, "height": 20},
                                 {"x": False, "y": 0, "width": 20, "height": 20},
                                 {"x": 0, "y": 0, "width": 20, "height": 20, "extra": 1}])
def test_invalid_roi_is_not_clipped_or_silently_repaired(roi):
    with pytest.raises(ValueError):
        crop_region(synthetic_image(), roi)


def test_boundary_roi_is_exact_and_fixed_center_survives_background_expansion():
    frame = synthetic_image()
    assert np.array_equal(crop_region(frame, {"x": 0, "y": 0, "width": 160, "height": 160}), frame)
    smaller = crop_region(frame, {"x": 20, "y": 20, "width": 120, "height": 120})
    larger = crop_region(frame, {"x": 10, "y": 10, "width": 140, "height": 140})
    first, second = measure(smaller), measure(larger)
    assert first["mean_gv"] != second["mean_gv"]
    assert first["center_fixed96"]["mean_gv"] == second["center_fixed96"]["mean_gv"]
    assert np.array_equal(larger[10:-10, 10:-10], smaller)


def test_border_touch_and_ambiguous_foregrounds_fail_without_fabricated_regions():
    border = synthetic_image()[:, 70:]
    result = measure(border)
    assert "UNAVAILABLE" in result["segmentation"]["status"]
    assert result["segmentation"]["foreground"] is None
    assert result["highlights"]["foreground_ge245_fraction"] is None
    ambiguous = np.full((160, 160, 3), 240, np.uint8)
    ambiguous[10:70, 10:70] = 60
    ambiguous[90:150, 90:150] = 60
    assert measure(ambiguous)["segmentation"]["status"] == "UNAVAILABLE_MULTIPLE_LARGE_COMPONENTS"


def test_normalization_is_affine_gain_invariant_but_reacts_to_blur():
    image = synthetic_image()
    image = (image.astype(float) * 0.5).astype(np.uint8)
    gain = image * 2
    first, second = measure(image)["sharpness"], measure(gain)["sharpness"]
    for key in ("laplacian_over_gray_variance", "tenengrad_over_gray_variance"):
        assert first[key] == pytest.approx(second[key], rel=1e-10)
        assert measure(cv2.GaussianBlur(image, (0, 0), 2))["sharpness"][key] < first[key]


def test_high_white_background_is_not_an_overexposure_verdict():
    measured = measure(synthetic_image())
    assert measured["highlights"]["ge245_fraction"] > 0.5
    assert measured["highlights"]["largest_component_touches_border"]
    assert measured["highlights"]["foreground_ge245_fraction"] == 0
    assert measured["highlights"]["background_ge245_fraction"] == 1
    assert measured["highlights"]["interpretation"] == "DIGITAL_HIGHLIGHT_MEASUREMENTS_NOT_OVEREXPOSURE_VERDICT"


def test_shared_sources_and_capture_derivatives_cannot_cross_groups():
    rows = [{"inspection_id": name, "capture_id": capture, "crop_sha256": checksum}
            for name, capture, checksum in (("A", "cap1", "a"), ("B", "cap2", "b"),
                                            ("C", "cap2", "c"), ("D", "cap4", "d"))]
    result = grouped_split(rows, {"A": ["source1"], "B": ["source1"], "C": ["source2"], "D": ["source3"]})
    assert result["A"] == result["B"] == result["C"]
    assert result["D"]["group_id"] != result["A"]["group_id"]
    assert result == grouped_split(rows, {"A": ["source1"], "B": ["source1"], "C": ["source2"], "D": ["source3"]})


def test_candidate_module_has_no_backend_network_or_database_imports():
    path = Path(__file__).parents[1] / "scripts/experiments/quality_candidates.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports.extend(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    assert not any(name.startswith(("backend", "google", "httpx", "requests", "psycopg", "sqlalchemy")) for name in imports)


def test_component_timing_is_finite_without_mutating_the_input():
    image = synthetic_image()
    original = image.copy()
    timing = benchmark_components(image)
    assert len(timing) == 4 and all(np.isfinite(value) and value >= 0 for value in timing.values())
    assert np.array_equal(image, original)
