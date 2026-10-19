"""Offline background-only render control; no inspection API, model or provider imports."""

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def statistics(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    counts = np.bincount(gray.ravel(), minlength=256)
    return {"mean_gv": round(float(gray.mean()), 2), "std_gv": round(float(gray.std()), 2),
            "median_gv": float(np.median(gray)), "below_125_percent": round(float((gray < 125).mean()) * 100, 2),
            "histogram": counts.tolist()}


def histogram_distance(reference, candidate):
    reference = np.asarray(reference["histogram"], dtype=float)
    candidate = np.asarray(candidate["histogram"], dtype=float)
    return round(float(np.abs(np.cumsum(reference / reference.sum()) - np.cumsum(candidate / candidate.sum())).sum()), 4)


def decode_frames(path, indices):
    capture = cv2.VideoCapture(str(path))
    selected = {}
    try:
        if not capture.isOpened():
            raise RuntimeError("VIDEO_DECODE_UNAVAILABLE")
        for index in range(max(indices) + 1):
            available, frame = capture.read()
            if not available:
                raise RuntimeError("VIDEO_FRAME_MISSING")
            if index in indices:
                selected[index] = frame
    finally:
        capture.release()
    return selected


def sprite_slice(renderer, sprite, center_x, center_y):
    size = sprite[1].shape[0]
    origin_x, origin_y = int(center_x - size / 2), int(center_y - size / 2)
    left, right = max(0, origin_x), min(renderer.WIDTH, origin_x + size)
    top, bottom = max(107, origin_y), min(414, origin_y + size)
    if left >= right or top >= bottom:
        return None
    return (slice(top, bottom), slice(left, right),
            slice(top - origin_y, bottom - origin_y), slice(left - origin_x, right - origin_x))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--inspection-ids", nargs="+", required=True)
    parser.add_argument("--remove-belt-lines", action="store_true")
    parser.add_argument("--bright-reference", type=Path)
    arguments = parser.parse_args()
    if arguments.remove_belt_lines and arguments.bright_reference is None:
        raise RuntimeError("EXISTING_BRIGHT_REFERENCE_REQUIRED")
    output = arguments.output.resolve()
    if (ROOT / "data/outputs/experiments").resolve() not in output.parents:
        raise RuntimeError("ISOLATED_OUTPUT_REQUIRED")
    output.mkdir(parents=True, exist_ok=True)
    if (output / "comparison.json").exists():
        raise RuntimeError("OUTPUT_COLLISION")
    generator = ROOT / "data/outputs/videos/render_conveyor.py"
    specification = importlib.util.spec_from_file_location("offline_conveyor_renderer", generator)
    renderer = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(renderer)
    main_node = next(node for node in ast.parse(generator.read_text(encoding="utf-8")).body
                     if isinstance(node, ast.FunctionDef) and node.name == "main")
    folder_node = next(node.value for node in main_node.body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "folders" for target in node.targets))
    folders = [ROOT / ast.literal_eval(element.right) for element in folder_node.elts]
    sources, sprites, background_samples, source_hashes, source_stats = [], {}, [], {}, {}
    for folder_index, folder in enumerate(folders):
        sprites[folder_index] = []
        for image_index in range(3):
            path = folder / f"{image_index:03d}.png"
            if not path.is_file():
                raise RuntimeError("RENDER_SOURCE_UNAVAILABLE")
            raw = path.read_bytes()
            image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            contours, _ = cv2.findContours((gray < 207).astype(np.uint8) * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            mask = np.zeros_like(gray)
            cv2.drawContours(mask, [max(contours, key=cv2.contourArea)], -1, 255, cv2.FILLED)
            background_samples.append(float(np.median(gray[mask == 0])))
            source_id = f"VIDEO-SRC-{len(sources) + 1:04d}"
            source_hashes[path] = hashlib.sha256(raw).hexdigest()
            source_stats[source_id] = {**statistics(image), "sha256": source_hashes[path], "shape": list(image.shape)}
            sprites[folder_index].append((renderer.make_sprite(path, 260, float(renderer.RANDOM.uniform(-28, 28))), source_id))
            sources.append(path)
    bright_level = int(round(float(np.median(background_samples))))
    background = renderer.make_background()
    background[443:] = (17, 22, 29)
    noise = renderer.RANDOM.normal(0, 1.35, (307, renderer.WIDTH, 1))
    vertical = np.linspace(-1, 1, 307)[:, None, None]
    belts = []
    plain_bright_belt = None
    for base in ((53, 57, 59), (bright_level,) * 3):
        belt = np.clip(np.array(base)[None, None, :] + noise - 11 * vertical ** 2, 0, 255).astype(np.uint8)
        plain_bright_belt = belt.copy()
        for stripe in range(0, renderer.WIDTH, 7):
            belt[:, stripe:stripe + 1] = np.maximum(belt[:, stripe:stripe + 1].astype(np.int16) - 4, 0)
        belts.append(belt)
    names = ("gray", "bright")
    if arguments.remove_belt_lines:
        belts.append(plain_bright_belt)
        names += ("bright_no_lines",)
    ordering = (0, 1, 3, 0, 2, 1, 0, 3, 2, 0, 1, 2, 3, 0)
    bottles = [(index * 350, 260, *sprites[ordering[index + 7]][index % 3]) for index in range(-7, 7)]
    records = [json.loads(line) for line in (ROOT / "data/inspections.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = []
    for identifier in arguments.inspection_ids:
        found = [record for record in records if record["inspection_id"] == identifier]
        if len(found) != 1:
            raise RuntimeError("INSPECTION_RECORD_NOT_UNIQUE")
        selected.append(found[0])
    frame_indices = {record["metrics"]["input_provenance"]["frame_index"] for record in selected}
    original_video = ROOT / "data/outputs/videos/bottle_conveyor_clean_h264_1920x480_8s.mp4"
    video_hash = sha256(original_video)
    originals = decode_frames(original_video, frame_indices)
    reference_hash = sha256(arguments.bright_reference) if arguments.bright_reference else None
    reference_frames = decode_frames(arguments.bright_reference, frame_indices) if arguments.bright_reference else None
    snapshots = {}
    writers = []
    try:
        for name in names:
            target = output / (name + ".render.mp4")
            if target.exists():
                raise RuntimeError("OUTPUT_COLLISION")
            with target.open("xb"):
                pass
            writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"mp4v"), 30, (1920, 480))
            if not writer.isOpened():
                raise RuntimeError("MP4V_ENCODER_UNAVAILABLE")
            writers.append(writer)
        for frame_index in range(240):
            travel = frame_index / 30 * 252
            frames = []
            for belt_index, belt in enumerate(belts):
                frame = background.copy()
                frame[107:414] = np.roll(belt, int(travel) % 1920, axis=1)
                for seam in range(-1, 8) if belt_index < 2 else ():
                    seam_x = int(seam * 420 + travel % 420)
                    cv2.line(frame, (seam_x, 109), (seam_x, 411), (32, 37, 39), 3)
                    cv2.line(frame, (seam_x + 3, 109), (seam_x + 3, 411), (65, 70, 71), 1)
                for start_x, center_y, sprite, source_id in bottles:
                    renderer.composite(frame, sprite, start_x + travel, center_y)
                frames.append(frame)
            if frame_index in frame_indices:
                opacity = np.zeros((480, 1920), np.float32)
                assignments = []
                for start_x, center_y, sprite, source_id in bottles:
                    placement = sprite_slice(renderer, sprite, start_x + travel, center_y)
                    if placement is not None:
                        rows, columns, sprite_rows, sprite_columns = placement
                        local = sprite[1][sprite_rows, sprite_columns, 0]
                        opacity[rows, columns] = np.maximum(opacity[rows, columns], local)
                        assignments.append((source_id, placement, local))
                core = opacity >= 1
                if any(not np.array_equal(frames[0][core], candidate[core]) for candidate in frames[1:]):
                    raise RuntimeError("OPAQUE_BOTTLE_PIXELS_CHANGED")
                if arguments.remove_belt_lines and (
                    not np.array_equal(frames[1][:107], frames[2][:107])
                    or not np.array_equal(frames[1][414:], frames[2][414:])
                ):
                    raise RuntimeError("NON_BELT_REGION_CHANGED")
                snapshots[frame_index] = (frames, opacity, assignments)
            for writer, frame in zip(writers, frames):
                writer.write(frame)
    finally:
        for writer in writers:
            writer.release()
    for name in names:
        clean = output / (name + ".clean.mp4")
        if clean.exists():
            raise RuntimeError("OUTPUT_COLLISION")
        with clean.open("xb"):
            pass
        capture = cv2.VideoCapture(str(output / (name + ".render.mp4")))
        writer = cv2.VideoWriter(str(clean), cv2.VideoWriter_fourcc(*"mp4v"), 30, (1920, 480))
        written = 0
        try:
            if not writer.isOpened():
                raise RuntimeError("MP4V_ENCODER_UNAVAILABLE")
            while True:
                available, frame = capture.read()
                if not available:
                    break
                frame[443:] = (17, 22, 29)
                writer.write(frame)
                written += 1
        finally:
            capture.release()
            writer.release()
        if written != 240:
            raise RuntimeError("CONTROL_FRAME_COUNT_MISMATCH")
        command = [str(arguments.ffmpeg), "-hide_banner", "-nostdin", "-n", "-i", str(clean), "-map", "0:v:0",
                   "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-fps_mode", "passthrough",
                   "-movflags", "+faststart", "-an", "-map_metadata", "-1", "-map_chapters", "-1", str(output / (name + "_control.mp4"))]
        with (output / (name + ".encode.log")).open("xb") as log:
            encoded = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=log, timeout=120,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if encoded.returncode != 0:
            raise RuntimeError("CONTROL_VIDEO_ENCODING_FAILED")
    decoded = [decode_frames(output / (name + "_control.mp4"), frame_indices) for name in names]
    comparisons = []
    for record in selected:
        provenance = record["metrics"]["input_provenance"]
        index, roi = provenance["frame_index"], provenance["roi"]
        region = (slice(roi["y"], roi["y"] + roi["height"]), slice(roi["x"], roi["x"] + roi["width"]))
        raw = (ROOT / "data/outputs/grab_inspection_inputs" / (record["image_id"] + ".png")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != provenance["crop_sha256"]:
            raise RuntimeError("SAVED_CROP_HASH_MISMATCH")
        saved = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        actual = originals[index][region]
        if not np.array_equal(saved, actual):
            raise RuntimeError("SAVED_CROP_FRAME_MISMATCH")
        frames, opacity, assignments = snapshots[index]
        gray_crop, bright_crop = frames[0][region], frames[1][region]
        alignment_mae = float(np.abs(actual.astype(float) - decoded[0][index][region].astype(float)).mean())
        if alignment_mae > 3:
            raise RuntimeError("SOURCE_RECONSTRUCTION_ALIGNMENT_FAILED")
        scores = []
        for source_id, placement, local in assignments:
            rows, columns, sprite_rows, sprite_columns = placement
            overlap = local[max(0, roi["y"] - rows.start):max(0, min(rows.stop, roi["y"] + roi["height"]) - rows.start),
                            max(0, roi["x"] - columns.start):max(0, min(columns.stop, roi["x"] + roi["width"]) - columns.start)]
            scores.append((float(overlap.sum()), source_id))
        source_id = max(scores)[1]
        values = {"saved_crop": statistics(actual), "gray_render": statistics(gray_crop), "bright_render": statistics(bright_crop),
                  "gray_encoded": statistics(decoded[0][index][region]), "bright_encoded": statistics(decoded[1][index][region])}
        comparison = {"inspection_id": record["inspection_id"], "frame_index": index, "roi": roi, "source_id": source_id,
            "original_source": source_stats[source_id], "brightness": values, "crop_sha256": provenance["crop_sha256"],
            "background_fraction": round(float((opacity[region] == 0).mean()), 4),
            "soft_edge_fraction": round(float(((opacity[region] > 0) & (opacity[region] < 1)).mean()), 4),
            "opaque_bottle_fraction": round(float((opacity[region] >= 1).mean()), 4),
            "original_video_vs_gray_encoded_mae": round(alignment_mae, 4), "opaque_pixels_changed_preencoding": 0,
            "gray_histogram_distance_to_source_gv": histogram_distance(source_stats[source_id], values["gray_encoded"]),
            "bright_histogram_distance_to_source_gv": histogram_distance(source_stats[source_id], values["bright_encoded"]),
            "bright_meets_125": values["bright_encoded"]["mean_gv"] >= 125}
        comparisons.append(comparison)
        if arguments.remove_belt_lines:
            if not np.array_equal(decoded[1][index], reference_frames[index]):
                raise RuntimeError("BRIGHT_REFERENCE_RECONSTRUCTION_MISMATCH")
            seam_mask = np.zeros((480, 1920), dtype=np.uint8)
            travel = index / 30 * 252
            for seam in range(-1, 8):
                seam_x = int(seam * 420 + travel % 420)
                cv2.line(seam_mask, (seam_x, 109), (seam_x, 411), 255, 3)
                cv2.line(seam_mask, (seam_x + 3, 109), (seam_x + 3, 411), 255, 1)
            changed = np.any(frames[1][region] != frames[2][region], axis=2)
            seam_region = seam_mask[region] != 0
            before_raw = cv2.cvtColor(frames[1][region], cv2.COLOR_BGR2GRAY).astype(float)
            after_raw = cv2.cvtColor(frames[2][region], cv2.COLOR_BGR2GRAY).astype(float)
            delta_raw = after_raw - before_raw
            after_encoded = statistics(decoded[2][index][region])
            comparison["line_removal"] = {
                "before_encoded_mean_gv": values["bright_encoded"]["mean_gv"],
                "after_encoded": after_encoded,
                "encoded_mean_gv_increase": round(after_encoded["mean_gv"] - values["bright_encoded"]["mean_gv"], 2),
                "after_meets_lower_125": after_encoded["mean_gv"] >= 125,
                "seam_geometry_intersects_roi": bool(seam_region.any()),
                "visible_changed_pixels": int(changed.sum()),
                "visible_changed_percent": round(float(changed.mean()) * 100, 4),
                "visible_seam_changed_percent": round(float((changed & seam_region).mean()) * 100, 4),
                "visible_fine_only_changed_percent": round(float((changed & ~seam_region).mean()) * 100, 4),
                "seam_region_mean_gv_contribution": round(float(np.where(seam_region, delta_raw, 0).mean()), 4),
                "fine_only_mean_gv_contribution": round(float(np.where(~seam_region, delta_raw, 0).mean()), 4),
                "raw_mean_gv_increase": round(float(delta_raw.mean()), 4),
                "opaque_pixels_changed_preencoding": int(np.any(frames[1][region] != frames[2][region], axis=2)[opacity[region] >= 1].sum()),
                "opaque_pixel_mae_after_lossy_encoding": round(float(np.abs(
                    decoded[1][index][region].astype(float) - decoded[2][index][region].astype(float)
                )[opacity[region] >= 1].mean()), 4),
                "existing_bright_reference_reconstructed_exactly": True,
            }
            if not cv2.imwrite(str(output / (record["inspection_id"] + "_bright_no_lines.png")), decoded[2][index][region]):
                raise RuntimeError("CROP_OUTPUT_FAILED")
        cv2.imwrite(str(output / (record["inspection_id"] + "_gray.png")), decoded[0][index][region])
        cv2.imwrite(str(output / (record["inspection_id"] + "_bright.png")), decoded[1][index][region])
    if sha256(original_video) != video_hash or any(sha256(path) != digest for path, digest in source_hashes.items()):
        raise RuntimeError("ORIGINAL_INPUT_CHANGED")
    if arguments.bright_reference and sha256(arguments.bright_reference) != reference_hash:
        raise RuntimeError("EXISTING_BRIGHT_REFERENCE_CHANGED")
    result = {"experiment": "BACKGROUND_ONLY_DIAGNOSTIC_NOT_MODEL_EVALUATION", "bright_belt_base_gv": bright_level,
              "encoding": "Matched MP4V render -> MP4V clean -> H.264 medium CRF18 yuv420p; neutral footer from render stage",
              "original_video_sha256": video_hash, "source_selection": "Existing renderer folders with exact 000/001/002 filenames; reconstruction alignment checked",
              "transparency_limitation": "Original filled outer-contour alpha retained; bottle interior is opaque, not a physical glass transmission simulation",
              "comparisons": comparisons, "actual_patchcore_calls": 0, "actual_google_calls": 0}
    if arguments.remove_belt_lines:
        result.update({"experiment": "BELT_LINES_ONLY_DIAGNOSTIC_NOT_MODEL_EVALUATION",
                       "bright_reference_sha256": reference_hash,
                       "removed_elements": ["Every-7-pixel minus-4-GV belt grooves", "420-pixel conveyor seam dark line and highlight"],
                       "line_free_video": "bright_no_lines_control.mp4",
                       "lossy_encoding_limitation": "Opaque bottle pixels are unchanged before encoding; independent lossy encodes can change decoded pixels"})
    with (output / "comparison.json").open("x", encoding="utf-8") as destination:
        json.dump(result, destination, indent=2)
    print(json.dumps({"bright_belt_base_gv": bright_level, "comparisons": [{key: value for key, value in item.items()
        if key not in {"original_source", "brightness"}} | {"original_source_mean_gv": item["original_source"]["mean_gv"],
        "gray_mean_gv": item["brightness"]["gray_encoded"]["mean_gv"], "bright_mean_gv": item["brightness"]["bright_encoded"]["mean_gv"]}
        for item in comparisons]}, indent=2))


if __name__ == "__main__":
    main()
