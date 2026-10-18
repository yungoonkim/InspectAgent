"""Immutable anomaly-map bundles with commit-last publication and read-only retrieval."""

import hashlib
import json
import logging
import os
from pathlib import Path
import re
import struct
import tempfile
import zipfile
from typing import Any, Dict, Optional

import cv2
import numpy as np

logger = logging.getLogger("vision_insight.anomaly_map_store")
INSPECTION_ID_REGEX = re.compile(r"INSP-[A-Za-z0-9_-]{1,32}")
DEFAULT_ANOMALY_MAP_DIR = Path("data/outputs/inspection_anomaly_maps")


def get_anomaly_map_dir() -> Path:
    from backend.config import PROJECT_ROOT
    target = Path(os.environ.get("ANOMALY_MAP_DIR", str(DEFAULT_ANOMALY_MAP_DIR)))
    return (PROJECT_ROOT / target).resolve()


def is_valid_inspection_id(inspection_id: str) -> bool:
    return isinstance(inspection_id, str) and INSPECTION_ID_REGEX.fullmatch(inspection_id) is not None


def _safe_file(directory: Path, name: str) -> Path:
    path = directory / name
    if path.is_symlink() or path.resolve().parent != directory.resolve():
        raise ValueError("Invalid artifact path")
    return path


def _dimensions(width, height):
    if any(isinstance(value, bool) or not isinstance(value, (int, np.integer)) for value in (width, height)):
        raise ValueError("Invalid image dimensions")
    if not 1 <= width <= 4096 or not 1 <= height <= 4096:
        raise ValueError("Image dimensions exceed visualization limits")
    return int(width), int(height)


