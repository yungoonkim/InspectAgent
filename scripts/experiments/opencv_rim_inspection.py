"""Local, experimental rim geometry measurements on verified PNG pixels."""

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import time
from uuid import uuid4

import cv2
import numpy as np


@dataclass(frozen=True)
class RimParameters:
    minimum_contrast: float = 12.0
    minimum_edge_support: float = 0.60
    angular_bins: int = 180
    canny_low: int = 30
    canny_high: int = 90


def decode_png(raw):
    if len(raw) < 24 or len(raw) > 4 * 1024 * 1024 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise ValueError("PNG_REQUIRED")
    width, height = struct.unpack(">II", raw[16:24])
    if not 16 <= width <= 1920 or not 16 <= height <= 1080:
        raise ValueError("UNSUPPORTED_IMAGE_DIMENSIONS")
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None or image.dtype != np.uint8 or image.shape != (height, width, 3):
        raise ValueError("UINT8_THREE_CHANNEL_PNG_REQUIRED")
    return image


def _edge_support(edges, center_x, center_y, radius, bins):
    angles = np.arange(bins) * (2 * math.pi / bins)
    offsets = np.linspace(-max(2.0, radius * 0.045), max(2.0, radius * 0.045), 9)
    column = np.rint(center_x + (radius + offsets[:, None]) * np.cos(angles)).astype(int)
    row = np.rint(center_y + (radius + offsets[:, None]) * np.sin(angles)).astype(int)
    inside = (column >= 0) & (row >= 0) & (column < edges.shape[1]) & (row < edges.shape[0])
    values = np.zeros(column.shape, dtype=bool)
    values[inside] = edges[row[inside], column[inside]] > 0
    return values.any(axis=0), inside.any(axis=0)


def _unsupported_arcs(supported, center_x, center_y, radius):
    if supported.all() or not supported.any():
        return []
    anchor = int(np.flatnonzero(supported)[0])
    shifted = np.roll(supported, -anchor)
    regions = []
    start = None
    for index in range(1, len(shifted) + 1):
        missing = index < len(shifted) and not shifted[index]
        if missing and start is None:
            start = index
        if not missing and start is not None:
            span = (index - start) * 360 / len(shifted)
            if span >= 12:
                middle = (anchor + (start + index) / 2) * 2 * math.pi / len(shifted)
                regions.append({"kind": "UNSUPPORTED_EDGE_ARC_NOT_CONFIRMED_DEFECT",
                    "start_degrees": ((anchor + start) * 360 / len(shifted)) % 360,
                    "span_degrees": span, "x": float(center_x + radius * math.cos(middle)),
                    "y": float(center_y + radius * math.sin(middle))})
            start = None
    return sorted(regions, key=lambda item: item["span_degrees"], reverse=True)[:6]


