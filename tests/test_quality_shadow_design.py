"""A-3 draft contract tests using synthetic images only, not a runtime integration."""

import ast
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from scripts.experiments.validate_quality_shadow_design import Metric, ShadowDraft, measured, probe, synthetic_source


def image_fixture():
    return np.random.default_rng(20261021).integers(0, 256, (160, 160, 3), dtype=np.uint8)


def test_reproducible_original_pixels_and_mean_rounding():
    from backend.vision import analyze_brightness

    image = image_fixture()
    original = image.copy()
    source = synthetic_source(image)
    first, second = probe(image, source), probe(image, source)
    assert first.metrics == second.metrics
    assert first.processing == second.processing
    assert np.array_equal(image, original)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    assert round(first.metrics.mean_gv.value, 2) == analyze_brightness(image)["mean"]
    assert first.metrics.gray_variance.value == float(gray.var(ddof=0))
    json.dumps(first.model_dump(mode="json"), allow_nan=False)


def test_png_hash_identity_and_file_are_unchanged(tmp_path):
    path = tmp_path / "synthetic.png"
    image = image_fixture()
    assert cv2.imwrite(str(path), image)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = probe(cv2.imread(str(path)), synthetic_source(image))
    assert result.source.crop_sha256 == before
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert result.source.inspection_id == "INSP-999999"


@pytest.mark.parametrize("shape", [(8, 8), (9, 11), (31, 60), (160, 160)])
def test_half_open_original_coordinate_regions_partition_all_pixels(shape):
    image = np.random.default_rng(1).integers(0, 256, (*shape, 3), dtype=np.uint8)
    result = probe(image, synthetic_source(image))
    left, top, right, bottom = result.processing.center_xyxy
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    assert result.metrics.center_mean_gv.value == gray[top:bottom, left:right].mean()
    center_pixels = (right - left) * (bottom - top)
    recomposed = (result.metrics.center_mean_gv.value * center_pixels + result.metrics.edge_mean_gv.value * (gray.size - center_pixels)) / gray.size
    assert result.metrics.mean_gv.value == pytest.approx(recomposed)
    assert result.metrics.edge_minus_center_gv.value == pytest.approx(result.metrics.edge_mean_gv.value - result.metrics.center_mean_gv.value)


@pytest.mark.parametrize("level", [0, 1, 255])
def test_uniform_and_extremely_dark_images_are_not_quality_verdicts(level):
    image = np.full((3, 3, 3), level, np.uint8)
    result = probe(image, synthetic_source(image))
    assert result.metrics.mean_gv.value == level
    assert result.metrics.raw_tenengrad.value == 0
    assert result.metrics.normalized_tenengrad.value is None
    assert result.metrics.normalized_tenengrad.reason == "LOW_GRAY_VARIANCE"
    assert result.metrics.center_mean_gv.reason == "TOO_SMALL_FOR_CENTER"
    assert result.status == "MEASURED_PARTIALLY"
    assert result.processing.segmentation == "NOT_REQUESTED"


def test_nonzero_but_tiny_variance_does_not_create_a_large_normalized_value():
    image = np.zeros((160, 160, 3), np.uint8)
    image[80, 80] = 1
    result = probe(image, synthetic_source(image))
    assert 0 < result.metrics.gray_variance.value < 1
    assert result.metrics.normalized_tenengrad.reason == "LOW_GRAY_VARIANCE"


@pytest.mark.parametrize("upper,available", [(1, False), (2, True)])
def test_proposed_variance_floor_has_an_explicit_boundary(upper, available):
    image = np.zeros((8, 8, 3), np.uint8)
    image[4:] = upper
    result = probe(image, synthetic_source(image))
    assert (result.metrics.normalized_tenengrad.value is not None) is available


@pytest.mark.parametrize("image", [None, np.zeros((2, 2, 3), np.uint8), np.zeros((8, 8, 4), np.uint8),
                                  np.full((8, 8, 3), np.nan), np.full((8, 8, 3), np.inf)])
