"""Original-pixel measurements only; never a quality or product verdict."""

from datetime import datetime, timezone
import hashlib
import math
import struct
from time import perf_counter
from typing import Literal

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


SCHEMA_VERSION = "quality-shadow-v1"
ALGORITHM_VERSION = "opencv-original-exact-variance-v1"
UNITS = {
    "mean_gv": "GV", "p10_gv": "GV", "p25_gv": "GV", "center_mean_gv": "GV",
    "edge_mean_gv": "GV", "edge_minus_center_gv": "GV", "raw_tenengrad": "SOBEL_GV_SQUARED",
    "normalized_tenengrad": "RATIO", "gray_variance": "GV_SQUARED",
}


class SourceIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    inspection_id: str = Field(pattern=r"^INSP-[0-9]{6,12}$")
    image_id: str = Field(pattern=r"^IMG-GRAB-[0-9a-f]{32}$")
    crop_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(strict=True, ge=3, le=1920)
    height: int = Field(strict=True, ge=3, le=1080)


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, revalidate_instances="always")
    value: float | None
    unit: Literal["GV", "GV_SQUARED", "SOBEL_GV_SQUARED", "RATIO"]
    status: Literal["MEASURED", "NOT_MEASURED"]
    reason: Literal["ZERO_GRAY_VARIANCE", "NUMERICALLY_UNRESOLVED_VARIANCE", "NON_FINITE",
                    "TOO_SMALL_FOR_CENTER", "METRIC_EXCEPTION", "DEPENDENCY_UNAVAILABLE", "COMPUTATION_FAILED"] | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "MEASURED":
            if self.value is None or self.reason is not None:
                raise ValueError("SHADOW_METRIC_STATUS_INVALID")
        elif self.value is not None or self.reason is None:
            raise ValueError("SHADOW_METRIC_REASON_REQUIRED")
        return self