def save_anomaly_map_artifact(
    inspection_id: str, image_id: str, anomaly_map: np.ndarray, original_width: int, original_height: int,
    model_name: str = "PatchCore", anomaly_score: Optional[float] = None,
    decision_threshold: Optional[float] = None, custom_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    if not is_valid_inspection_id(inspection_id) or inspection_id == "INSP-001391":
        raise ValueError("Unavailable or malformed inspection ID")
    if not isinstance(image_id, str) or re.fullmatch(r"IMG-[A-Za-z0-9_-]{1,64}", image_id) is None:
        raise ValueError("Invalid image identifier")
    if not isinstance(anomaly_map, np.ndarray) or anomaly_map.ndim != 2 or anomaly_map.dtype.kind not in "fiu":
        raise ValueError("Expected a numeric two-dimensional anomaly map")
    map_height, map_width = anomaly_map.shape
    if not 16 <= map_width <= 2048 or not 16 <= map_height <= 2048:
        raise ValueError("Invalid anomaly map dimensions")
    width, height = _dimensions(original_width, original_height)
    clean_map = np.nan_to_num(anomaly_map.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    minimum, maximum = float(clean_map.min()), float(clean_map.max())
    normalized = (clean_map - minimum) / (maximum - minimum) if maximum > minimum else np.zeros_like(clean_map)
    resized = cv2.resize(normalized, (width, height), interpolation=cv2.INTER_LINEAR)
    color = cv2.applyColorMap((np.clip(resized, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_JET)
    alpha = (np.power(np.clip((resized - 0.15) / 0.85, 0, 1), 1.3) * 210).astype(np.uint8)
    success, encoded = cv2.imencode(".png", np.dstack((color, alpha)))
    if not success:
        raise RuntimeError("Overlay encoding failed")
    directory = Path(custom_dir) if custom_dir is not None else get_anomaly_map_dir()
    directory.mkdir(parents=True, exist_ok=True)
    names = [f"{inspection_id}.npz", f"{inspection_id}_overlay.png", f"{inspection_id}.json"]
    targets = [_safe_file(directory, name) for name in names]
    lock = _safe_file(directory, f".{inspection_id}.lock")
    lock_descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    published = []
    try:
        if any(target.exists() for target in targets):
            raise FileExistsError("Anomaly map artifacts are immutable")
        with tempfile.TemporaryDirectory(prefix=f".{inspection_id}-", dir=directory) as temporary:
            staging = Path(temporary)
            with (staging / names[0]).open("wb") as stream:
                np.savez_compressed(stream, anomaly_map=clean_map)
            (staging / names[1]).write_bytes(encoded.tobytes())
            metadata = {
                "schema_version": "1.1.0", "inspection_id": inspection_id, "image_id": image_id,
                "model_name": model_name,
                "anomaly_score": round(anomaly_score, 4) if anomaly_score is not None else None,
                "decision_threshold": round(decision_threshold, 4) if decision_threshold is not None else None,
                "original_image_width": width, "original_image_height": height,
                "anomaly_map_width": map_width, "anomaly_map_height": map_height,
                "spatial_transform": {
                    "type": "axis_aligned_resize", "model_input_resolution": [map_width, map_height],
                    "original_resolution": [width, height], "crop": None, "padding": None,
                    "coordinate_convention": "pixel_centers_half_open_edges",
                    "map_to_original_center": "(index + 0.5) * original_size / map_size - 0.5",
                    "interpolation": "opencv_INTER_LINEAR", "flip": False,
                },
                "range": {"min": round(minimum, 4), "max": round(maximum, 4), "mean": round(float(clean_map.mean()), 4)},
                "localization_available": True, "overlay_filename": names[1], "npz_filename": names[0],
                "artifact_sha256": {
                    "npz": hashlib.sha256((staging / names[0]).read_bytes()).hexdigest(),
                    "overlay": hashlib.sha256(encoded.tobytes()).hexdigest(),
                },
            }
            (staging / names[2]).write_text(json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8")
            for name, target in zip(names, targets):
                os.link(staging / name, target)
                published.append(target)
        return metadata
    except BaseException:
        for target in reversed(published):
            target.unlink(missing_ok=True)
        raise
    finally:
        os.close(lock_descriptor)
        lock.unlink(missing_ok=True)


def get_anomaly_map_metadata(inspection_id: str, custom_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    if not is_valid_inspection_id(inspection_id) or inspection_id == "INSP-001391":
        return None
    directory = Path(custom_dir) if custom_dir is not None else get_anomaly_map_dir()
    try:
        target = _safe_file(directory, f"{inspection_id}.json")
        if not target.is_file() or target.stat().st_size > 65536:
            return None
        metadata = json.loads(target.read_text(encoding="utf-8"))
        if metadata.get("inspection_id") != inspection_id or metadata.get("localization_available") is not True:
            return None
        if metadata.get("schema_version") not in ("1.0.0", "1.1.0"):
            return None
        if re.fullmatch(r"IMG-[A-Za-z0-9_-]{1,64}", metadata.get("image_id", "")) is None:
            return None
        width, height = _dimensions(metadata["original_image_width"], metadata["original_image_height"])
        map_width, map_height = metadata["anomaly_map_width"], metadata["anomaly_map_height"]
        if any(type(value) is not int or not 16 <= value <= 2048 for value in (map_width, map_height)):
            return None
        transform = metadata.get("spatial_transform", {})
        if (transform.get("type") not in ("isotropic_linear_resize", "axis_aligned_resize")
                or transform.get("crop") is not None or transform.get("padding") is not None
                or transform.get("flip", False) is not False
                or transform.get("model_input_resolution") != [map_width, map_height]
                or transform.get("original_resolution") != [width, height]):
            return None
        if metadata.get("npz_filename") != f"{inspection_id}.npz" or metadata.get("overlay_filename") != f"{inspection_id}_overlay.png":
            return None
        npz = _safe_file(directory, metadata["npz_filename"])
        overlay = _safe_file(directory, metadata["overlay_filename"])
        if not npz.is_file() or not overlay.is_file() or npz.stat().st_size > 20 * 1024 * 1024 or overlay.stat().st_size > 64 * 1024 * 1024:
            return None
        hashes = metadata.get("artifact_sha256")
        if metadata["schema_version"] == "1.1.0" and not isinstance(hashes, dict):
            return None
        if hashes is not None and (hashlib.sha256(npz.read_bytes()).hexdigest() != hashes["npz"]
                                  or hashlib.sha256(overlay.read_bytes()).hexdigest() != hashes["overlay"]):
            return None
        with zipfile.ZipFile(npz) as archive:
            if len(archive.infolist()) != 1 or archive.infolist()[0].file_size > 2048 * 2048 * 4 + 1024:
                return None
        with np.load(npz, allow_pickle=False) as stored:
            signal = stored["anomaly_map"]
            if signal.dtype != np.float32 or signal.shape != (map_height, map_width) or not np.isfinite(signal).all():
                return None
        raw = overlay.read_bytes()
        if raw[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", raw[16:24]) != (width, height):
            return None
        decoded = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if decoded is None or decoded.shape != (height, width, 4):
            return None
        return metadata
    except (OSError, ValueError, TypeError, KeyError, AttributeError, struct.error, zipfile.BadZipFile, cv2.error):
        return None


def get_anomaly_map_overlay_path(inspection_id: str, custom_dir: Optional[Path] = None) -> Optional[Path]:
    metadata = get_anomaly_map_metadata(inspection_id, custom_dir)
    if metadata is None:
        return None
    directory = Path(custom_dir) if custom_dir is not None else get_anomaly_map_dir()
    return _safe_file(directory, metadata["overlay_filename"])