def measure_png(raw, input_id, parameters=None):
    started = time.perf_counter()
    parameters = parameters or RimParameters()
    if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", input_id or "") is None:
        raise ValueError("NEUTRAL_INPUT_ID_REQUIRED")
    image = decode_png(raw)
    overlay = image.copy()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    contrast = float(np.percentile(gray, 95) - np.percentile(gray, 5))
    result = {"analysis_id": "OCV-" + uuid4().hex, "input_id": input_id,
        "analysis_mode": "EXPERIMENTAL_OPENCV", "created_at": datetime.now(timezone.utc).isoformat(),
        "image_sha256": hashlib.sha256(raw).hexdigest(), "width": image.shape[1], "height": image.shape[0],
        "opencv_version": cv2.__version__, "parameters": asdict(parameters),
        "parameter_basis": "Engineering measurement eligibility guards; not calibrated defect thresholds",
        "status": "UNKNOWN", "reason": None, "gray_mean": float(gray.mean()),
        "gray_percentile_contrast": contrast, "features": None, "detected_contour": [],
        "suspected_regions": [], "product_verdict": "NOT_EVALUATED",
        "limitations": ["Circle/edge support is not a calibrated confidence probability.",
            "Reflections, other round objects, perspective and Crop placement can affect detection.",
            "Unsupported arcs are observations, not verified physical defects."]}
    blurred = cv2.GaussianBlur(gray, (5, 5), 1.0)
    edges = cv2.Canny(blurred, parameters.canny_low, parameters.canny_high)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    minimum_radius = max(8, int(min(gray.shape) * 0.12))
    maximum_radius = int(min(gray.shape) * 0.48)
    candidates = []
    if contrast >= parameters.minimum_contrast:
        circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, dp=1, minDist=min(gray.shape) / 4,
            param1=parameters.canny_high, param2=25, minRadius=minimum_radius, maxRadius=maximum_radius)
        if circles is not None:
            candidates.extend((float(circle[0]), float(circle[1]), float(circle[2]), None)
                for circle in circles[0][:32])
        for contour in contours:
            if len(contour) < 20:
                continue
            perimeter = cv2.arcLength(contour, True)
            circularity = 4 * math.pi * cv2.contourArea(contour) / max(perimeter ** 2, 1)
            (center_x, center_y), (axis_x, axis_y), _ = cv2.fitEllipse(contour)
            radius = (axis_x + axis_y) / 4
            if minimum_radius <= radius <= maximum_radius and min(axis_x, axis_y) / max(axis_x, axis_y) >= 0.7 and circularity >= 0.5:
                candidates.append((center_x, center_y, radius, contour))
    ranked = []
    for center_x, center_y, radius, contour in candidates:
        supported, inside = _edge_support(edges, center_x, center_y, radius, parameters.angular_bins)
        if not inside.all():
            continue
        rank = float(supported.mean()) + 0.03 * radius / maximum_radius
        ranked.append((rank, center_x, center_y, radius, contour, supported))
    if contrast < parameters.minimum_contrast:
        result["reason"] = "INSUFFICIENT_IMAGE_CONTRAST"
    elif not ranked:
        result["reason"] = "NO_SUPPORTED_RIM_CANDIDATE"
    else:
        _, center_x, center_y, radius, contour, supported = max(ranked, key=lambda value: value[0])
        support = float(supported.mean())
        features = {"center_x": float(center_x), "center_y": float(center_y), "radius_pixels": float(radius),
            "rim_edge_support_fraction": support, "circularity": None, "radial_std_pixels": None,
            "contour_points": 0}
        if contour is not None:
            points = contour[:, 0, :]
            distances = np.linalg.norm(points - np.array([center_x, center_y]), axis=1)
            perimeter = cv2.arcLength(contour, True)
            features.update({"circularity": float(4 * math.pi * cv2.contourArea(contour) / max(perimeter ** 2, 1)),
                "radial_std_pixels": float(distances.std()), "contour_points": len(points)})
            result["detected_contour"] = points[::max(1, math.ceil(len(points) / 256))].tolist()
            cv2.drawContours(overlay, [contour], -1, (255, 255, 0), 1)
        result["features"] = features
        result["suspected_regions"] = _unsupported_arcs(supported, center_x, center_y, radius)
        result["status"] = "MEASURED" if support >= parameters.minimum_edge_support else "UNKNOWN"
        result["reason"] = "GEOMETRY_ONLY_NOT_A_DEFECT_VERDICT" if result["status"] == "MEASURED" else "INSUFFICIENT_RIM_EDGE_SUPPORT"
        cv2.circle(overlay, (round(center_x), round(center_y)), round(radius), (0, 255, 0), 1)
        cv2.drawMarker(overlay, (round(center_x), round(center_y)), (0, 255, 0), markerSize=8)
        for region in result["suspected_regions"]:
            cv2.circle(overlay, (round(region["x"]), round(region["y"])), 4, (0, 180, 255), 1)
    cv2.putText(overlay, "OPENCV " + result["status"] + " - MEASUREMENT ONLY", (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (255, 255, 0), 1)
    success, encoded = cv2.imencode(".png", overlay)
    if not success:
        raise ValueError("OVERLAY_ENCODING_FAILED")
    result["elapsed_ms"] = (time.perf_counter() - started) * 1000
    return result, encoded.tobytes()


def load_inspection_crop(project_root, inspection_id):
    if re.fullmatch(r"INSP-[0-9]{6,12}", inspection_id or "") is None:
        raise ValueError("INVALID_INSPECTION_ID")
    root = Path(project_root)
    matches = []
    with (root / "data/inspections.jsonl").open(encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            if record.get("inspection_id") == inspection_id:
                matches.append(record)
    if len(matches) != 1:
        raise ValueError("INSPECTION_MISSING_OR_AMBIGUOUS")
    record = matches[0]
    source = record.get("metrics", {}).get("input_provenance", {})
    image_id = record.get("image_id", "")
    if record.get("metrics", {}).get("input_source") != "LIVEVIEW_GRAB" or re.fullmatch(r"IMG-GRAB-[0-9a-f]{32}", image_id) is None:
        raise ValueError("MANAGED_GRAB_REQUIRED")
    directory = root / "data/outputs/grab_inspection_inputs"
    path = directory / (image_id + ".png")
    if any(parent.is_symlink() for parent in [path, *path.parents]) or path.resolve().parent != directory.resolve():
        raise ValueError("LINKED_IMAGE_PATH_REJECTED")
    raw = path.read_bytes()
    image = decode_png(raw)
    if (hashlib.sha256(raw).hexdigest() != source.get("crop_sha256")
            or image.shape[:2] != (source.get("crop_height"), source.get("crop_width"))):
        raise ValueError("CROP_PROVENANCE_MISMATCH")
    return raw, path


def synthetic_inputs():
    for identifier, radius in [("SYN-RIM-001", 80), ("SYN-RIM-002", 55), ("SYN-RIM-003", None)]:
        image = np.full((256, 256, 3), 60, np.uint8)
        if radius is not None:
            cv2.circle(image, (128, 128), radius, (220, 220, 220), 6)
        success, encoded = cv2.imencode(".png", image)
        if not success:
            raise ValueError("SYNTHETIC_ENCODING_FAILED")
        yield identifier, encoded.tobytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--inspection-id")
    selection.add_argument("--synthetic", action="store_true")
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = Path(arguments.output).absolute()
    experiment_root = (root / "data/outputs/experiments").resolve()
    if experiment_root not in output.resolve().parents or any(parent.is_symlink() for parent in [output, *output.parents]):
        parser.error("Output must be a new directory under data/outputs/experiments")
    source_path = None
    if arguments.inspection_id:
        raw, source_path = load_inspection_crop(root, arguments.inspection_id)
        inputs = [(arguments.inspection_id, raw)]
    else:
        inputs = list(synthetic_inputs())
    output.mkdir(parents=True, exist_ok=False)
    for identifier, raw in inputs:
        result, overlay = measure_png(raw, identifier)
        overlay_name = identifier + "_overlay.png"
        result["overlay_path"] = overlay_name
        result["overlay_sha256"] = hashlib.sha256(overlay).hexdigest()
        result["input_source"] = "SAVED_LIVEVIEW_GRAB" if source_path else "SYNTHETIC_GEOMETRY_TEST"
        if source_path and hashlib.sha256(source_path.read_bytes()).hexdigest() != result["image_sha256"]:
            raise ValueError("SOURCE_CHANGED_DURING_ANALYSIS")
        with (output / overlay_name).open("xb") as target:
            target.write(overlay)
        with (output / (identifier + ".json")).open("x", encoding="utf-8") as target:
            json.dump(result, target, indent=2, ensure_ascii=False, allow_nan=False)
        print(json.dumps({"input_id": identifier, "status": result["status"], "reason": result["reason"], "features": result["features"], "elapsed_ms": result["elapsed_ms"]}))


if __name__ == "__main__":
    main()
