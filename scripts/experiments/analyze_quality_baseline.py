"""Offline A-1 measurements only; never an inspection or a production quality policy."""

import argparse
import ast
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
VIDEOS = {
    "VID-000002": ("bottle_conveyor_bright_no_lines_h264_1920x480_8s.mp4",
                   "2eaee8ad99835600137ed54c1cfee25b009e22f41023fc1b41a08584ff314991"),
    "VID-000003": ("bottle_conveyor_mixed_ok_ng_16s_h264_1920x480.mp4",
                   "bcdf19620579a60b4d7211f6cb7e2db948336b240b0ac78114c18bb2359ef7d5"),
}
CASES = ("INSP-001695", "INSP-001704", "INSP-001702")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def write_png(path, image):
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise RuntimeError("PNG_ENCODING_FAILED")
    with path.open("xb") as stream:
        stream.write(encoded.tobytes())


def read_png(path):
    raw = path.read_bytes()
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("PNG_DECODE_FAILED")
    return image, hashlib.sha256(raw).hexdigest()


def metrics(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    if gray.dtype != np.uint8 or gray.ndim != 2 or min(gray.shape) < 3:
        raise ValueError("UINT8_IMAGE_AT_LEAST_3X3_REQUIRED")
    percentiles = np.percentile(gray, [1, 5, 25, 50, 75, 95, 99])
    gradient_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    return {
        "width": int(gray.shape[1]), "height": int(gray.shape[0]), "pixels": int(gray.size),
        "mean_gv": float(gray.mean()), "std_gv": float(gray.std()),
        "min_gv": int(gray.min()), "max_gv": int(gray.max()),
        "quantiles": dict(zip(("p01", "p05", "p25", "p50", "p75", "p95", "p99"), percentiles.tolist())),
        "histogram": np.bincount(gray.ravel(), minlength=256).tolist(),
        "below_125_fraction": float((gray < 125).mean()),
        "above_150_fraction": float((gray > 150).mean()),
        "bright_ge200_fraction": float((gray >= 200).mean()),
        "digital_shadow_le1_fraction": float((gray <= 1).mean()),
        "digital_highlight_ge254_fraction": float((gray >= 254).mean()),
        "laplacian_variance_ksize3": float(cv2.Laplacian(gray, cv2.CV_64F, ksize=3).var()),
        "tenengrad_mean_squared_ksize3": float((gradient_x ** 2 + gradient_y ** 2).mean()),
        "contrast_p95_p05": float(percentiles[5] - percentiles[1]),
        "contrast_p99_p01": float(percentiles[6] - percentiles[0]),
    }


def region_statistics(gray, foreground):
    def values(mask):
        sample = gray[mask]
        if not sample.size:
            return None
        return {"pixels": int(sample.size), "area_fraction": float(mask.mean()),
                "mean_gv": float(sample.mean()), "median_gv": float(np.median(sample)),
                "std_gv": float(sample.std())}
    inside, outside = values(foreground), values(~foreground)
    difference = outside["mean_gv"] - inside["mean_gv"] if inside and outside else None
    return {"foreground": inside, "background": outside, "background_minus_foreground_gv": difference,
            "confidence": "NOT_CALIBRATED_NO_SEGMENTATION_GROUND_TRUTH"}


def partitions(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    threshold, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    masks = {"gray207_pixels": gray < 207, "otsu_pixels": binary > 0,
             "hsv_background_v200_s40": ~((hsv[:, :, 2] >= 200) & (hsv[:, :, 1] <= 40))}
    results = {}
    for name, mask in masks.items():
        results[name] = {"status": "EXPLORATORY_PIXEL_PARTITION_NOT_BOTTLE_GROUND_TRUTH",
                         **region_statistics(gray, mask)}
    results["otsu_pixels"]["threshold_gv"] = float(threshold)
    contours, _ = cv2.findContours((gray < 207).astype(np.uint8) * 255,
                                   cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    status = "UNAVAILABLE_NO_CONTOUR"
    if contours:
        contour = max(contours, key=cv2.contourArea)
        left, top, width, height = cv2.boundingRect(contour)
        if left == 0 or top == 0 or left + width >= gray.shape[1] or top + height >= gray.shape[0]:
            status = "UNAVAILABLE_BORDER_TOUCH_NOT_COMPLETED"
        elif cv2.contourArea(contour) < gray.size * 0.1:
            status = "UNAVAILABLE_SMALL_COMPONENT"
        else:
            filled = np.zeros_like(gray)
            cv2.drawContours(filled, [contour], -1, 255, cv2.FILLED)
            masks["closed_gray207_contour"] = filled > 0
            results["closed_gray207_contour"] = {"status": "EXPLORATORY_CLOSED_CONTOUR_NOT_VALIDATED",
                                                 **region_statistics(gray, filled > 0)}
    if "closed_gray207_contour" not in results:
        results["closed_gray207_contour"] = {"status": status, "foreground": None, "background": None,
                                             "confidence": "NOT_AVAILABLE"}
    return results, masks


def paired_loss(reference, candidate):
    if reference.shape != candidate.shape:
        raise ValueError("EXACTLY_ALIGNED_PAIR_REQUIRED")
    first = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY).astype(np.float64)
    second = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY).astype(np.float64)
    if min(first.shape) < 11:
        raise ValueError("SSIM_WINDOW_REQUIRES_11_PIXELS")
    mean_first = cv2.GaussianBlur(first, (11, 11), 1.5)
    mean_second = cv2.GaussianBlur(second, (11, 11), 1.5)
    variance_first = cv2.GaussianBlur(first * first, (11, 11), 1.5) - mean_first * mean_first
    variance_second = cv2.GaussianBlur(second * second, (11, 11), 1.5) - mean_second * mean_second
    covariance = cv2.GaussianBlur(first * second, (11, 11), 1.5) - mean_first * mean_second
    ssim = ((2 * mean_first * mean_second + 6.5025) * (2 * covariance + 58.5225)
            / ((mean_first ** 2 + mean_second ** 2 + 6.5025)
               * (variance_first + variance_second + 58.5225)))
    mse = float(np.mean((first - second) ** 2))
    return {"gray_mae": float(np.abs(first - second).mean()), "gray_mse": mse,
            "psnr_db": 10 * math.log10(255 ** 2 / mse) if mse else None,
            "psnr_status": "FINITE" if mse else "EXACT_PIXELS_INFINITE_PSNR",
            "ssim_gray_window11_sigma1_5": float(ssim[5:-5, 5:-5].mean()),
            "candidate_minus_reference_mean_gv": float(second.mean() - first.mean())}


def source_paths():
    tree = ast.parse((ROOT / "data/outputs/videos/render_conveyor.py").read_text(encoding="utf-8"))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    folders = next(node.value for node in main.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "folders" for target in node.targets))
    result = []
    for folder in folders.elts:
        relative = Path(ast.literal_eval(folder.right))
        if relative.is_absolute() or ".." in relative.parts or "ground_truth" in relative.parts:
            raise ValueError("UNSAFE_SOURCE_MAPPING")
        for index in range(3):
            result.append(ROOT / relative / f"{index:03d}.png")
    return result