def processing(source):
    width, height = source.width, source.height
    rectangle = [width // 4, height // 4, width - width // 4, height - height // 4] if min(width, height) >= 8 else None
    return {"coordinate_system": "ORIGINAL_CROP_XY_HALF_OPEN", "gray": "OPENCV_BGR2GRAY_UINT8", "resize": "NONE",
            "center_policy": "QUARTER_INSET_MIN_SIDE_8", "center_xyxy": rectangle,
            "sobel": "KSIZE3_CV64F_SCALE1_DELTA0_BORDER_REFLECT_101", "variance_ddof": 0,
            "normalization": "EXACT_UINT8_VARIANCE_POSITIVE_NO_EXPOSURE_FLOOR", "segmentation": "NOT_REQUESTED"}


class ShadowResult(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, revalidate_instances="always")
    schema_version: Literal["quality-shadow-v1"]
    algorithm_version: Literal["opencv-original-exact-variance-v1"]
    mode: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    source: SourceIdentity
    processing: dict
    metrics: dict[str, Metric]
    status: Literal["MEASURED", "MEASURED_PARTIALLY", "NOT_MEASURED"]
    measured_at: datetime
    elapsed_ms: float = Field(ge=0)

    @model_validator(mode="after")
    def consistent(self):
        if set(self.metrics) != set(UNITS) or self.processing != processing(self.source):
            raise ValueError("SHADOW_CONTRACT_INVALID")
        count = 0
        for name, metric in self.metrics.items():
            if metric.unit != UNITS[name]:
                raise ValueError("SHADOW_UNIT_INVALID")
            if metric.value is None:
                continue
            count += 1
            lower = -255 if name == "edge_minus_center_gv" else 0
            upper = 255 if UNITS[name] == "GV" else math.inf
            if not lower <= metric.value <= upper:
                raise ValueError("SHADOW_RANGE_INVALID")
        expected = "MEASURED" if count == len(UNITS) else "NOT_MEASURED" if not count else "MEASURED_PARTIALLY"
        if self.status != expected or self.measured_at.utcoffset() is None:
            raise ValueError("SHADOW_STATUS_OR_TIME_INVALID")
        center = self.metrics["center_mean_gv"]
        edge = self.metrics["edge_mean_gv"]
        difference = self.metrics["edge_minus_center_gv"]
        if self.processing["center_xyxy"] is None and any(metric.value is not None for metric in (center, edge, difference)):
            raise ValueError("SHADOW_CENTER_INVALID")
        if difference.value is not None and (center.value is None or edge.value is None or not math.isclose(difference.value, edge.value - center.value, abs_tol=1e-10)):
            raise ValueError("SHADOW_DIFFERENCE_INVALID")
        mean = self.metrics["mean_gv"].value
        rectangle = self.processing["center_xyxy"]
        if rectangle is not None and all(metric.value is not None for metric in (center, edge)) and mean is not None:
            left, top, right, bottom = rectangle
            center_pixels = (right - left) * (bottom - top)
            pixels = self.source.width * self.source.height
            reconstructed = (center.value * center_pixels + edge.value * (pixels - center_pixels)) / pixels
            if not math.isclose(mean, reconstructed, abs_tol=1e-10, rel_tol=1e-12):
                raise ValueError("SHADOW_MEAN_GEOMETRY_INVALID")
        normalized = self.metrics["normalized_tenengrad"].value
        if normalized is not None:
            raw, variance = self.metrics["raw_tenengrad"].value, self.metrics["gray_variance"].value
            pixels = self.source.width * self.source.height
            if raw is None or variance is None or variance < minimum_variance(pixels) or not math.isclose(normalized, raw / variance, rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError("SHADOW_NORMALIZATION_INVALID")
        return self


def missing(name, reason):
    return Metric(value=None, unit=UNITS[name], status="NOT_MEASURED", reason=reason)


def value_metric(name, value):
    if not math.isfinite(float(value)):
        return missing(name, "NON_FINITE")
    return Metric(value=float(value), unit=UNITS[name], status="MEASURED")


def minimum_variance(pixels):
    return (pixels - 1) / (pixels * pixels)


def normalized_metric(raw, variance, pixels):
    if not math.isfinite(raw) or not math.isfinite(variance):
        return missing("normalized_tenengrad", "NON_FINITE")
    if variance == 0:
        return missing("normalized_tenengrad", "ZERO_GRAY_VARIANCE")
    if variance < minimum_variance(pixels):
        return missing("normalized_tenengrad", "NUMERICALLY_UNRESOLVED_VARIANCE")
    return value_metric("normalized_tenengrad", raw / variance)


def validate_png(payload, source):
    if (not isinstance(payload, bytes) or not 33 <= len(payload) <= 16 * 1024 * 1024
            or payload[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            or hashlib.sha256(payload).hexdigest() != source.crop_sha256):
        raise ValueError("SHADOW_PNG_OR_HASH_INVALID")
    width, height = struct.unpack(">II", payload[16:24])
    if (width, height) != (source.width, source.height):
        raise ValueError("SHADOW_DIMENSIONS_INVALID")
    image = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None or image.dtype != np.uint8 or image.shape != (height, width, 3):
        raise ValueError("SHADOW_BGR_UINT8_REQUIRED")
    return image


def finish(source, metrics, elapsed_ms):
    count = sum(metric.value is not None for metric in metrics.values())
    return ShadowResult(schema_version=SCHEMA_VERSION, algorithm_version=ALGORITHM_VERSION,
                        source=source, processing=processing(source), metrics=metrics,
                        status="MEASURED" if count == len(UNITS) else "NOT_MEASURED" if not count else "MEASURED_PARTIALLY",
                        measured_at=datetime.now(timezone.utc), elapsed_ms=elapsed_ms)


def failed_result(source, elapsed_ms):
    return finish(source, {name: missing(name, "COMPUTATION_FAILED") for name in UNITS}, elapsed_ms)


def gradient_energy(gray):
    gradient_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3, borderType=cv2.BORDER_REFLECT_101)
    gradient_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3, borderType=cv2.BORDER_REFLECT_101)
    return float(np.mean(gradient_x ** 2 + gradient_y ** 2))


def exact_variance(gray):
    integers = gray.astype(np.uint64)
    pixels = gray.size
    total = int(integers.sum())
    squares = int((integers * integers).sum())
    return (pixels * squares - total * total) / (pixels * pixels)


def measure_pixels(image, source):
    started = perf_counter()
    if (not isinstance(image, np.ndarray) or image.dtype != np.uint8
            or image.shape != (source.height, source.width, 3)):
        raise ValueError("SHADOW_INPUT_INVALID")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    metrics = {name: missing(name, "METRIC_EXCEPTION") for name in UNITS}
    for name, operation in (
        ("mean_gv", lambda: gray.mean()), ("p10_gv", lambda: np.percentile(gray, 10, method="linear")),
        ("p25_gv", lambda: np.percentile(gray, 25, method="linear")),
        ("gray_variance", lambda: exact_variance(gray)), ("raw_tenengrad", lambda: gradient_energy(gray)),
    ):
        try:
            metrics[name] = value_metric(name, operation())
        except Exception:
            metrics[name] = missing(name, "METRIC_EXCEPTION")
    rectangle = processing(source)["center_xyxy"]
    if rectangle is None:
        for name in ("center_mean_gv", "edge_mean_gv", "edge_minus_center_gv"):
            metrics[name] = missing(name, "TOO_SMALL_FOR_CENTER")
    else:
        try:
            left, top, right, bottom = rectangle
            central = np.zeros_like(gray, dtype=bool)
            central[top:bottom, left:right] = True
            center, edge = float(gray[central].mean()), float(gray[~central].mean())
            for name, value in (("center_mean_gv", center), ("edge_mean_gv", edge), ("edge_minus_center_gv", edge - center)):
                metrics[name] = value_metric(name, value)
        except Exception:
            pass
    raw, variance = metrics["raw_tenengrad"].value, metrics["gray_variance"].value
    metrics["normalized_tenengrad"] = (normalized_metric(raw, variance, gray.size) if raw is not None and variance is not None
                                         else missing("normalized_tenengrad", "DEPENDENCY_UNAVAILABLE"))
    return finish(source, metrics, (perf_counter() - started) * 1000)


def measure_png(payload, source):
    return measure_pixels(validate_png(payload, source), source).model_dump(mode="json")
