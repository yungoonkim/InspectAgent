"""Read-only saved Crop verification of the browser detector against OpenCV masks."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from uuid import uuid4

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
NODE = """
import {readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {detectBottleEdges} from './src/utils/bottleEdges.ts';
globalThis.fetch=()=>{throw Error('NETWORK_FORBIDDEN');};
const folder=process.argv[1];
const inputs=JSON.parse(readFileSync(join(folder,'inputs.json'),'utf8'));
const results=inputs.map(input=>({...input,edges:detectBottleEdges({width:input.width,height:input.height,
data:new Uint8ClampedArray(readFileSync(join(folder,input.rgba_file)))})}));
writeFileSync(join(folder,'browser_results.json'),JSON.stringify(results,null,2),{flag:'wx'});
"""


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inspection_ids", nargs="+")
    arguments = parser.parse_args()
    output = ROOT / "data/outputs/experiments" / ("bottle-edges-" + uuid4().hex[:12])
    output.mkdir(exist_ok=False)
    records_path = ROOT / "data/inspections.jsonl"
    records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    protected = {records_path: digest(records_path)}
    for relative in ("data/inspection_logs.jsonl",
                     "data/outputs/videos/bottle_conveyor_clean_h264_1920x480_8s.mp4",
                     "data/outputs/videos/bottle_conveyor_bright_no_lines_h264_1920x480_8s.mp4",
                     "data/outputs/videos/bottle_conveyor_mixed_ok_ng_16s_h264_1920x480.mp4"):
        path = ROOT / relative
        if path.is_file():
            protected[path] = digest(path)
    images, inputs = {}, []
    for identifier in arguments.inspection_ids:
        matches = [record for record in records if record["inspection_id"] == identifier]
        if len(matches) != 1 or matches[0].get("metrics", {}).get("input_source") != "LIVEVIEW_GRAB":
            raise RuntimeError("UNIQUE_SAVED_GRAB_REQUIRED")
        record = matches[0]
        directory = ROOT / "data/outputs/grab_inspection_inputs"
        image_path = (directory / (record["image_id"] + ".png")).resolve(strict=True)
        if image_path.parent != directory.resolve():
            raise RuntimeError("IMAGE_PATH_INVALID")
        raw = image_path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        if checksum != record["metrics"]["input_provenance"]["crop_sha256"]:
            raise RuntimeError("SOURCE_HASH_MISMATCH")
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("IMAGE_DECODE_FAILED")
        protected[image_path] = checksum
        images[identifier] = image
        inputs.append({"case_id": identifier, "inspection_id": identifier, "source_sha256": checksum,
                       "stored_mean_gv": record.get("metrics", {}).get("mean"), "kind": "SAVED_CROP"})
    reference = next(iter(images.values()))
    images["SYNTHETIC_PARTIAL"] = reference[:, reference.shape[1] // 2:].copy()
    images["SYNTHETIC_LOW_CONTRAST"] = (reference.astype(float) * 0.04 + 30).astype(np.uint8)
    images["SYNTHETIC_BLANK"] = np.full_like(reference, 127)
    for name in ("SYNTHETIC_PARTIAL", "SYNTHETIC_LOW_CONTRAST", "SYNTHETIC_BLANK"):
        inputs.append({"case_id": name, "inspection_id": None, "kind": "SYNTHETIC_TEST_ONLY"})
    for item in inputs:
        image = images[item["case_id"]]
        item.update({"width": image.shape[1], "height": image.shape[0], "rgba_file": item["case_id"] + ".rgba"})
        with (output / item["rgba_file"]).open("xb") as stream:
            stream.write(cv2.cvtColor(image, cv2.COLOR_BGR2RGBA).tobytes())
    write_json(output / "inputs.json", inputs)
    subprocess.run(["node", "--experimental-strip-types", "--input-type=module", "-e", NODE, str(output)],
                   cwd=ROOT / "frontend", check=True, timeout=90, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    results = json.loads((output / "browser_results.json").read_text(encoding="utf-8"))
    previews, summaries = [], []
    for item in results:
        edges = item["edges"]
        image = images[item["case_id"]]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        threshold, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=4)
        opencv_area = None
        filled = None
        if count > 1:
            largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            body = (labels == largest).astype(np.uint8) * 255
            padded = cv2.copyMakeBorder(body, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
            cv2.floodFill(padded, None, (0, 0), 255)
            filled = cv2.bitwise_or(body, cv2.bitwise_not(padded[1:-1, 1:-1]))
            opencv_area = int((filled > 0).sum())
        regions = edges["regions"]
        masks = {"roi": np.ones(gray.shape, dtype=bool)}
        if regions["body"] is not None:
            if filled is None or edges["assessment"]["outer"]["status"] != "SUCCESS":
                raise RuntimeError("UNSUPPORTED_BODY_STATISTICS")
            masks.update({"body": filled > 0, "background": filled == 0})
        if regions["rim"] is not None:
            if not edges["assessment"]["rim"]["closed"] or len(edges["rim"]) != 72:
                raise RuntimeError("INVENTED_RIM_CLOSURE")
            points = [segment[0] for segment in edges["rim"]]
            rows, columns = np.indices(gray.shape, dtype=float)
            rows += 0.5
            columns += 0.5
            inside = np.zeros(gray.shape, dtype=bool)
            for index, first in enumerate(points):
                second = points[(index + 1) % len(points)]
                if second["y"] == first["y"]:
                    continue
                crossing = ((first["y"] > rows) != (second["y"] > rows)) & (
                    columns < first["x"] + (rows - first["y"]) * (second["x"] - first["x"]) / (second["y"] - first["y"]))
                inside ^= crossing
            masks["rim"] = inside
        for name, mask in masks.items():
            pixels = gray[mask].astype(float)
            expected = {"mean": float(pixels.mean()), "median": float(np.median(pixels)),
                        "std": float(pixels.std()), "pixels": int(pixels.size), "areaRatio": pixels.size / gray.size}
            for field, value in expected.items():
                if regions[name] is None or not np.isclose(regions[name][field], value, rtol=0, atol=1e-6):
                    raise RuntimeError(f"REGION_STATISTIC_MISMATCH:{item['case_id']}:{name}:{field}")
        if item.get("stored_mean_gv") is not None and round(regions["roi"]["mean"], 2) != item["stored_mean_gv"]:
            raise RuntimeError("STORED_ROI_MEAN_MISMATCH")
        overlay = image.copy()
        for name, color in (("outer", (0, 255, 0)), ("rim", (0, 255, 255))):
            for first, second in edges[name]:
                points = [(round(point["x"] - 0.5), round(point["y"] - 0.5)) for point in (first, second)]
                cv2.line(overlay, points[0], points[1], color, 1, cv2.LINE_AA)
        success, encoded = cv2.imencode(".png", overlay)
        if not success:
            raise RuntimeError("OVERLAY_ENCODING_FAILED")
        with (output / (item["case_id"] + "_overlay.png")).open("xb") as stream:
            stream.write(encoded.tobytes())
        tile = np.full((350, 320, 3), (17, 22, 29), np.uint8)
        scale = min(300 / image.shape[1], 300 / image.shape[0])
        resized = cv2.resize(overlay, (round(image.shape[1] * scale), round(image.shape[0] * scale)))
        tile[:resized.shape[0], :resized.shape[1]] = resized
        cv2.putText(tile, item["case_id"], (5, 320), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (255, 255, 255), 1)
        label = f"outer {edges['assessment']['outer']['status']} / rim {edges['assessment']['rim']['status']}"
        cv2.putText(tile, label, (5, 342), cv2.FONT_HERSHEY_SIMPLEX, 0.37, (255, 255, 255), 1)
        previews.append(tile)
        summaries.append({"case_id": item["case_id"], "status": edges["status"], "reasons": edges["reasons"],
                          "assessment": edges["assessment"], "regions": regions,
                          "stored_mean_gv": item.get("stored_mean_gv"), "numpy_statistics_verified": True,
                          "statistics": edges["statistics"], "opencv_otsu_threshold": threshold,
                          "opencv_filled_body_area": opencv_area, "server_decision_changed": False})
    while len(previews) % 4:
        previews.append(np.zeros((350, 320, 3), np.uint8))
    montage = np.vstack([np.hstack(previews[index:index + 4]) for index in range(0, len(previews), 4)])
    success, encoded = cv2.imencode(".png", montage)
    if not success:
        raise RuntimeError("MONTAGE_ENCODING_FAILED")
    with (output / "edge_montage.png").open("xb") as stream:
        stream.write(encoded.tobytes())
    unchanged = all(digest(path) == checksum for path, checksum in protected.items())
    if not unchanged:
        raise RuntimeError("ORIGINAL_DATA_CHANGED")
    write_json(output / "summary.json", {"cases": summaries, "original_files_unchanged": unchanged,
                                         "protected_sha256": {str(path.relative_to(ROOT)): checksum for path, checksum in protected.items()},
                                         "opencv_version": cv2.__version__, "patchcore_calls": 0, "gemini_calls": 0})
    print(json.dumps({"output": str(output), "cases": summaries, "original_files_unchanged": unchanged}, indent=2))


if __name__ == "__main__":
    main()
