"""Pure original-pixel metrics and numerical-contract tests."""

import hashlib
import json
import math
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

import backend.quality_shadow_metrics as metrics
from backend.vision import analyze_brightness
from tests.quality_shadow_helpers import synthetic_input


def test_reproducibility_original_dimensions_and_existing_mean(tmp_path):
    payload, source = synthetic_input(height=49, width=67)
    path = tmp_path / "synthetic.png"
    path.write_bytes(payload)
    first, second = metrics.measure_png(payload, source), metrics.measure_png(payload, source)
    assert first["metrics"] == second["metrics"]
    assert first["processing"] == second["processing"]
    assert first["source"] == source.model_dump()
    image = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_UNCHANGED)
    assert round(first["metrics"]["mean_gv"]["value"], 2) == analyze_brightness(image)["mean"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == source.crop_sha256
    left, top, right, bottom = first["processing"]["center_xyxy"]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    assert first["metrics"]["center_mean_gv"]["value"] == gray[top:bottom, left:right].mean()
    assert first["metrics"]["gray_variance"]["value"] == pytest.approx(gray.var(), rel=1e-12)
    assert first["processing"]["resize"] == "NONE"
    json.dumps(first, allow_nan=False)


@pytest.mark.parametrize("level", [0, 1, 125, 255])
def test_uniform_images_preserve_real_metrics_without_fake_normalization(level):
    payload, source = synthetic_input(image=np.full((8, 8, 3), level, np.uint8))
    result = metrics.measure_png(payload, source)
    assert result["metrics"]["mean_gv"]["value"] == level
    assert result["metrics"]["raw_tenengrad"]["value"] == 0
    assert result["metrics"]["gray_variance"]["value"] == 0
    assert result["metrics"]["normalized_tenengrad"]["value"] is None
    assert result["metrics"]["normalized_tenengrad"]["reason"] == "ZERO_GRAY_VARIANCE"
    assert result["status"] == "MEASURED_PARTIALLY"


@pytest.mark.parametrize("height,width", [(3, 3), (7, 21), (8, 8), (9, 11)])
def test_small_and_odd_regions_are_explicit_and_not_resized(height, width):
    payload, source = synthetic_input(height=height, width=width)
    result = metrics.measure_png(payload, source)
    for name in ("center_mean_gv", "edge_mean_gv", "edge_minus_center_gv"):
        if min(height, width) < 8:
            assert result["metrics"][name]["reason"] == "TOO_SMALL_FOR_CENTER"
        else:
            assert result["metrics"][name]["status"] == "MEASURED"


@pytest.mark.parametrize("upper", [1, 2])
def test_nonzero_variance_below_one_is_not_a_new_exposure_threshold(upper):
    image = np.zeros((8, 8, 3), np.uint8)
    image[4:] = upper
    payload, source = synthetic_input(image=image)
    result = metrics.measure_png(payload, source)["metrics"]
    assert result["gray_variance"]["value"] == upper * upper / 4
    assert result["normalized_tenengrad"]["value"] is not None


def test_single_code_single_pixel_has_exact_positive_variance():
    image = np.full((160, 160, 3), 128, np.uint8)
    image[80, 80] = 129
    payload, source = synthetic_input(image=image)
    result = metrics.measure_png(payload, source)["metrics"]
    assert result["gray_variance"]["value"] == metrics.minimum_variance(25600)
    assert math.isfinite(result["normalized_tenengrad"]["value"])
    assert metrics.normalized_metric(1.0, 1e-300, 25600).reason == "NUMERICALLY_UNRESOLVED_VARIANCE"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_calculations_are_null_and_cannot_be_stored(value):
    assert metrics.value_metric("mean_gv", value).reason == "NON_FINITE"
    assert metrics.normalized_metric(1, value, 100).value is None
    with pytest.raises(ValidationError):
        metrics.Metric(value=value, unit="GV", status="MEASURED")


@pytest.mark.parametrize("kind", ["hash", "header", "dimensions", "gray", "dtype", "tiny"])
def test_invalid_inputs_are_rejected_without_repair(kind):
    payload, source = synthetic_input()
    if kind == "hash":
        payload += b"changed"
    elif kind == "header":
        payload = b"not png"
    elif kind == "dimensions":
        source = source.model_copy(update={"width": 41})
    elif kind == "gray":
        success, encoded = cv2.imencode(".png", np.zeros((32, 40), np.uint8))
        assert success
        payload = encoded.tobytes()
        source = source.model_copy(update={"crop_sha256": hashlib.sha256(payload).hexdigest()})
    elif kind == "dtype":
        with pytest.raises(ValueError):
            metrics.measure_pixels(np.full((32, 40, 3), np.nan), source)
        return
    else:
        with pytest.raises(ValidationError):
            metrics.SourceIdentity(**{**source.model_dump(), "width": 2})
        return
    with pytest.raises(ValueError):
        metrics.measure_png(payload, source)


def test_partial_sobel_failure_does_not_discard_other_metrics(monkeypatch):
    payload, source = synthetic_input()
    monkeypatch.setattr(metrics, "gradient_energy", lambda gray: (_ for unused in ()).throw(RuntimeError("private payload")))
    result = metrics.measure_png(payload, source)
    assert result["metrics"]["mean_gv"]["value"] is not None
    assert result["metrics"]["gray_variance"]["value"] is not None
    assert result["metrics"]["raw_tenengrad"]["reason"] == "METRIC_EXCEPTION"
    assert result["metrics"]["normalized_tenengrad"]["reason"] == "DEPENDENCY_UNAVAILABLE"
    assert "private payload" not in json.dumps(result)


def test_schema_rejects_judgments_inconsistent_normalization_and_units():
    payload, source = synthetic_input()
    document = metrics.measure_png(payload, source)
    with pytest.raises(ValidationError):
        metrics.ShadowResult.model_validate({**document, "final_result": "OK"})
    document["metrics"]["normalized_tenengrad"]["value"] += 1
    with pytest.raises(ValidationError):
        metrics.ShadowResult.model_validate(document)
    document = metrics.measure_png(payload, source)
    document["metrics"]["mean_gv"]["unit"] = "RATIO"
    with pytest.raises(ValidationError):
        metrics.ShadowResult.model_validate(document)


def test_exact_normalization_responds_to_synthetic_gain_and_blur_without_a_verdict():
    image = np.zeros((96, 96, 3), np.uint8)
    image[20:76, 20:76] = 100
    def normalized(candidate):
        payload, source = synthetic_input(image=candidate)
        return metrics.measure_png(payload, source)["metrics"]["normalized_tenengrad"]["value"]
    baseline = normalized(image)
    assert normalized(image // 2) == pytest.approx(baseline, rel=1e-12)
    assert normalized(cv2.GaussianBlur(image, (0, 0), 2)) < baseline


def test_calculation_cost_is_reported_not_enforced_as_accuracy():
    payload, source = synthetic_input(height=280, width=280)
    metrics.measure_png(payload, source)
    elapsed = []
    for iteration in range(30):
        started = perf_counter()
        metrics.measure_png(payload, source)
        elapsed.append((perf_counter() - started) * 1000)
    with Path("quality-shadow-timing.json").open("x", encoding="utf-8") as stream:
        json.dump({"input": "SYNTHETIC_280X280", "repetitions": 30, "includes": "PNG hash/decode, metrics, validation; excludes disk/queue",
                   "mean_ms": float(np.mean(elapsed)), "p95_ms": float(np.percentile(elapsed, 95)),
                   "opencv": cv2.__version__, "numpy": np.__version__}, stream, allow_nan=False)