def snapshot(sources):
    paths = list((ROOT / "data").glob("*.jsonl"))
    for directory in ("data/outputs/captures", "data/outputs/grab_inspection_inputs",
                      "data/outputs/inspection_anomaly_maps", "data/outputs/reinspection_history",
                      "data/outputs/vision_reviews", "data/outputs/agent_reports", "data/outputs/videos",
                      "data/logs", "models", "backend", "frontend/src", "migrations"):
        paths.extend(path for path in (ROOT / directory).rglob("*") if path.is_file()
                     and "__pycache__" not in path.parts)
    paths.extend(sources)
    aliases = {path: f"MVTec-source-{index + 1:04d}" for index, path in enumerate(sources)}
    result, failures = {}, []
    for path in sorted(set(paths)):
        alias = aliases.get(path, str(path.relative_to(ROOT)))
        try:
            if path.is_symlink():
                raise ValueError("LINK_NOT_FOLLOWED")
            result[alias] = digest(path)
        except (OSError, ValueError) as error:
            failures.append({"asset": alias, "error": type(error).__name__})
    return {"sha256": result, "unverified": failures}


def install_guard(output):
    counters = {"network_attempts": 0, "blocked_io": 0}
    def audit(event, arguments):
        if event == "socket.connect":
            counters["network_attempts"] += 1
            raise RuntimeError("NETWORK_FORBIDDEN")
        if event == "open" and arguments and isinstance(arguments[0], (str, bytes)):
            import os
            path = Path(os.fsdecode(arguments[0])).resolve()
            if path.name.startswith(".env") or "ground_truth" in path.parts or "evaluation_private" in path.parts:
                counters["blocked_io"] += 1
                raise RuntimeError("PRIVATE_DATA_FORBIDDEN")
            mode, flags = arguments[1:3]
            writing = isinstance(mode, str) and any(character in mode for character in "wax+")
            writing |= isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            if writing and output not in path.parents:
                counters["blocked_io"] += 1
                raise RuntimeError("OUTPUT_DIRECTORY_ONLY")
        if event in {"os.remove", "os.rmdir", "os.mkdir", "os.rename", "os.link", "os.symlink", "os.chmod"}:
            count = 2 if event in {"os.rename", "os.link", "os.symlink"} else 1
            for value in arguments[:count]:
                if isinstance(value, str):
                    path = Path(value).resolve()
                    if path != output and output not in path.parents:
                        counters["blocked_io"] += 1
                        raise RuntimeError("MUTATION_OUTSIDE_ANALYSIS_FORBIDDEN")
    sys.addaudithook(audit)
    return counters


