"""Read-only inspection artifact audit; no backend imports or service requests."""

import hashlib
import json
from pathlib import Path
import struct

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/outputs"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_records(path):
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def snapshot():
    paths = [ROOT / "data/inspections.jsonl", ROOT / "data/inspection_logs.jsonl"]
    for name in ("captures", "grab_inspection_inputs", "inspection_anomaly_maps", "agent_reports"):
        paths.extend(path for path in (OUTPUT / name).glob("*") if path.is_file())
    for name in ("reinspection_history", "vision_reviews"):
        path = OUTPUT / name / "state.json"
        if path.is_file():
            paths.append(path)
    return {str(path.relative_to(ROOT)): digest(path) for path in sorted(paths)}


def inspect_grab(record, log_counts):
    provenance = record["metrics"]["input_provenance"]
    identifier = record["inspection_id"]
    image_id = record["image_id"]
    result = {"inspection_id": identifier, "capture_id": provenance.get("capture_id"),
        "video_id": provenance.get("video_id"), "frame_index": provenance.get("frame_index"),
        "roi": provenance.get("roi"), "crop_dimensions": [provenance.get("crop_width"), provenance.get("crop_height")],
        "image_id": image_id, "final_result": record.get("final_result"), "execution_log_count": log_counts.get(identifier, 0)}
    try:
        directory = OUTPUT / "grab_inspection_inputs"
        path = directory / (image_id + ".png")
        if path.resolve().parent != directory.resolve() or path.is_symlink():
            raise ValueError("Unexpected input path")
        raw = path.read_bytes()
        result["crop_path"] = str(path.relative_to(ROOT))
        result["crop_sha256_matches_record"] = hashlib.sha256(raw).hexdigest() == provenance.get("crop_sha256")
        result["crop_dimensions_match"] = struct.unpack(">II", raw[16:24]) == (provenance.get("crop_width"), provenance.get("crop_height"))
        metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        result["crop_manifest_matches"] = metadata.get("image_id") == image_id and metadata.get("crop_sha256") == provenance.get("crop_sha256")
    except (OSError, ValueError, KeyError, TypeError, struct.error) as error:
        result["crop_validation_error"] = type(error).__name__
    result.update(inspect_map(identifier, image_id, provenance.get("crop_width"), provenance.get("crop_height")))
    return result


def inspect_map(identifier, image_id, width, height):
    directory = OUTPUT / "inspection_anomaly_maps"
    try:
        metadata = json.loads((directory / (identifier + ".json")).read_text(encoding="utf-8"))
        npz_path = directory / (identifier + ".npz")
        overlay_path = directory / (identifier + "_overlay.png")
        hashes = metadata.get("artifact_sha256", {})
        with np.load(npz_path, allow_pickle=False) as stored:
            signal = stored["anomaly_map"]
            map_valid = signal.dtype == np.float32 and signal.shape == (256, 256) and bool(np.isfinite(signal).all())
        overlay = overlay_path.read_bytes()
        return {"map_bundle_present": True, "map_ids_and_dimensions_match": metadata.get("inspection_id") == identifier
                and metadata.get("image_id") == image_id and metadata.get("original_image_width") == width
                and metadata.get("original_image_height") == height,
            "map_array_valid": map_valid,
            "overlay_dimensions_match": struct.unpack(">II", overlay[16:24]) == (width, height),
            "npz_hash_matches_metadata": digest(npz_path) == hashes["npz"] if "npz" in hashes else "UNKNOWN_NO_RECORDED_HASH",
            "overlay_hash_matches_metadata": hashlib.sha256(overlay).hexdigest() == hashes["overlay"] if "overlay" in hashes else "UNKNOWN_NO_RECORDED_HASH"}
    except (OSError, ValueError, KeyError, TypeError, struct.error) as error:
        return {"map_validation_error": type(error).__name__}


def main():
    before = snapshot()
    records = read_records(ROOT / "data/inspections.jsonl")
    logs = read_records(ROOT / "data/inspection_logs.jsonl")
    log_counts = {}
    for entry in logs:
        identifier = entry.get("inspection_id")
        log_counts[identifier] = log_counts.get(identifier, 0) + 1
    grabs = [record for record in records if record.get("metrics", {}).get("input_source") == "LIVEVIEW_GRAB"]
    current_captures = sorted(path.stem for path in (OUTPUT / "captures").glob("CAP-*.png"))
    reports = []
    for path in sorted((OUTPUT / "agent_reports").glob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        identifier = report.get("inspection_id")
        reports.append({"filename": path.name, "inspection_id": identifier,
            "filename_matches_id": path.stem == identifier, "analysis_id": report.get("analysis_id", "UNKNOWN"),
            "analysis_status": report.get("analysis_status", "UNKNOWN"), "provenance": report.get("provenance", "UNKNOWN"),
            "inspection_exists": any(record.get("inspection_id") == identifier for record in records)})
    static_maps = []
    for path in sorted((OUTPUT / "inspection_anomaly_maps").glob("INSP-*.json")):
        identifier = path.stem
        if any(record["inspection_id"] == identifier for record in grabs):
            continue
        matching = [record for record in records if record.get("inspection_id") == identifier]
        metadata = json.loads(path.read_text(encoding="utf-8"))
        static_maps.append({"inspection_id": identifier, "record_count": len(matching),
            "image_id_matches_record": len(matching) == 1 and matching[0].get("image_id") == metadata.get("image_id"),
            **inspect_map(identifier, metadata.get("image_id"), metadata.get("original_image_width"), metadata.get("original_image_height"))})
    after = snapshot()
    output = {"readonly_audit": True, "protected_file_count": len(before), "protected_files_unchanged": before == after,
        "inspection_rows": len(records), "log_rows": len(logs),
        "duplicate_inspection_ids": len(records) - len({record["inspection_id"] for record in records}),
        "current_capture_ids": current_captures,
        "current_capture_related_inspections": [record["inspection_id"] for record in grabs
            if record["metrics"]["input_provenance"].get("capture_id") in current_captures],
        "grab_inspections": [inspect_grab(record, log_counts) for record in grabs],
        "registered_image_maps": static_maps, "agent_reports": reports,
        "reinspection_state_exists": (OUTPUT / "reinspection_history/state.json").is_file(),
        "vision_state_exists": (OUTPUT / "vision_reviews/state.json").is_file()}
    final = snapshot()
    output["protected_files_unchanged"] = output["protected_files_unchanged"] and final == before
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["protected_files_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
