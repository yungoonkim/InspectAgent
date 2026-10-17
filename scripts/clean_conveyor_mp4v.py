import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

import cv2
import numpy as np


SOURCE_SHA256 = "daefc8f14912e2a1e1fac77823f7eee97572e47722d3276f93ea3530b1cdda82"
NEUTRAL_BGR = (17, 22, 29)
FOOTER_START = 443


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def metadata(capture):
    fourcc = int(capture.get(cv2.CAP_PROP_FOURCC))
    pixel_format = int(capture.get(cv2.CAP_PROP_CODEC_PIXEL_FORMAT))
    return {
        "width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": capture.get(cv2.CAP_PROP_FPS),
        "frame_count": int(capture.get(cv2.CAP_PROP_FRAME_COUNT)),
        "decoder_fourcc": fourcc.to_bytes(4, "little").decode("ascii", "replace"),
        "decoder_pixel_format": pixel_format.to_bytes(4, "little").decode("ascii", "replace"),
    }


def container_metadata(path):
    content = path.read_bytes()
    atoms = []
    details = {}

    def walk(start, end, parent):
        position = start
        while position + 8 <= end:
            size, kind = struct.unpack_from(">I4s", content, position)
            header = 8
            if size == 1:
                size = struct.unpack_from(">Q", content, position + 8)[0]
                header = 16
            if size == 0:
                size = end - position
            if size < header or position + size > end:
                raise ValueError("Invalid MP4 atom bounds")
            name = kind.decode("latin1")
            atom_path = f"{parent}/{name}"
            atoms.append(atom_path)
            payload = position + header
            if kind in (b"moov", b"trak", b"mdia", b"minf", b"stbl", b"udta", b"ilst"):
                walk(payload, position + size, atom_path)
            elif kind == b"meta":
                walk(payload + 4, position + size, atom_path)
            elif kind == b"hdlr":
                details.setdefault("handlers", []).append(content[payload + 8:payload + 12].decode("ascii"))
            elif kind == b"stsd":
                details["sample_entry"] = content[payload + 12:payload + 16].decode("ascii")
            elif kind == b"stts":
                entries = struct.unpack_from(">I", content, payload + 4)[0]
                details["sample_durations"] = [
                    list(struct.unpack_from(">II", content, payload + 8 + offset * 8))
                    for offset in range(entries)
                ]
            elif kind == b"mdhd" and content[payload] == 0:
                timescale, duration = struct.unpack_from(">II", content, payload + 12)
                details["timescale"] = timescale
                details["duration_units"] = duration
                details["duration_seconds"] = duration / timescale
            elif parent.endswith("/ilst"):
                details.setdefault("tags", {})[name] = content[payload:position + size].decode("utf8", "replace")
            position += size

    walk(0, len(content), "")
    return {"atoms": atoms, **details}


def generate(source_path, output_path):
    if sha256(source_path) != SOURCE_SHA256:
        raise ValueError("Source revision differs from the approved video")
    if output_path.exists():
        raise FileExistsError(output_path)
    capture = cv2.VideoCapture(str(source_path))
    writer = None
    frame_count = 0
    try:
        source_metadata = metadata(capture)
        if not capture.isOpened() or source_metadata["width"] != 1920 or source_metadata["height"] != 480:
            raise ValueError("Unexpected source geometry")
        if source_metadata["fps"] != 30 or source_metadata["frame_count"] != 240:
            raise ValueError("Unexpected source timeline")
        with output_path.open("xb"):
            pass
        writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (1920, 480))
        if not writer.isOpened():
            raise RuntimeError("mp4v writer initialization failed")
        while True:
            decoded, original = capture.read()
            if not decoded:
                break
            cleaned = original.copy()
            cleaned[FOOTER_START:, :] = NEUTRAL_BGR
            if not np.array_equal(original[:FOOTER_START], cleaned[:FOOTER_START]):
                raise AssertionError("Unexpected pre-encoding modification outside the footer")
            writer.write(cleaned)
            frame_count += 1
    finally:
        capture.release()
        if writer is not None:
            writer.release()
    if frame_count != 240 or sha256(source_path) != SOURCE_SHA256:
        raise AssertionError("Source timeline or revision changed")
    return {"written_frames": frame_count, "pre_encoding_preserved_region_exact": True}


def differences(original, cleaned):
    difference = original.astype(np.float32) - cleaned.astype(np.float32)
    mean_square = float(np.mean(difference ** 2))
    return {
        "mae": float(np.mean(np.abs(difference))),
        "psnr_db": 10 * math.log10(255 ** 2 / mean_square) if mean_square else None,
        "max_absolute_difference": int(np.max(np.abs(difference))),
    }


