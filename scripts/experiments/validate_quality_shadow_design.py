"""A-3 synthetic contract probe only; never imported by the inspection runtime."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Annotated, Literal

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments import analyze_quality_baseline as baseline
from scripts.experiments.quality_candidates import checked_image, normalized_sharpness


class DraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Source(DraftModel):
    inspection_id: Annotated[str, Field(pattern=r"^INSP-\d{6}$")]
    image_id: Annotated[str, Field(pattern=r"^IMG-[A-Za-z0-9-]+$")]
    crop_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    width: Annotated[int, Field(strict=True, ge=3, le=1920)]
    height: Annotated[int, Field(strict=True, ge=3, le=1080)]
    coordinate_system: Literal["ORIGINAL_CROP_XY_HALF_OPEN"] = "ORIGINAL_CROP_XY_HALF_OPEN"


class Metric(DraftModel):
    value: float | None
    unit: Literal["GV", "GV_SQUARED", "SOBEL_GV_SQUARED", "RATIO"]
    status: Literal["MEASURED", "NOT_MEASURED"]
    reason: Literal["TOO_SMALL_FOR_CENTER", "LOW_GRAY_VARIANCE", "NON_FINITE", "TIMEOUT", "MODULE_EXCEPTION"] | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "MEASURED":
            if self.value is None or self.reason is not None:
                raise ValueError("MEASURED_REQUIRES_FINITE_VALUE_AND_NO_REASON")
        elif self.value is not None or self.reason is None:
            raise ValueError("NOT_MEASURED_REQUIRES_NULL_AND_REASON")
        return self


class Measurements(DraftModel):
    mean_gv: Metric
    p10_gv: Metric
    p25_gv: Metric
    center_mean_gv: Metric
    edge_mean_gv: Metric
    edge_minus_center_gv: Metric
    raw_tenengrad: Metric
    gray_variance: Metric
    normalized_tenengrad: Metric

    @model_validator(mode="after")
    def domains(self):
        for name, metric in self:
            expected_unit = "SOBEL_GV_SQUARED" if name == "raw_tenengrad" else "GV_SQUARED" if name == "gray_variance" else "RATIO" if name == "normalized_tenengrad" else "GV"
            if metric.unit != expected_unit:
                raise ValueError("METRIC_UNIT_MISMATCH")
            if metric.value is None:
                continue
            lower, upper = (-255, 255) if name == "edge_minus_center_gv" else (0, 255)
            if name in {"raw_tenengrad", "gray_variance", "normalized_tenengrad"}:
                lower, upper = 0, float("inf")
            if not lower <= metric.value <= upper:
                raise ValueError("METRIC_OUT_OF_DOMAIN")
        return self


class Processing(DraftModel):
    gray_conversion: Literal["OPENCV_BGR2GRAY_UINT8"] = "OPENCV_BGR2GRAY_UINT8"
    resize: Literal["NONE"] = "NONE"
    derivative: Literal["SOBEL_3_CV64F_BORDER_REFLECT_101"] = "SOBEL_3_CV64F_BORDER_REFLECT_101"
    variance_ddof: Literal[0] = 0
    variance_floor_gv_squared: Literal[1.0] = 1.0
    center_policy: Literal["QUARTER_INSET_MIN_SIDE_8"] = "QUARTER_INSET_MIN_SIDE_8"
    center_xyxy: tuple[int, int, int, int] | None
    segmentation: Literal["NOT_REQUESTED"] = "NOT_REQUESTED"


class ShadowDraft(DraftModel):
    version: Literal["experimental-v1"] = "experimental-v1"
    mode: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    source: Source
    processing: Processing
    status: Literal["MEASURED", "MEASURED_PARTIALLY", "NOT_MEASURED"]
    measured_at: datetime
    elapsed_ms: Annotated[float, Field(ge=0)]
    metrics: Measurements

    @model_validator(mode="after")
    def consistent(self):
        measured = sum(metric.status == "MEASURED" for name, metric in self.metrics)
        expected = "MEASURED" if measured == 9 else "NOT_MEASURED" if measured == 0 else "MEASURED_PARTIALLY"
        if self.status != expected:
            raise ValueError("AGGREGATE_STATUS_MISMATCH")
        width, height = self.source.width, self.source.height
        expected_rect = (width // 4, height // 4, width - width // 4, height - height // 4) if min(width, height) >= 8 else None
        if self.processing.center_xyxy != expected_rect:
            raise ValueError("CENTER_GEOMETRY_MISMATCH")
        if self.measured_at.utcoffset() is None:
            raise ValueError("UTC_OFFSET_REQUIRED")
        return self


def measured(value, unit):
    if not np.isfinite(value):
        return Metric(value=None, unit=unit, status="NOT_MEASURED", reason="NON_FINITE")
    return Metric(value=float(value), unit=unit, status="MEASURED")


def unavailable(unit, reason):
    return Metric(value=None, unit=unit, status="NOT_MEASURED", reason=reason)


def probe(image, source):
    started = perf_counter()
    image = checked_image(image)
    if image.shape[:2] != (source.height, source.width):
        raise ValueError("SOURCE_DIMENSIONS_MISMATCH")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    p10, p25 = np.percentile(gray, [10, 25], method="linear")
    sharpness = normalized_sharpness(gray)
    variance = float(gray.var())
    values = {
        "mean_gv": measured(gray.mean(), "GV"), "p10_gv": measured(p10, "GV"), "p25_gv": measured(p25, "GV"),
        "raw_tenengrad": measured(sharpness["tenengrad"], "SOBEL_GV_SQUARED"),
        "gray_variance": measured(variance, "GV_SQUARED"),
        "normalized_tenengrad": measured(sharpness["tenengrad"] / variance, "RATIO") if variance >= 1.0 else unavailable("RATIO", "LOW_GRAY_VARIANCE"),
    }
    rectangle = None
    if min(gray.shape) >= 8:
        height, width = gray.shape
        left, top = width // 4, height // 4
        rectangle = (left, top, width - left, height - top)
        central = np.zeros_like(gray, dtype=bool)
        central[top:height - top, left:width - left] = True
        center_mean, edge_mean = gray[central].mean(), gray[~central].mean()
        values.update(center_mean_gv=measured(center_mean, "GV"), edge_mean_gv=measured(edge_mean, "GV"),
                      edge_minus_center_gv=measured(edge_mean - center_mean, "GV"))
    else:
        values.update({name: unavailable("GV", "TOO_SMALL_FOR_CENTER") for name in
                       ("center_mean_gv", "edge_mean_gv", "edge_minus_center_gv")})
    count = sum(metric.status == "MEASURED" for metric in values.values())
    return ShadowDraft(source=source, processing=Processing(center_xyxy=rectangle), metrics=Measurements(**values),
                       status="MEASURED" if count == 9 else "MEASURED_PARTIALLY" if count else "NOT_MEASURED",
                       measured_at=datetime.now(timezone.utc), elapsed_ms=(perf_counter() - started) * 1000)


def synthetic_source(image):
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise ValueError("SYNTHETIC_PNG_ENCODING_FAILED")
    return Source(inspection_id="INSP-999999", image_id="IMG-SYNTHETIC-A3", width=image.shape[1], height=image.shape[0],
                  crop_sha256=hashlib.sha256(encoded.tobytes()).hexdigest())


def protection_snapshot():
    result = baseline.snapshot([])
    paths = [ROOT / "docs" / name for name in ("a1-image-quality-baseline-analysis.md", "a2-image-quality-improvement-proposal.md", "a2-image-quality-experimental-results.md")]
    for directory in ("data/outputs/quality-analysis/a1-baseline-20261020-verified", "data/outputs/quality-analysis/a2-experiments-20261020"):
        paths.extend(path for path in (ROOT / directory).rglob("*") if path.is_file())
    for path in paths:
        try:
            result["sha256"][str(path.relative_to(ROOT))] = baseline.digest(path)
        except OSError as exc:
            result["unverified"].append({"path": str(path.relative_to(ROOT)), "error": type(exc).__name__})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--tests-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.tests_only and arguments.verify_only:
        parser.error("CHOOSE_ONE_MODE")
    output = Path(arguments.output).resolve()
    if not output.is_relative_to((ROOT / "data/outputs/quality-analysis").resolve()):
        raise ValueError("ISOLATED_ANALYSIS_OUTPUT_REQUIRED")
    if not arguments.verify_only:
        output.mkdir(parents=True, exist_ok=False)
    if arguments.tests_only:
        import os
        import platform
        import tempfile
        import pytest

        os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        platform.uname()
    counters = baseline.install_guard(output)
    if arguments.tests_only:
        temporary = output / "python-temp"
        temporary.mkdir()
        tempfile.tempdir = str(temporary)
        status = pytest.main(["-q", "--capture=sys", "--log-file=" + str(output / "pytest.log"), "-p", "no:cacheprovider",
                              "--basetemp=" + str(output / "pytest-temp"), "--junitxml=" + str(output / "unit-tests.xml"),
                              "tests/test_quality_shadow_design.py", "tests/test_quality_candidates.py", "tests/test_quality_baseline_analysis.py"])
        baseline.write_json(output / "unit-safety.json", {"pytest_exit": int(status), "io_guard": dict(counters),
                            "inputs": "SYNTHETIC_ONLY_NO_OPERATING_INTEGRATION", "metadata_preflight": "OS_UNAME_CACHED_BEFORE_IO_GUARD"})
        return int(status) if not any(counters.values()) else 2
    if arguments.verify_only:
        before = json.loads((output / "protection-before.json").read_text(encoding="utf-8"))
        after = protection_snapshot()
        changed = sorted(path for path in set(before["sha256"]) | set(after["sha256"]) if before["sha256"].get(path) != after["sha256"].get(path))
        result = {"verified_files": len(before["sha256"]), "unchanged": not changed and not before["unverified"] and not after["unverified"],
                  "changed": changed, "unverified_before": before["unverified"], "unverified_after": after["unverified"], "io_guard": dict(counters),
                  "database": "NOT_CONNECTED_CONTENT_NOT_VERIFIED"}
        baseline.write_json(output / "protection-final.json", result)
        print(json.dumps(result))
        return 0 if result["unchanged"] and not any(counters.values()) else 2
    before = protection_snapshot()
    baseline.write_json(output / "protection-before.json", before)
    if before["unverified"]:
        print(json.dumps({"status": "BLOCKED_UNREADABLE_PROTECTED_FILES", "unverified": len(before["unverified"])}))
        return 2
    cv2.setNumThreads(1)
    measurements = []
    for height, width in ((96, 96), (160, 160), (280, 280), (512, 512), (1080, 1920)):
        image = np.random.default_rng(20261021).integers(0, 256, (height, width, 3), dtype=np.uint8)
        source = synthetic_source(image)
        probe(image, source)
        elapsed = []
        for iteration in range(30):
            started = perf_counter()
            probe(image, source)
            elapsed.append((perf_counter() - started) * 1000)
        measurements.append({"width": width, "height": height, "repetitions": 30, "median_ms": float(np.median(elapsed)),
                             "p95_ms": float(np.percentile(elapsed, 95)), "max_ms": max(elapsed)})
    example = np.random.default_rng(20261021).integers(0, 256, (160, 160, 3), dtype=np.uint8)
    baseline.write_json(output / "contract-schema.json", ShadowDraft.model_json_schema())
    baseline.write_json(output / "synthetic-example.json", {"evidence_kind": "SYNTHETIC_CONTRACT_PROBE_NOT_RUNTIME", "quality_observability": probe(example, synthetic_source(example)).model_dump(mode="json")})
    baseline.write_json(output / "benchmark.json", {"kind": "SYNTHETIC_ONLY_NOT_PRODUCTION_LATENCY", "python": sys.version.split()[0],
                        "opencv": cv2.__version__, "numpy": np.__version__, "pydantic_schema": "v2", "platform": sys.platform,
                        "method": "one OpenCV thread, one warmup, 30 timed calls incl BGR2GRAY, metrics and contract validation; excluding source hash, IO and queue",
                        "measurements": measurements, "io_guard": dict(counters)})
    print(json.dumps({"status": "SYNTHETIC_PROBE_COMPLETE", "measurements": measurements, "io_guard": dict(counters)}))
    return 0 if not any(counters.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
