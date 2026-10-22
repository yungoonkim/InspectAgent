"""A-2 offline experiments over the frozen A-1 inputs; no runtime API calls."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import time

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.experiments import analyze_quality_baseline as baseline
from scripts.experiments.quality_candidates import crop_region, highlight_statistics, measure, normalized_sharpness, variants


METRIC_PATHS = {
    "mean_gv": ("mean_gv",), "median_gv": ("median_gv",), "p10": ("p10",), "p25": ("p25",),
    "p75": ("p75",), "p90": ("p90",), "std_gv": ("std_gv",),
    "center_mean": ("center_fraction50", "mean_gv"), "edge_mean": ("edge_fraction50", "mean_gv"),
    "edge_minus_center": ("edge_minus_center_gv",), "fixed96_mean": ("center_fixed96", "mean_gv"),
    "foreground_mean": ("segmentation", "foreground", "mean_gv"),
    "background_mean": ("segmentation", "background", "mean_gv"),
    "laplacian": ("sharpness", "laplacian_variance"), "tenengrad": ("sharpness", "tenengrad"),
    "normalized_laplacian": ("sharpness", "laplacian_over_gray_variance"),
    "normalized_tenengrad": ("sharpness", "tenengrad_over_gray_variance"),
    "fixed96_normalized_laplacian": ("center_fixed_sharpness", "laplacian_over_gray_variance"),
    "ge245_fraction": ("highlights", "ge245_fraction"), "ge250_fraction": ("highlights", "ge250_fraction"),
    "ge254_fraction": ("highlights", "ge254_fraction"),
    "foreground_ge245_fraction": ("highlights", "foreground_ge245_fraction"),
    "background_ge245_fraction": ("highlights", "background_ge245_fraction"),
    "local_std_median": ("highlights", "local_std_median_5x5"),
}


def flattened(value):
    result = {}
    for name, path in METRIC_PATHS.items():
        current = value
        for part in path:
            current = current.get(part) if isinstance(current, dict) else None
        result[name] = current
    return result


def benchmark_components(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, masks = baseline.partitions(image)
    foreground = masks.get("closed_gray207_contour")
    operations = {
        "brightness_global_statistics": lambda: (gray.mean(), np.median(gray), gray.std(), np.percentile(gray, [10, 25, 75, 90]),
                                                  (gray < 125).mean(), (gray >= 200).mean()),
        "a1_segmentation_proposal": lambda: baseline.partitions(image),
        "raw_and_normalized_sharpness": lambda: normalized_sharpness(gray),
        "spatial_highlight_statistics": lambda: highlight_statistics(gray, foreground),
    }
    measured = {}
    for name, operation in operations.items():
        operation()
        timings = []
        for _repeat in range(3):
            started = time.perf_counter()
            operation()
            timings.append((time.perf_counter() - started) * 1000)
        measured[name] = float(np.median(timings))
    return measured


def save_csv(path, rows):
    if not rows:
        return
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False, allow_nan=False) if isinstance(value, (list, dict)) else value
                             for key, value in row.items()})


def brightness_table(rows):
    fields = ("mean_gv", "median_gv", "std_gv", "p10", "p25", "p75", "p90", "below125_fraction",
              "bright_ge200_fraction", "contrast_p90_p10", "center_fraction50", "edge_fraction50", "center_fixed96")
    return [{"inspection_id": row["inspection_id"], "operation": row["operation"], "source": row["source"],
             **{name: row["metrics"][name] for name in fields}, "segmentation": row["metrics"]["segmentation"]} for row in rows]


def source_tokens(row, manifest):
    roi = row["roi"]
    index = row["frame_index"]
    if row["video_id"] == "VID-000003":
        placements = [(entry["source_id"], entry["start_center_x"] + index / 30 * 168, entry["center_y"])
                      for entry in manifest["bottle_placements"]]
    elif row["video_id"] == "VID-000002":
        order = (0, 1, 3, 0, 2, 1, 0, 3, 2, 0, 1, 2, 3, 0)
        placements = [(f"VIDEO-SRC-{order[position + 7] * 3 + position % 3 + 1:04d}", position * 350 + index / 30 * 252, 260)
                      for position in range(-7, 7)]
    else:
        placements = []
    tokens = []
    for source_id, center_x, center_y in placements:
        if (min(roi["x"] + roi["width"], center_x + 148) > max(roi["x"], center_x - 148)
                and min(roi["y"] + roi["height"], center_y + 148) > max(roi["y"], center_y - 148)):
            checksum = next(item["source_sha256"] for item in manifest["source_images"] if item["source_id"] == source_id)
            tokens.append("source:" + checksum)
    if not tokens:
        tokens.append("unresolved-source-conservative-shared-group")
    return tokens


def grouped_split(rows, tokens):
    parents = {}
    def find(token):
        parents.setdefault(token, token)
        if parents[token] != token:
            parents[token] = find(parents[token])
        return parents[token]
    row_tokens = {}
    for row in rows:
        values = [*tokens[row["inspection_id"]], "capture:" + row["capture_id"], "crop:" + row["crop_sha256"]]
        row_tokens[row["inspection_id"]] = values
        for token in values[1:]:
            parents[find(token)] = find(values[0])
    unique = sorted({find(values[0]) for values in row_tokens.values()})
    assignments = {token: {"group_id": "QGROUP-" + hashlib.sha256(token.encode()).hexdigest()[:16],
                           "partition": "HELD_OUT_SOURCE_GROUP" if offset % 3 == 0 and len(unique) > 1 else "DEVELOPMENT_FIXED_PARAMETERS"}
                   for offset, token in enumerate(unique)}
    return {identifier: assignments[find(values[0])] for identifier, values in row_tokens.items()}


def plot_lines(path, title, labels, series):
    canvas = np.full((430, 1060, 3), 245, np.uint8)
    colors = ((40, 120, 210), (40, 150, 40), (190, 70, 120), (180, 100, 20))
    finite = [value for values in series.values() for value in values if value is not None]
    low, high = (min(finite), max(finite)) if finite else (0, 1)
    if high == low:
        high = low + 1
    cv2.putText(canvas, title, (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1)
    cv2.putText(canvas, f"range {low:.3f} .. {high:.3f}; missing values are gaps", (15, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (20, 20, 20), 1)
    for offset, (name, values) in enumerate(series.items()):
        color = colors[offset % len(colors)]
        cv2.putText(canvas, name, (20 + offset * 250, 77), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        previous = None
        for index, value in enumerate(values):
            if value is None:
                previous = None
                continue
            point = (70 + round(index * 890 / max(1, len(labels) - 1)), 345 - round((value - low) / (high - low) * 235))
            if previous is not None:
                cv2.line(canvas, previous, point, color, 2)
            cv2.circle(canvas, point, 4, color, -1)
            previous = point
    for index, label in enumerate(labels):
        cv2.putText(canvas, label[:13], (40 + round(index * 890 / max(1, len(labels) - 1)), 385 + (index % 2) * 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, (20, 20, 20), 1)
    baseline.write_png(path, canvas)


def summarize(rows, names, operation_key):
    result = []
    for partition in ("DEVELOPMENT_FIXED_PARAMETERS", "HELD_OUT_SOURCE_GROUP"):
        for operation in sorted({row[operation_key] for row in rows}):
            selected = [row for row in rows if row["partition"] == partition and row[operation_key] == operation]
            for name in names:
                differences = [row["deltas"].get(name) for row in selected if row["deltas"].get(name) is not None]
                ratios = [row["ratios"].get(name) for row in selected if row["ratios"].get(name) is not None]
                group_medians = []
                for group in sorted({row["group_id"] for row in selected}):
                    values = [row["ratios"].get(name) for row in selected if row["group_id"] == group and row["ratios"].get(name) is not None]
                    if values:
                        group_medians.append(float(np.median(values)))
                result.append({"partition": partition, "operation": operation, "metric": name, "row_count": len(selected),
                               "comparable_count": len(differences), "median_abs_delta": float(np.median(np.abs(differences))) if differences else None,
                               "median_ratio": float(np.median(ratios)) if ratios else None,
                               "group_count": len(group_medians), "median_of_source_group_median_ratios": float(np.median(group_medians)) if group_medians else None})
    return result


def delta_ratio(current, original):
    deltas, ratios = {}, {}
    for name, value in current.items():
        reference = original[name]
        valid = value is not None and reference is not None
        deltas[name] = value - reference if valid else None
        ratios[name] = value / reference if valid and abs(reference) > 1e-12 else None
    return deltas, ratios


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=ROOT / "data/outputs/quality-analysis/a1-baseline-20261020-verified/results.json")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    analysis_root = (ROOT / "data/outputs/quality-analysis").resolve()
    output, baseline_path = arguments.output.resolve(), arguments.baseline.resolve()
    if analysis_root not in output.parents or analysis_root not in baseline_path.parents:
        raise ValueError("MANAGED_ANALYSIS_PATHS_REQUIRED")
    output.mkdir(parents=True, exist_ok=False)
    sys.dont_write_bytecode = True
    counters = baseline.install_guard(output)
    cv2.setNumThreads(1)
    before = baseline.snapshot([])
    before["sha256"]["a1-results.json"] = baseline.digest(baseline_path)
    baseline.write_json(output / "protection-before.json", before)
    if before["unverified"]:
        baseline.write_json(output / "blocked.json", {"reason": "PROTECTION_READ_FAILED", "unverified": before["unverified"]})
        raise RuntimeError("PROTECTION_READ_FAILED_BEFORE_EXPERIMENTS")
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    inputs = data["inspections"]
    if len(inputs) != 60 or len({row["inspection_id"] for row in inputs}) != 60:
        raise ValueError("FROZEN_A1_60_UNIQUE_CROPS_REQUIRED")
    manifest = json.loads((ROOT / "data/outputs/videos/bottle_conveyor_mixed_ok_ng_16s_h264_1920x480_evidence/manifest.json").read_text(encoding="utf-8"))
    tokens = {row["inspection_id"]: source_tokens(row, manifest) for row in inputs}
    groups = grouped_split(inputs, tokens)
    config = {"analysis": "A2_EXPLORATORY_NO_NEW_VERDICTS", "baseline_sha256": baseline.digest(baseline_path),
              "opencv_version": cv2.__version__, "numpy_version": np.__version__, "opencv_threads": 1,
              "parameters": {"fixed_center_side": 96, "center_relative_fraction": 0.5, "margins": [-5, 0, 5, 10, 15],
                             "foreground_gray_threshold": 207, "multiple_component_min_area_fraction": 0.1, "highlight_thresholds": [245, 250, 254],
                             "gaussian_sigmas": [1, 2], "gain": 0.5, "contrast_gain": 0.5,
                             "clipping_gain": 1.8, "jpeg_quality": 80, "noise_sigma": 2, "noise_seed": 20261020},
              "parameter_provenance": "Frozen before measurement: A1 mask207, user exploration levels, analytical gain invariance. No label fitting.",
              "groups": groups, "grouping_method": "Conservative connected components of overlapping render-source hashes, Capture and identical PNG hashes; recipe-derived, not identity ground truth",
              "independent_group_count": len({value["group_id"] for value in groups.values()}),
              "split_warning": "HELD_OUT is within these two synthetic videos, not a labeled independent camera validation",
              "runtime_policy_changes": 0, "crop_resize_for_inspection": False}
    baseline.write_json(output / "experiment-config.json", config)
    records = [json.loads(line) for line in (ROOT / "data/inspections.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    images, rejected, measurements, transformed_rows, timing, component_timing = {}, [], [], [], [], []
    for row in inputs:
        identifier, image_id = row["inspection_id"], row["image_id"]
        if re.fullmatch(r"IMG-GRAB-[0-9a-f]{32}", image_id) is None:
            raise ValueError("INVALID_MANAGED_IMAGE_ID")
        matches = [record for record in records if record["inspection_id"] == identifier]
        if len(matches) != 1:
            raise ValueError("A1_INSPECTION_NO_LONGER_UNIQUE")
        current = matches[0]
        if (current["metrics"]["input_provenance"]["crop_sha256"] != row["crop_sha256"]
                or current["final_result"] != row["stored_final_result"]):
            raise ValueError("A1_RECORD_CHANGED")
        path = ROOT / "data/outputs/grab_inspection_inputs" / (image_id + ".png")
        image, checksum = baseline.read_png(path)
        metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        if checksum != row["crop_sha256"] or metadata["crop_sha256"] != checksum or metadata["image_id"] != image_id:
            raise ValueError("A1_CROP_CHANGED")
        images[identifier] = image
        component_timing.append({"inspection_id": identifier, **benchmark_components(image)})
        generated = variants(image)
        original_flat = None
        for operation, modified in generated.items():
            started = time.perf_counter()
            measured = measure(modified)
            elapsed = (time.perf_counter() - started) * 1000
            timing.append({"inspection_id": identifier, "operation": operation, "elapsed_ms": elapsed})
            flat = flattened(measured)
            if operation == "original":
                original_flat = flat
                measurements.append({**{key: row[key] for key in ("inspection_id", "video_id", "frame_index", "image_id", "capture_id", "roi", "crop_sha256",
                                                                 "stored_mean_gv", "stored_quality_status", "stored_final_result", "stored_model_verdict", "stored_patchcore_score")},
                                     **groups[identifier], "candidate_metrics": measured, "elapsed_ms": elapsed})
            deltas, ratios = delta_ratio(flat, original_flat)
            transformed_rows.append({"inspection_id": identifier, **groups[identifier], "operation": operation,
                                     "source": "STORED_PNG" if operation == "original" else "SYNTHETIC_TRANSFORM_NOT_CAMERA_OR_DEFECT_LABEL",
                                     "width": modified.shape[1], "height": modified.shape[0], "metrics": measured, "deltas": deltas, "ratios": ratios})
            if identifier in baseline.CASES:
                baseline.write_png(output / (identifier + "-" + operation + ".png"), modified)
    roi_rows = []
    for video_id, (filename, expected_hash) in baseline.VIDEOS.items():
        selected = [row for row in inputs if row["video_id"] == video_id]
        path = ROOT / "data/outputs/videos" / filename
        if baseline.digest(path) != expected_hash:
            raise ValueError("VIDEO_CHANGED")
        _, frames = baseline.frames_at(path, {row["frame_index"] for row in selected})
        for row in selected:
            identifier = row["inspection_id"]
            frame, original_roi = frames[row["frame_index"]], row["roi"]
            original_image = images[identifier]
            if not np.array_equal(crop_region(frame, original_roi), original_image):
                raise ValueError("A1_FRAME_ROI_CHANGED")
            reference = flattened(next(item["candidate_metrics"] for item in measurements if item["inspection_id"] == identifier))
            for margin in config["parameters"]["margins"]:
                roi = {"x": original_roi["x"] - margin, "y": original_roi["y"] - margin,
                       "width": original_roi["width"] + 2 * margin, "height": original_roi["height"] + 2 * margin}
                if roi["y"] < 107 or roi["y"] + roi["height"] > 414:
                    rejected.append({"inspection_id": identifier, "margin": margin, "reason": "NON_BELT_PIXELS_WOULD_BE_ADDED"})
                    continue
                try:
                    candidate = crop_region(frame, roi)
                except ValueError:
                    rejected.append({"inspection_id": identifier, "margin": margin, "reason": "ROI_OUT_OF_FRAME"})
                    continue
                measured = measure(candidate)
                deltas, ratios = delta_ratio(flattened(measured), reference)
                added_details = None
                if margin > 0:
                    if not np.array_equal(candidate[margin:-margin, margin:-margin], original_image):
                        raise ValueError("ORIGINAL_PIXELS_NOT_PRESERVED")
                    added = np.ones(candidate.shape[:2], bool)
                    added[margin:-margin, margin:-margin] = False
                    gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
                    added_details = {"pixels": int(added.sum()), "mean_gv": float(gray[added].mean()),
                                     "ge200_fraction": float((gray[added] >= 200).mean())}
                roi_rows.append({"inspection_id": identifier, **groups[identifier], "margin": margin, "roi": roi,
                                 "source": "OFFLINE_SAME_VIDEO_FRAME_NOT_NEW_CAPTURE", "added_pixels": added_details,
                                 "metrics": measured, "deltas": deltas, "ratios": ratios})
    summary = summarize(transformed_rows, METRIC_PATHS, "operation")
    roi_summary = summarize(roi_rows, METRIC_PATHS, "margin")
    for identifier in baseline.CASES:
        selected = [row for row in transformed_rows if row["inspection_id"] == identifier]
        names = [row["operation"] for row in selected]
        plot_lines(output / (identifier + "-sharpness.png"), identifier + " SYNTHETIC relative sharpness (original=1)", names,
                   {name: [row["ratios"][name] for row in selected] for name in ("laplacian", "tenengrad", "normalized_laplacian", "normalized_tenengrad")})
        plot_lines(output / (identifier + "-highlights.png"), identifier + " digital highlights, NOT exposure labels", names,
                   {name: [flattened(row["metrics"])[name] for row in selected] for name in ("ge245_fraction", "ge250_fraction", "ge254_fraction", "foreground_ge245_fraction")})
        selected_roi = [row for row in roi_rows if row["inspection_id"] == identifier]
        plot_lines(output / (identifier + "-roi-stability.png"), identifier + " same-frame ROI sensitivity (GV)", [str(row["margin"]) for row in selected_roi],
                   {name: [flattened(row["metrics"])[name] for row in selected_roi] for name in ("mean_gv", "p25", "fixed96_mean", "foreground_mean")})
    baseline.write_json(output / "measurements.json", {"inspections": measurements, "synthetic_experiments": transformed_rows,
                                                       "roi_experiments": roi_rows, "excluded_roi_variants": rejected,
                                                       "candidate_comparison": summary, "roi_comparison": roi_summary})
    save_csv(output / "inspection-comparison.csv", [{**{key: value for key, value in row.items() if key != "candidate_metrics"},
                                                     **flattened(row["candidate_metrics"]), "segmentation": row["candidate_metrics"]["segmentation"],
                                                     "highlights": row["candidate_metrics"]["highlights"]} for row in measurements])
    for name, rows in (("blur-low-light.csv", transformed_rows), ("roi-stability.csv", roi_rows)):
        save_csv(output / name, [{**{key: value for key, value in row.items() if key not in {"metrics", "deltas", "ratios"}},
                                 **flattened(row["metrics"]), "deltas": row["deltas"], "ratios": row["ratios"],
                                 "segmentation_status": row["metrics"]["segmentation"]["status"]} for row in rows])
    save_csv(output / "saturation-comparison.csv", [{"inspection_id": row["inspection_id"], **groups[row["inspection_id"]], "operation": row["operation"],
                                                   "segmentation_status": row["metrics"]["segmentation"]["status"], **row["metrics"]["highlights"]} for row in transformed_rows])
    save_csv(output / "brightness-distribution.csv", brightness_table(transformed_rows))
    save_csv(output / "candidate-comparison.csv", summary)
    save_csv(output / "roi-candidate-comparison.csv", roi_summary)
    save_csv(output / "timing.csv", timing)
    save_csv(output / "component-timing.csv", component_timing)
    baseline.write_json(output / "component-timing-summary.json", {
        "method": "Standalone components, precomputed gray, warmed once, three repeats median, one OpenCV thread; not additive pipeline timing",
        "timings": {key: {"median_ms": float(np.median([row[key] for row in component_timing])),
                          "p95_ms": float(np.percentile([row[key] for row in component_timing], 95))}
                    for key in component_timing[0] if key != "inspection_id"},
    })
    baseline.write_json(output / "candidate-comparison.json", {"synthetic": summary, "roi": roi_summary})
    after = baseline.snapshot([])
    after["sha256"]["a1-results.json"] = baseline.digest(baseline_path)
    changed = sorted(key for key in set(before["sha256"]) | set(after["sha256"]) if before["sha256"].get(key) != after["sha256"].get(key))
    protection = {"verified_files": len(before["sha256"]), "unchanged": not changed and not after["unverified"],
                  "changed_or_disappeared": changed, "unverified": after["unverified"], **counters,
                  "database_connections": 0, "postgresql": "NOT_VERIFIED_DATABASE_NOT_ACCESSED",
                  "google_calls": 0, "new_captures_or_grabs": 0, "patchcore_loads_or_inference": 0, "runtime_policy_changes": 0}
    baseline.write_json(output / "protection.json", protection)
    print(json.dumps({"output": str(output.relative_to(ROOT)), "images": len(measurements), "synthetic_rows_including_original": len(transformed_rows),
                      "roi_rows": len(roi_rows), "excluded_roi_rows": len(rejected), "source_groups": config["independent_group_count"],
                      "partition_counts": dict(Counter(group["partition"] for group in groups.values())),
                      "segmentation_statuses": dict(Counter(row["candidate_metrics"]["segmentation"]["status"] for row in measurements)),
                      "timing_median_ms": float(np.median([row["elapsed_ms"] for row in timing])), "protection": protection}, ensure_ascii=True))
    return 0 if protection["unchanged"] and not any(counters.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