def validate(source_path, output_path):
    original_capture = cv2.VideoCapture(str(source_path))
    clean_capture = cv2.VideoCapture(str(output_path))
    references = {}
    per_frame = []
    source_fingerprints = []
    clean_fingerprints = []
    try:
        output_metadata = metadata(clean_capture)
        for frame_index in range(240):
            original_ok, original = original_capture.read()
            clean_ok, cleaned = clean_capture.read()
            if not original_ok or not clean_ok or cleaned.shape != (480, 1920, 3):
                raise AssertionError(f"Decode failed at frame {frame_index}")
            footer = cleaned[448:]
            per_frame.append({
                "frame_index": frame_index,
                "preserved_region": differences(original[:FOOTER_START], cleaned[:FOOTER_START]),
                "bottle_band": differences(original[107:414], cleaned[107:414]),
                "footer_interior_channel_min": footer.min(axis=(0, 1)).tolist(),
                "footer_interior_channel_max": footer.max(axis=(0, 1)).tolist(),
                "footer_interior_channel_std": footer.std(axis=(0, 1)).tolist(),
                "footer_entire_max_error_from_background": int(np.max(np.abs(cleaned[FOOTER_START:].astype(np.int16) - np.array(NEUTRAL_BGR)))),
            })
            source_fingerprints.append(cv2.resize(original[:FOOTER_START], (120, 28)).astype(np.float32))
            clean_fingerprints.append(cv2.resize(cleaned[:FOOTER_START], (120, 28)).astype(np.float32))
            if frame_index in (0, 60, 120, 180, 239):
                references[frame_index] = cleaned.copy()
        original_eof = not original_capture.read()[0]
        clean_eof = not clean_capture.read()[0]
        if not original_eof or not clean_eof:
            raise AssertionError("Unexpected frames beyond index 239")
    finally:
        original_capture.release()
        clean_capture.release()
    fingerprints = np.stack(source_fingerprints)
    alignment = []
    for frame_index, fingerprint in enumerate(clean_fingerprints):
        distances = np.mean(np.abs(fingerprints - fingerprint), axis=(1, 2, 3))
        alignment.append({"frame_index": frame_index, "nearest_source_index": int(distances.argmin())})
    grabs = []
    for frame_index, reference in references.items():
        for repetition in range(1, 4):
            capture = cv2.VideoCapture(str(output_path))
            try:
                seek_accepted = capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                decoded, grabbed = capture.read()
                next_position = capture.get(cv2.CAP_PROP_POS_FRAMES)
                timestamp_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
                identical = bool(decoded and np.array_equal(reference, grabbed))
                eof_after_last = not capture.read()[0] if frame_index == 239 else None
                grabs.append({
                    "frame_index": frame_index,
                    "repetition": repetition,
                    "seek_accepted": seek_accepted,
                    "next_position": next_position,
                    "timestamp_ms": timestamp_ms,
                    "shape": list(grabbed.shape) if decoded else None,
                    "identical_to_sequential": identical,
                    "difference": differences(reference, grabbed) if decoded else None,
                    "eof_after_last": eof_after_last,
                })
                if not identical or next_position != frame_index + 1:
                    raise AssertionError("Random seek differs from sequential reference")
            finally:
                capture.release()
    summaries = {}
    for region in ("preserved_region", "bottle_band"):
        summaries[region] = {
            metric: {
                "minimum": min(frame[region][metric] for frame in per_frame),
                "mean": float(np.mean([frame[region][metric] for frame in per_frame])),
                "maximum": max(frame[region][metric] for frame in per_frame),
            }
            for metric in ("mae", "psnr_db", "max_absolute_difference")
        }
    return {
        "source_sha256": sha256(source_path),
        "output_sha256": sha256(output_path),
        "output_bytes": output_path.stat().st_size,
        "opencv_version": cv2.__version__,
        "metadata": output_metadata,
        "container": container_metadata(output_path),
        "decoded_frames": len(per_frame),
        "original_eof": original_eof,
        "clean_eof": clean_eof,
        "quantitative_summary": summaries,
        "per_frame": per_frame,
        "alignment": alignment,
        "grabs": grabs,
        "all_captures_released": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    arguments = parser.parse_args()
    if not arguments.evidence_dir.is_dir():
        raise ValueError("The isolated evidence directory must already exist")
    generation = generate(arguments.source, arguments.output)
    results = {"generation": generation, **validate(arguments.source, arguments.output)}
    evidence_path = arguments.evidence_dir / "video_validation.json"
    with evidence_path.open("x", encoding="utf8") as evidence:
        json.dump(results, evidence, indent=2, allow_nan=False)
    print(json.dumps({key: value for key, value in results.items() if key not in ("per_frame", "alignment", "grabs")}, indent=2))
    print(f"Evidence: {evidence_path}")


if __name__ == "__main__":
    main()