def test_invalid_input_is_not_repaired_or_presented_as_success(image):
    with pytest.raises(ValueError):
        probe(image, synthetic_source(image_fixture()))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_calculation_becomes_null_and_invalid_storage_is_rejected(value):
    result = measured(value, "GV")
    assert result.value is None and result.reason == "NON_FINITE"
    with pytest.raises(ValidationError):
        Metric(value=value, unit="GV", status="MEASURED")


def test_source_dimensions_status_geometry_and_decision_fields_are_enforced():
    image = image_fixture()
    source = synthetic_source(image)
    with pytest.raises(ValueError, match="SOURCE_DIMENSIONS_MISMATCH"):
        probe(image[:100], source)
    document = probe(image, source).model_dump(mode="json")
    for key, value in (("final_result", "OK"), ("quality_status", "NORMAL"), ("judge_verdict", "NG")):
        with pytest.raises(ValidationError):
            ShadowDraft.model_validate({**document, key: value})
    with pytest.raises(ValidationError):
        ShadowDraft.model_validate({**document, "status": "NOT_MEASURED"})
    document["processing"]["center_xyxy"] = [0, 0, 160, 160]
    with pytest.raises(ValidationError):
        ShadowDraft.model_validate(document)


def test_distinct_synthetic_sources_do_not_share_identity_or_results():
    first_image = image_fixture()
    second_image = first_image // 2
    first = probe(first_image, synthetic_source(first_image))
    second_source = synthetic_source(second_image).model_copy(update={"inspection_id": "INSP-999998"})
    second = probe(second_image, second_source)
    assert first.source.inspection_id != second.source.inspection_id
    assert first.source.crop_sha256 != second.source.crop_sha256
    assert first.metrics.mean_gv.value != second.metrics.mean_gv.value


def test_wrong_units_and_out_of_range_brightness_are_rejected():
    image = image_fixture()
    document = probe(image, synthetic_source(image)).model_dump(mode="json")
    document["metrics"]["mean_gv"]["unit"] = "RATIO"
    with pytest.raises(ValidationError):
        ShadowDraft.model_validate(document)
    document["metrics"]["mean_gv"].update(unit="GV", value=256)
    with pytest.raises(ValidationError):
        ShadowDraft.model_validate(document)


@pytest.mark.parametrize("reason", ["TIMEOUT", "MODULE_EXCEPTION"])
def test_failure_envelope_contract_not_a_worker_execution_test(reason):
    image = image_fixture()
    document = probe(image, synthetic_source(image)).model_dump(mode="json")
    document["status"] = "NOT_MEASURED"
    for entry in document["metrics"].values():
        entry.update(value=None, status="NOT_MEASURED", reason=reason)
    result = ShadowDraft.model_validate(document)
    assert result.status == "NOT_MEASURED"
    json.dumps(result.model_dump(mode="json"), allow_nan=False)


def test_synthetic_gain_and_blur_are_observations_not_classification():
    gray = np.zeros((160, 160), np.uint8)
    gray[30:130, 30:130] = 180
    image = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    first = probe(image, synthetic_source(image)).metrics
    darker = image // 2
    blurred = cv2.GaussianBlur(image, (0, 0), 2)
    assert probe(darker, synthetic_source(darker)).metrics.normalized_tenengrad.value == pytest.approx(first.normalized_tenengrad.value)
    assert probe(blurred, synthetic_source(blurred)).metrics.normalized_tenengrad.value < first.normalized_tenengrad.value


def test_probe_has_no_runtime_api_storage_model_or_network_imports():
    path = Path(__file__).resolve().parents[1] / "scripts/experiments/validate_quality_shadow_design.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports.extend(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    assert not any(name.startswith(("backend", "torch", "google", "requests", "httpx", "socket", "psycopg")) for name in imports)