def frames_at(path, indices):
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError("VIDEO_DECODE_UNAVAILABLE")
    frames = {}
    metadata = {"width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": capture.get(cv2.CAP_PROP_FPS), "frame_count": int(capture.get(cv2.CAP_PROP_FRAME_COUNT)),
                "fourcc": int(capture.get(cv2.CAP_PROP_FOURCC)).to_bytes(4, "little").decode("ascii", "replace")}
    try:
        for index in range(max(indices) + 1):
            available, frame = capture.read()
            if not available:
                raise ValueError("FRAME_UNAVAILABLE")
            if index in indices:
                frames[index] = frame
    finally:
        capture.release()
    return metadata, frames


def mask_picture(image, masks):
    tiles = []
    for name in ("gray207_pixels", "otsu_pixels", "hsv_background_v200_s40", "closed_gray207_contour"):
        tile = image.copy()
        if name in masks:
            mask = masks[name]
            tint = np.full_like(tile, (0, 200, 0))
            tile[mask] = (tile[mask].astype(float) * 0.65 + tint[mask] * 0.35).astype(np.uint8)
        canvas = np.full((tile.shape[0] + 50, tile.shape[1], 3), 30, np.uint8)
        canvas[50:] = tile
        cv2.putText(canvas, name, (3, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        cv2.putText(canvas, "EXPERIMENT ONLY" if name in masks else "NOT AVAILABLE", (3, 37),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 220, 255), 1)
        tiles.append(canvas)
    return np.hstack(tiles)


def histogram_picture(cases):
    canvas = np.full((280 * len(cases), 570, 3), 245, np.uint8)
    for index, row in enumerate(cases):
        origin = index * 280
        histogram = np.asarray(row["quality_metrics"]["histogram"])
        cv2.putText(canvas, row["inspection_id"] + " / ROI GV histogram", (15, origin + 23),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1)
        for value, count in enumerate(histogram):
            height = int(205 * count / max(1, histogram.max()))
            cv2.line(canvas, (25 + value * 2, origin + 245), (25 + value * 2, origin + 245 - height), (100, 70, 30), 2)
        for value, color in ((125, (0, 0, 220)), (150, (0, 140, 220))):
            cv2.line(canvas, (25 + value * 2, origin + 38), (25 + value * 2, origin + 245), color, 1)
        cv2.putText(canvas, "0               red=125 orange=150                    255", (20, origin + 269),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (20, 20, 20), 1)
    return canvas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    if (ROOT / "data/outputs/quality-analysis").resolve() not in output.parents:
        raise ValueError("ISOLATED_QUALITY_ANALYSIS_OUTPUT_REQUIRED")
    output.mkdir(parents=True, exist_ok=False)
    sys.dont_write_bytecode = True
    counters = install_guard(output)
    sys.path.insert(0, str(ROOT))
    from backend.vision import analyze_brightness, evaluate_image_quality
    sources = source_paths()
    before = snapshot(sources)
    write_json(output / "protection-before.json", before)
    raw_records = [json.loads(line) for line in (ROOT / "data/inspections.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    grab_records = [row for row in raw_records if row.get("metrics", {}).get("input_source") == "LIVEVIEW_GRAB"]
    counts = Counter(row["inspection_id"] for row in raw_records)
    logs = [json.loads(line) for line in (ROOT / "data/inspection_logs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    manifest_path = ROOT / "data/outputs/videos/bottle_conveyor_mixed_ok_ng_16s_h264_1920x480_evidence/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_rows = []
    for index, path in enumerate(sources):
        source_id = f"VIDEO-SRC-{index + 1:04d}"
        try:
            image, checksum = read_png(path)
            expected = next(item["source_sha256"] for item in manifest["source_images"] if item["source_id"] == source_id)
            if checksum != expected:
                raise ValueError("SOURCE_MANIFEST_HASH_MISMATCH")
            source_rows.append({"source_id": source_id, "sha256": checksum, "status": "SOURCE_HASH_VERIFIED",
                                "quality_metrics": metrics(image), "comparison": "RAW_SOURCE_NOT_ALIGNED_WITH_VIDEO_ROI_NO_PSNR"})
        except (OSError, ValueError) as error:
            source_rows.append({"source_id": source_id, "status": "NOT_AVAILABLE", "error": type(error).__name__})
    rows, excluded, video_rows, loss_rows, sensitivity, stress_rows = [], [], [], [], [], []
    case_images = {}
    for video_id, (filename, expected_hash) in VIDEOS.items():
        selected = [row for row in grab_records if row["metrics"].get("input_provenance", {}).get("video_id") == video_id]
        frame_count = 240 if video_id == "VID-000002" else 480
        samples = sorted(set(np.linspace(0, frame_count - 1, 9, dtype=int).tolist()))
        wanted = set(samples + [row["metrics"]["input_provenance"]["frame_index"] for row in selected])
        path = ROOT / "data/outputs/videos" / filename
        if digest(path) != expected_hash:
            raise ValueError("REGISTERED_VIDEO_HASH_MISMATCH")
        metadata, frames = frames_at(path, wanted)
        video_rows.append({"video_id": video_id, "filename": filename, "sha256": expected_hash, **metadata,
                           "samples": [{"frame_index": index, "whole_frame": metrics(frames[index]),
                                        "belt_strip_107_414": metrics(frames[index][107:414])} for index in samples]})
        for record in selected:
            identifier = record["inspection_id"]
            provenance = record["metrics"]["input_provenance"]
            try:
                if counts[identifier] != 1:
                    raise ValueError("DUPLICATE_INSPECTION_ID")
                image_id = record["image_id"]
                import re
                if re.fullmatch(r"IMG-GRAB-[0-9a-f]{32}", image_id) is None:
                    raise ValueError("INVALID_MANAGED_IMAGE_ID")
                png = ROOT / "data/outputs/grab_inspection_inputs" / (image_id + ".png")
                image, checksum = read_png(png)
                stored = json.loads(png.with_suffix(".json").read_text(encoding="utf-8"))
                if checksum != provenance["crop_sha256"] or checksum != stored["crop_sha256"] or stored["image_id"] != image_id:
                    raise ValueError("CROP_MANIFEST_HASH_MISMATCH")
                if provenance["source_revision"] != expected_hash:
                    raise ValueError("VIDEO_PROVENANCE_MISMATCH")
                roi = provenance["roi"]
                frame = frames[provenance["frame_index"]]
                decoded = frame[roi["y"]:roi["y"] + roi["height"], roi["x"]:roi["x"] + roi["width"]]
                if not np.array_equal(decoded, image):
                    raise ValueError("DECODED_FRAME_AND_SAVED_CROP_DIFFER")
                current = analyze_brightness(image)
                if current["mean"] != record["metrics"]["mean"]:
                    raise ValueError("STORED_GV_MISMATCH")
                quality = metrics(image)
                split, masks = partitions(image)
                events = [event for event in logs if event.get("inspection_id") == identifier]
                row = {"inspection_id": identifier, "video_id": video_id, "frame_index": provenance["frame_index"],
                       "image_id": image_id, "capture_id": provenance["capture_id"], "crop_sha256": checksum,
                       "roi": roi, "quality_metrics": quality, "partitions": split,
                       "stored_mean_gv": current["mean"], "stored_quality_status": record.get("image_quality_status"),
                       "stored_final_result": record.get("final_result"), "stored_final_reason_code": record.get("final_reason_code"),
                       "stored_model_verdict": record.get("result"), "stored_patchcore_score": record["metrics"].get("anomaly_score"),
                       "event_codes": [event.get("event_code") for event in events],
                       "verification": "PNG_HASH_MANIFEST_FRAME_AND_RECORDED_GV_MATCH",
                       "quality_replay_125_150": evaluate_image_quality(current, 125, 150)["quality_status"],
                       "limitations": ["No defect ground truth or physical exposure label", "Masks are exploratory, not anatomical truth"]}
                rows.append(row)
                if identifier in CASES:
                    case_images[identifier] = image
                    write_png(output / (identifier + "-partitions.png"), mask_picture(image, masks))
                    for margin in (-10, 0, 10):
                        left, top = roi["x"] - margin, roi["y"] - margin
                        width, height = roi["width"] + 2 * margin, roi["height"] + 2 * margin
                        if left < 0 or top < 107 or left + width > frame.shape[1] or top + height > 414:
                            sensitivity.append({"inspection_id": identifier, "margin": margin, "status": "EXCLUDED_NON_BELT_OR_OUT_OF_FRAME"})
                            continue
                        region = frame[top:top + height, left:left + width]
                        entry = {"inspection_id": identifier, "margin": margin, "status": "OFFLINE_SAME_FRAME_NOT_NEW_GRAB",
                                 "roi": {"x": left, "y": top, "width": width, "height": height}, "quality_metrics": metrics(region)}
                        if margin > 0:
                            added = np.ones(region.shape[:2], bool)
                            added[margin:-margin, margin:-margin] = False
                            gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
                            entry["added_pixels"] = {"count": int(added.sum()), "mean_gv": float(gray[added].mean()),
                                                     "ge200_fraction": float((gray[added] >= 200).mean())}
                        sensitivity.append(entry)
                    for name, transformed in (("gaussian_sigma1", cv2.GaussianBlur(image, (0, 0), 1)),
                                              ("gaussian_sigma2", cv2.GaussianBlur(image, (0, 0), 2)),
                                              ("digital_half_gain", (image.astype(float) * 0.5).astype(np.uint8)),
                                              ("digital_clipping_gain1_8", np.clip(image.astype(float) * 1.8, 0, 255).astype(np.uint8))):
                        stress_rows.append({"inspection_id": identifier, "operation": name,
                                            "source": "SYNTHETIC_STRESS_NOT_REAL_EXPOSURE_OR_DEFECT_LABEL", "quality_metrics": metrics(transformed)})
                        write_png(output / (identifier + "-stress-" + name + ".png"), transformed)
            except (OSError, ValueError, KeyError) as error:
                excluded.append({"inspection_id": identifier, "reason": str(error) if isinstance(error, ValueError) else type(error).__name__})
        if video_id == "VID-000002":
            intermediate = ROOT / "data/outputs/experiments/conveyor-lines-ab-20261019-no-stripes-01/bright_no_lines.clean.mp4"
            final_control = intermediate.parent / "bright_no_lines_control.mp4"
            if intermediate.exists() and final_control.exists() and digest(final_control) == expected_hash:
                original_metadata, originals = frames_at(intermediate, set(samples))
                if any(original_metadata[key] != metadata[key] for key in ("width", "height", "fps", "frame_count")):
                    raise ValueError("ENCODING_PAIR_METADATA_MISMATCH")
                for index in samples:
                    loss_rows.append({"video_id": video_id, "frame_index": index,
                                      "pair": "EXISTING_MP4V_CLEAN_TO_H264_CONTROL_SAME_FRAME_INDEX",
                                      "reference_sha256": digest(intermediate), "candidate_sha256": expected_hash,
                                      "region": "BELT_STRIP_ROWS_107_414", **paired_loss(originals[index][107:414], frames[index][107:414])})
            else:
                loss_rows.append({"video_id": video_id, "status": "NOT_AVAILABLE_ALIGNED_INTERMEDIATE"})
        else:
            loss_rows.append({"video_id": video_id, "status": "NOT_VERIFIED_RAW_PREENCODE_FRAMES_NOT_PERSISTED_NO_PSNR_SSIM"})
    for record in grab_records:
        if record["metrics"].get("input_provenance", {}).get("video_id") not in VIDEOS:
            excluded.append({"inspection_id": record["inspection_id"], "reason": "OUTSIDE_VID2_VID3_ANALYSIS_SCOPE"})
    comparison = {}
    for video_id in VIDEOS:
        selected = [row for row in rows if row["video_id"] == video_id]
        means = [row["quality_metrics"]["mean_gv"] for row in selected]
        comparison[video_id] = {"count": len(selected), "final_counts": dict(Counter(row["stored_final_result"] for row in selected)),
                                "mean_gv_range": [min(means), max(means)] if means else None,
                                "contour_statuses": dict(Counter(row["partitions"]["closed_gray207_contour"]["status"] for row in selected)),
                                "quality_replay_mismatches": [row["inspection_id"] for row in selected if row["quality_replay_125_150"] != row["stored_quality_status"]],
                                "selection_bias": "Operator-selected ROIs, repeated products and nonrandom frames; not detection accuracy"}
    write_json(output / "results.json", {"created_at": datetime.now(timezone.utc).isoformat(),
                                         "opencv_version": cv2.__version__, "numpy_version": np.__version__,
                                         "analysis_kind": "OFFLINE_BASELINE_NO_RUNTIME_POLICY_CHANGE", "source_images": source_rows,
                                         "video_samples": video_rows, "inspections": rows, "excluded": excluded,
                                         "paired_encoding_loss": loss_rows, "roi_sensitivity": sensitivity, "synthetic_stress": stress_rows,
                                         "summary": comparison})
    fields = ["inspection_id", "video_id", "frame_index", "image_id", "capture_id", "crop_sha256", "roi",
              "stored_mean_gv", "stored_quality_status", "stored_model_verdict", "stored_patchcore_score", "stored_final_result",
              "std_gv", "below_125_fraction", "bright_ge200_fraction", "digital_shadow_le1_fraction",
              "digital_highlight_ge254_fraction", "laplacian_variance_ksize3", "tenengrad_mean_squared_ksize3", "contrast_p95_p05", "partitions"]
    with (output / "inspection-metrics.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            flat = {key: row.get(key, row["quality_metrics"].get(key)) for key in fields}
            for key in ("roi", "partitions"):
                flat[key] = json.dumps(flat[key], ensure_ascii=False, allow_nan=False)
            writer.writerow(flat)
    case_rows = [next(row for row in rows if row["inspection_id"] == identifier) for identifier in CASES if identifier in case_images]
    if case_rows:
        write_png(output / "case-histograms.png", histogram_picture(case_rows))
    after = snapshot(sources)
    changed = [key for key in set(before["sha256"]) | set(after["sha256"]) if before["sha256"].get(key) != after["sha256"].get(key)]
    protection = {"verified_files": len(before["sha256"]), "unchanged": not changed and not before["unverified"] and not after["unverified"],
                  "changed_or_disappeared": sorted(changed), "unverified_before": before["unverified"], "unverified_after": after["unverified"],
                  "postgresql": "NOT_VERIFIED_DATABASE_NOT_ACCESSED", "database_connections": 0,
                  "gemini_calls": 0, "new_grabs": 0, "patchcore_loads_or_predictions": 0, **counters}
    write_json(output / "protection.json", protection)
    print(json.dumps({"output": str(output.relative_to(ROOT)), "source_images_verified": sum(row["status"] == "SOURCE_HASH_VERIFIED" for row in source_rows),
                      "analyzed_crops": len(rows), "excluded_grab_records": len(excluded), "summary": comparison,
                      "protection": {key: value for key, value in protection.items() if key not in {"unverified_before", "unverified_after"}},
                      "unverified_before_count": len(before["unverified"]), "unverified_after_count": len(after["unverified"])}, ensure_ascii=True))
    return 0 if protection["unchanged"] and not any(counters.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
