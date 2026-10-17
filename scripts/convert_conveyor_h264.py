import argparse
import hashlib
import json
import math
import struct
import subprocess
from pathlib import Path

import cv2
import numpy as np


CLEAN_SHA256 = "cfefcd68116d79670d5d09a016f57f998d5c654499c4bdeaf7b32bdba248ce5e"
ORIGINAL_SHA256 = "daefc8f14912e2a1e1fac77823f7eee97572e47722d3276f93ea3530b1cdda82"


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def run(command, evidence_path):
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf8", errors="replace", timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    with evidence_path.open("x", encoding="utf8") as evidence:
        json.dump({"command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}, evidence, indent=2)
    if result.returncode:
        raise RuntimeError(f"Tool failed; see {evidence_path}")
    return result.stdout


def difference(reference, output):
    values = reference.astype(np.float32) - output.astype(np.float32)
    mean_square = float(np.mean(values ** 2))
    return {
        "mae": float(np.mean(np.abs(values))),
        "psnr_db": 10 * math.log10(255 ** 2 / mean_square) if mean_square else None,
        "maximum_absolute_difference": int(np.max(np.abs(values))),
    }


def top_level_atoms(path):
    atoms = []
    with path.open("rb") as source:
        while source.tell() < path.stat().st_size:
            offset = source.tell()
            size, name = struct.unpack(">I4s", source.read(8))
            if size == 1:
                size = struct.unpack(">Q", source.read(8))[0]
            if size == 0:
                size = path.stat().st_size - offset
            if size < 8 or offset + size > path.stat().st_size:
                raise ValueError("Invalid MP4 atom")
            atoms.append({"name": name.decode("ascii"), "offset": offset, "size": size})
            source.seek(offset + size)
    return atoms


def validate_pixels(clean_path, original_path, output_path):
    captures = [cv2.VideoCapture(str(path)) for path in (clean_path, original_path, output_path)]
    per_frame = []
    references = {}
    clean_fingerprints = []
    output_fingerprints = []
    try:
        if not all(capture.isOpened() for capture in captures):
            raise RuntimeError("OpenCV could not open a validation input")
        output_capture = captures[2]
        output_metadata = {
            "width": output_capture.get(cv2.CAP_PROP_FRAME_WIDTH),
            "height": output_capture.get(cv2.CAP_PROP_FRAME_HEIGHT),
            "fps": output_capture.get(cv2.CAP_PROP_FPS),
            "frame_count": output_capture.get(cv2.CAP_PROP_FRAME_COUNT),
        }
        if list(output_metadata.values()) != [1920, 480, 30, 240]:
            raise AssertionError("Unexpected OpenCV output metadata")
        for frame_index in range(240):
            decoded = [capture.read() for capture in captures]
            if not all(success and frame.shape == (480, 1920, 3) for success, frame in decoded):
                raise AssertionError(f"Frame {frame_index} decode failed")
            clean, original, output = [frame for success, frame in decoded]
            per_frame.append({
                "frame_index": frame_index,
                "incremental_preserved_region": difference(clean[:443], output[:443]),
                "incremental_bottle_band": difference(clean[107:414], output[107:414]),
                "cumulative_preserved_region": difference(original[:443], output[:443]),
                "cumulative_bottle_band": difference(original[107:414], output[107:414]),
                "footer_channel_min": output[448:].min(axis=(0, 1)).tolist(),
                "footer_channel_max": output[448:].max(axis=(0, 1)).tolist(),
                "footer_channel_std": output[448:].std(axis=(0, 1)).tolist(),
                "timestamp_ms": output_capture.get(cv2.CAP_PROP_POS_MSEC),
            })
            clean_fingerprints.append(cv2.resize(clean[:443], (120, 28)).astype(np.float32))
            output_fingerprints.append(cv2.resize(output[:443], (120, 28)).astype(np.float32))
            if frame_index in (0, 60, 120, 180, 239):
                references[frame_index] = output.copy()
        eof = [not capture.read()[0] for capture in captures]
        if not all(eof):
            raise AssertionError("Unexpected frames beyond index 239")
    finally:
        for capture in captures:
            capture.release()
            if capture.isOpened():
                raise AssertionError("Decoder release failed")
    alignment = []
    fingerprints = np.stack(clean_fingerprints)
    for frame_index, fingerprint in enumerate(output_fingerprints):
        distances = np.mean(np.abs(fingerprints - fingerprint), axis=(1, 2, 3))
        alignment.append({"frame_index": frame_index, "nearest_clean_index": int(distances.argmin())})
    if any(entry["frame_index"] != entry["nearest_clean_index"] for entry in alignment):
        raise AssertionError("Unexpected temporal alignment")
    grabs = []
    for frame_index, reference in references.items():
        for repetition in range(1, 4):
            capture = cv2.VideoCapture(str(output_path))
            try:
                accepted = capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                success, output = capture.read()
                position = capture.get(cv2.CAP_PROP_POS_FRAMES)
                identical = bool(success and np.array_equal(reference, output))
                after_last_eof = not capture.read()[0] if frame_index == 239 else None
                grabs.append({
                    "frame_index": frame_index, "repetition": repetition,
                    "seek_accepted": accepted, "next_position": position,
                    "timestamp_ms": capture.get(cv2.CAP_PROP_POS_MSEC) if frame_index != 239 else per_frame[239]["timestamp_ms"],
                    "shape": list(output.shape) if success else None,
                    "identical_to_sequential": identical, "eof_after_last": after_last_eof,
                })
                if not identical or position != frame_index + 1 or after_last_eof is False:
                    raise AssertionError("Random seek does not match sequential decoding")
            finally:
                capture.release()
                if capture.isOpened():
                    raise AssertionError("Grab decoder release failed")
    capture = cv2.VideoCapture(str(output_path))
    try:
        beyond_seek = capture.set(cv2.CAP_PROP_POS_FRAMES, 240)
        beyond_decoded = capture.read()[0]
        if beyond_decoded:
            raise AssertionError("Frame index 240 unexpectedly decoded")
    finally:
        capture.release()
    summary = {}
    for region in ("incremental_preserved_region", "incremental_bottle_band", "cumulative_preserved_region", "cumulative_bottle_band"):
        summary[region] = {
            metric: {"minimum": min(entry[region][metric] for entry in per_frame),
                     "mean": float(np.mean([entry[region][metric] for entry in per_frame])),
                     "maximum": max(entry[region][metric] for entry in per_frame)}
            for metric in ("mae", "psnr_db", "maximum_absolute_difference")
        }
    return {"metadata": output_metadata, "decoded_frames": 240, "all_eof": eof,
            "all_decoders_released": True, "per_frame": per_frame, "summary": summary,
            "alignment": alignment, "grabs": grabs,
            "index_240": {"seek_accepted": beyond_seek, "decoded": beyond_decoded}}


def main():
    parser = argparse.ArgumentParser()
    for argument in ("ffmpeg", "ffprobe", "clean", "original", "output", "evidence-dir"):
        parser.add_argument(f"--{argument}", type=Path, required=True)
    arguments = parser.parse_args()
    if not arguments.ffmpeg.is_absolute() or not arguments.ffprobe.is_absolute():
        raise ValueError("Portable tool paths must be absolute")
    if sha256(arguments.clean) != CLEAN_SHA256 or sha256(arguments.original) != ORIGINAL_SHA256:
        raise ValueError("An approved input revision changed")
    if arguments.output.exists():
        raise FileExistsError(arguments.output)
    if not arguments.evidence_dir.is_dir():
        raise ValueError("Create an isolated evidence directory before running")
    command = [str(arguments.ffmpeg), "-hide_banner", "-nostdin", "-n", "-i", str(arguments.clean),
               "-map", "0:v:0", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
               "-pix_fmt", "yuv420p", "-fps_mode", "passthrough", "-movflags", "+faststart",
               "-an", "-map_metadata", "-1", "-map_chapters", "-1", str(arguments.output)]
    run(command, arguments.evidence_dir / "encode.json")
    probe_text = run([str(arguments.ffprobe), "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(arguments.output)], arguments.evidence_dir / "ffprobe.json")
    probe = json.loads(probe_text)
    streams = probe["streams"]
    if len(streams) != 1:
        raise AssertionError("Unexpected extra streams")
    stream = streams[0]
    expected = {"codec_name": "h264", "pix_fmt": "yuv420p", "width": 1920, "height": 480,
                "avg_frame_rate": "30/1", "nb_read_frames": "240", "nb_frames": "240"}
    if any(stream.get(key) != value for key, value in expected.items()):
        raise AssertionError("Unexpected ffprobe stream contract")
    if abs(float(probe["format"]["duration"]) - 8) > 0.000001:
        raise AssertionError("Output duration changed")
    pts_text = run([str(arguments.ffprobe), "-v", "error", "-select_streams", "v:0", "-show_frames", "-show_entries", "frame=best_effort_timestamp_time,duration_time", "-of", "json", str(arguments.output)], arguments.evidence_dir / "frame_pts.json")
    timestamps = json.loads(pts_text)["frames"]
    if len(timestamps) != 240 or any(abs(float(frame["best_effort_timestamp_time"]) - index / 30) > 0.000001 for index, frame in enumerate(timestamps)):
        raise AssertionError("Frame presentation timeline changed")
    hashes_text = run([str(arguments.ffmpeg), "-v", "error", "-xerror", "-i", str(arguments.output), "-map", "0:v:0", "-fps_mode", "passthrough", "-f", "framehash", "-hash", "sha256", "-"], arguments.evidence_dir / "ffmpeg_decode.json")
    frame_hashes = [line for line in hashes_text.splitlines() if line and not line.startswith("#")]
    if len(frame_hashes) != 240:
        raise AssertionError("FFmpeg did not decode 240 frames")
    results = validate_pixels(arguments.clean, arguments.original, arguments.output)
    atoms = top_level_atoms(arguments.output)
    names = [atom["name"] for atom in atoms]
    if names.index("moov") > names.index("mdat"):
        raise AssertionError("MP4 is not faststart")
    if sha256(arguments.clean) != CLEAN_SHA256 or sha256(arguments.original) != ORIGINAL_SHA256:
        raise AssertionError("Input revision changed during validation")
    results.update({"clean_sha256": CLEAN_SHA256, "original_sha256": ORIGINAL_SHA256,
                    "output_sha256": sha256(arguments.output), "output_bytes": arguments.output.stat().st_size,
                    "ffprobe": probe, "ffmpeg_decoded_frames": len(frame_hashes),
                    "frame_timeline_verified": True, "top_level_atoms": atoms, "faststart": True})
    with (arguments.evidence_dir / "h264_validation.json").open("x", encoding="utf8") as evidence:
        json.dump(results, evidence, indent=2, allow_nan=False)
    print(json.dumps({key: value for key, value in results.items() if key not in ("per_frame", "alignment", "grabs", "ffprobe")}, indent=2))


if __name__ == "__main__":
    main()
