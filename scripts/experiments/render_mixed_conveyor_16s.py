"""Offline demonstration rendering; source annotations are not model predictions."""

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
WIDTH, HEIGHT, FPS, FRAME_COUNT = 1920, 480, 30, 480
SPEED, SPACING, CENTER_Y = 168, 380, 260
VIDEO_NAME = "bottle_conveyor_mixed_ok_ng_16s_h264_1920x480.mp4"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def save_png(path, image):
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise RuntimeError("PNG_ENCODING_FAILED")
    with path.open("xb") as stream:
        stream.write(encoded.tobytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--ffprobe", type=Path, required=True)
    arguments = parser.parse_args()
    directory = ROOT / "data/outputs/videos"
    destination = directory / VIDEO_NAME
    evidence = directory / f"{destination.stem}_evidence"
    if destination.exists() or evidence.exists():
        raise RuntimeError("OUTPUT_COLLISION_NO_OVERWRITE")
    for executable in (arguments.ffmpeg, arguments.ffprobe):
        if not executable.is_absolute() or not executable.is_file():
            raise RuntimeError("LOCAL_ENCODER_REQUIRED")

    generator = directory / "render_conveyor.py"
    specification = importlib.util.spec_from_file_location("demo_renderer", generator)
    renderer = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(renderer)
    folders = (
        ROOT / "dataset/bottle/train/good",
        ROOT / "dataset/bottle/test/broken_large",
        ROOT / "dataset/bottle/test/broken_small",
        ROOT / "dataset/bottle/test/contamination",
    )
    annotations = ("REFERENCE_GOOD", "REFERENCE_BROKEN_LARGE", "REFERENCE_BROKEN_SMALL", "REFERENCE_CONTAMINATION")
    sources = [folder / f"{index:03d}.png" for folder in folders for index in range(3)]
    if not all(path.is_file() for path in sources):
        raise RuntimeError("SOURCE_IMAGES_UNAVAILABLE")
    protected = [*sources, *directory.glob("*.mp4"), generator,
                 directory / "render_metadata.json", directory / "render_metadata_single_lane.json",
                 ROOT / "backend/video_source.py", ROOT / "data/inspections.jsonl", ROOT / "data/inspection_logs.jsonl"]
    before = {str(path.relative_to(ROOT)): digest(path) for path in protected if path.is_file()}
    evidence.mkdir(exist_ok=False)
    save_json(evidence / "protected_before.json", before)
    sprites, references = {}, []
    random = np.random.default_rng(17)
    for group_index, folder in enumerate(folders):
        for source_index in range(3):
            path = folder / f"{source_index:03d}.png"
            source_id = f"VIDEO-SRC-{group_index * 3 + source_index + 1:04d}"
            angle = float(random.uniform(-28, 28))
            sprites[group_index, source_index] = (renderer.make_sprite(path, 260, angle), source_id)
            references.append({"source_id": source_id, "source_sha256": digest(path),
                               "reference_annotation": annotations[group_index], "rotation_degrees": angle})

    background = renderer.make_background()
    background[:78] = (17, 22, 29)
    background[443:] = (17, 22, 29)
    background[107:414] = (255, 255, 255)
    renderer.text(background, "VISIONINSIGHT", (50, 42), 1.0, (236, 242, 246), 2)
    renderer.text(background, "TOP-DOWN CONVEYOR / 16 SECOND DEMO", (1170, 39), 0.65)
    renderer.text(background, "SOURCE-IMAGE COMPOSITE / NOT REAL FACTORY FOOTAGE", (50, 468), 0.48)
    renderer.text(background, "PAUSE / SELECT ROI / GRAB", (1430, 468), 0.48)
    ordering = [(0, 0), (1, 0), (0, 1), (3, 0), (0, 2), (2, 0), (0, 0),
                (1, 1), (0, 1), (3, 1), (0, 2), (2, 1), (1, 2), (0, 0)]
    bottles, placements = [], []
    for position_index, source_key in zip(range(-8, 6), ordering):
        sprite, source_id = sprites[source_key]
        start_x = 160 + position_index * SPACING
        half_size = sprite[1].shape[0] / 2
        first_full = max(0, math.ceil((half_size - start_x) / SPEED * FPS))
        last_full = min(FRAME_COUNT - 1, math.floor((WIDTH - half_size - start_x) / SPEED * FPS))
        bottles.append((start_x, sprite, source_id))
        placements.append({"instance_id": f"BOTTLE-{position_index + 9:02d}", "source_id": source_id,
                           "reference_annotation": annotations[source_key[0]], "start_center_x": start_x,
                           "center_y": CENTER_Y, "full_visibility_frames":
                           [first_full, last_full] if first_full <= last_full else None})
    samples = {}
    for position_index in (2, 1, 0, -1, -2, -3, -4, -5):
        placement = placements[position_index + 8]
        frame_index = min(FRAME_COUNT - 1, max(0, round((960 - placement["start_center_x"]) / SPEED * FPS)))
        samples[frame_index] = placement

    command = [str(arguments.ffmpeg), "-hide_banner", "-nostdin", "-n", "-f", "rawvideo", "-pixel_format", "bgr24",
               "-video_size", f"{WIDTH}x{HEIGHT}", "-framerate", str(FPS), "-i", "pipe:0", "-frames:v", str(FRAME_COUNT),
               "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-threads", "2",
               "-movflags", "+faststart", "-an", "-map_metadata", "-1", str(destination)]
    with (evidence / "encode.log").open("xb") as log:
        encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            for frame_index in range(FRAME_COUNT):
                frame = background.copy()
                for start_x, sprite, source_id in bottles:
                    renderer.composite(frame, sprite, start_x + frame_index / FPS * SPEED, CENTER_Y)
                encoder.stdin.write(frame.tobytes())
        finally:
            encoder.stdin.close()
            return_code = encoder.wait(timeout=120)
        if return_code != 0:
            raise RuntimeError("ENCODING_FAILED")

    result = subprocess.run([str(arguments.ffprobe), "-v", "error", "-count_frames", "-show_streams", "-show_format",
                             "-of", "json", str(destination)], capture_output=True, text=True, check=True, timeout=90,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    probe = json.loads(result.stdout)
    save_json(evidence / "ffprobe.json", probe)
    stream = probe["streams"][0]
    expected = {"codec_name": "h264", "codec_tag_string": "avc1", "pix_fmt": "yuv420p", "width": WIDTH,
                "height": HEIGHT, "avg_frame_rate": "30/1", "r_frame_rate": "30/1", "nb_frames": "480", "nb_read_frames": "480"}
    if len(probe["streams"]) != 1 or any(stream.get(name) != value for name, value in expected.items()):
        raise RuntimeError("VIDEO_METADATA_MISMATCH")
    if float(stream["duration"]) != 16 or float(probe["format"]["duration"]) != 16:
        raise RuntimeError("DURATION_MISMATCH")

    capture = cv2.VideoCapture(str(destination))
    previews, crop_previews, observations = [], [], []
    decoded = 0
    try:
        while True:
            available, frame = capture.read()
            if not available:
                break
            if frame.shape != (HEIGHT, WIDTH, 3):
                raise RuntimeError("FRAME_DIMENSION_MISMATCH")
            if decoded in samples:
                placement = samples[decoded]
                center_x = placement["start_center_x"] + decoded / FPS * SPEED
                left, top, size = round(center_x) - 150, CENTER_Y - 150, 300
                crop = frame[top:top + size, left:left + size]
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                prefix = f"frame_{decoded:03d}_{placement['source_id']}"
                save_png(evidence / f"{prefix}.png", frame)
                save_png(evidence / f"{prefix}_crop.png", crop)
                tile = np.full((350, 340, 3), (17, 22, 29), dtype=np.uint8)
                tile[0:300, 20:320] = crop
                renderer.text(tile, f"F{decoded:03d} / {placement['source_id']}", (12, 320), 0.43)
                renderer.text(tile, placement["reference_annotation"], (12, 342), 0.40)
                crop_previews.append(tile)
                previews.append(cv2.resize(frame, (960, 240), interpolation=cv2.INTER_AREA))
                observations.append({"frame_index": decoded, "seconds": round(decoded / FPS, 3),
                                     "source_id": placement["source_id"], "reference_annotation": placement["reference_annotation"],
                                     "roi": {"x": left, "y": top, "width": size, "height": size},
                                     "mean_gv": round(float(gray.mean()), 2), "full_frame_file": prefix + ".png",
                                     "crop_file": prefix + "_crop.png", "model_prediction": "NOT_RUN"})
            decoded += 1
    finally:
        capture.release()
    if decoded != FRAME_COUNT or len(previews) != 8:
        raise RuntimeError("DECODE_COUNT_MISMATCH")
    save_png(evidence / "representative_frames.png", np.vstack([np.hstack(previews[index:index + 2]) for index in range(0, 8, 2)]))
    save_png(evidence / "representative_crops.png", np.vstack([np.hstack(crop_previews[:4]), np.hstack(crop_previews[4:])]))
    after = {name: digest(ROOT / name) for name in before}
    save_json(evidence / "protection.json", {"protected_count": len(before), "unchanged": before == after,
                                            "changed": [name for name in before if before[name] != after[name]]})
    if before != after:
        raise RuntimeError("PROTECTED_FILE_CHANGED")
    metadata = {"video": str(destination.relative_to(ROOT)), "sha256": digest(destination),
                "file_bytes": destination.stat().st_size, "duration_seconds": 16, "width": WIDTH, "height": HEIGHT,
                "fps": FPS, "frame_count": decoded, "codec": "h264/avc1", "pixel_format": "yuv420p",
                "sprite_diameter_pixels": 260, "spacing_pixels": SPACING, "speed_pixels_per_second": SPEED,
                "belt_background_bgr": [255, 255, 255], "belt_seams_or_stripes": False,
                "reference_annotations_are_predictions": False, "patchcore_inference_calls": 0, "gemini_calls": 0,
                "limitations": "Existing outer-contour alpha, resize, rotation and shadow compositing reused. Bottle interior remains opaque; not a physical glass transmission simulation. Source reference class does not guarantee an OK/NG server result or detection accuracy.",
                "source_images": references, "bottle_placements": placements, "representative_crops": observations}
    save_json(evidence / "manifest.json", metadata)
    print(json.dumps({name: value for name, value in metadata.items() if name not in ("source_images", "bottle_placements")}, indent=2))


if __name__ == "__main__":
    main()
