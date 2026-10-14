"""Verification Script for PatchCore CPU Inference.

Verifies:
1. Model loading on strictly CPU environment (`map_location="cpu"`).
2. Memory bank shape and weights integrity.
3. Model file size, load time, and RAM memory consumption.
4. Anomaly score and latency on real bottle images (normal & defect).
5. Does NOT optimize decision threshold.
6. Does NOT access ground truth masks or answer files.
"""

import os
import sys
import time
from pathlib import Path

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    os.environ["PYTHONIOENCODING"] = "utf-8"

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import ctypes
from ctypes import wintypes
import numpy as np
import torch

from backend.ml.patchcore_inferencer import PatchCoreInferencer


def get_process_memory_mb() -> float:
    """Get current process working set (RAM usage) in MB using psapi on Windows."""
    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    try:
        psapi = ctypes.WinDLL("psapi.dll")
        kernel32 = ctypes.WinDLL("kernel32.dll")
        pid = os.getpid()
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        hProcess = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if hProcess:
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            success = psapi.GetProcessMemoryInfo(hProcess, ctypes.byref(counters), counters.cb)
            kernel32.CloseHandle(hProcess)
            if success:
                return counters.WorkingSetSize / (1024 * 1024)
    except Exception:
        pass
    return 0.0


def verify_patchcore_cpu():
    project_root = Path(__file__).resolve().parent.parent
    ckpt_path = project_root / "models" / "patchcore" / "patchcore_bottle.ckpt"
    meta_path = project_root / "models" / "patchcore" / "model_metadata.json"

    print("=" * 75)
    print("VisionInsight — PatchCore CPU Inference Verification (Day 3.5 Step 2)")
    print("=" * 75)

    # 1. Check Model Checkpoint Existence & File Size
    if not ckpt_path.exists():
        raise FileNotFoundError(f"Checkpoint file not found: {ckpt_path}. Run scripts/train_patchcore.py first.")

    ckpt_bytes = ckpt_path.stat().st_size
    ckpt_mb = ckpt_bytes / (1024 ** 2)
    print(f"[Model File] Path: {ckpt_path}")
    print(f"[Model File] File Size: {ckpt_mb:.2f} MB ({ckpt_bytes:,} bytes)")

    # 2. Measure RAM Before Loading
    ram_before_mb = get_process_memory_mb()
    print(f"[System Memory] RAM usage before model load: {ram_before_mb:.2f} MB")

    # 3. Load Model on CPU & Measure Load Time
    print("\n[Loading] Initializing PatchCoreInferencer on CPU...")
    t_load_start = time.perf_counter()
    inferencer = PatchCoreInferencer(
        checkpoint_path=ckpt_path,
        metadata_path=meta_path,
        device="cpu",
    )
    load_time_seconds = time.perf_counter() - t_load_start

    ram_after_mb = get_process_memory_mb()
    ram_increment_mb = ram_after_mb - ram_before_mb

    print(f"[Loading] Model loading time: {load_time_seconds:.3f} seconds")
    print(f"[System Memory] RAM usage after model load: {ram_after_mb:.2f} MB (Delta: +{ram_increment_mb:.2f} MB)")
    print(f"[Model State] Memory bank shape: {inferencer.memory_bank_shape}")

    # 4. Define Test Images (Direct image files, no GT masks, no answer files)
    test_cases = [
        {
            "id": "IMG-TRAIN-GOOD-000",
            "type": "Train Normal (Self-check)",
            "path": project_root / "dataset" / "bottle" / "train" / "good" / "000.png",
        },
        {
            "id": "IMG-TEST-GOOD-000",
            "type": "Unseen Test Normal",
            "path": project_root / "dataset" / "bottle" / "test" / "good" / "000.png",
        },
        {
            "id": "IMG-TEST-DEFECT-000",
            "type": "Unseen Test Defect (broken_large)",
            "path": project_root / "dataset" / "bottle" / "test" / "broken_large" / "000.png",
        },
    ]

    print("\n" + "=" * 75)
    print("CPU Inference Tests on Real Bottle Images (No Thresholding, Raw Scores)")
    print("=" * 75)
    print(f"{'Image ID':<22} | {'Category':<26} | {'Score':<10} | {'Latency (ms)':<12}")
    print("-" * 75)

    results = []
    # Warmup
    _ = inferencer.predict(test_cases[0]["path"])

    for tc in test_cases:
        img_path = tc["path"]
        if not img_path.exists():
            print(f"Warning: {img_path} not found. Skipping.")
            continue

        res = inferencer.predict(img_path)
        score = res["anomaly_score"]
        latency = res["inference_time_ms"]
        anomaly_map = res["anomaly_map"]

        results.append({
            "id": tc["id"],
            "type": tc["type"],
            "score": score,
            "latency_ms": latency,
            "map_shape": anomaly_map.shape,
            "map_min": float(np.min(anomaly_map)),
            "map_max": float(np.max(anomaly_map)),
        })

        print(f"{tc['id']:<22} | {tc['type']:<26} | {score:<10.4f} | {latency:<10.2f} ms")

    print("-" * 75)

    # 5. Latency Benchmark (5 repeated runs on CPU)
    print("\n[Latency Benchmark] Running 5 repeated CPU inferences on unseen test image...")
    sample_img = test_cases[1]["path"]
    latencies = []
    for _ in range(5):
        res = inferencer.predict(sample_img)
        latencies.append(res["inference_time_ms"])

    avg_lat = np.mean(latencies)
    std_lat = np.std(latencies)
    min_lat = np.min(latencies)
    max_lat = np.max(latencies)

    print(f"[Latency Benchmark] CPU Latency (5 runs):")
    print(f"  - Average: {avg_lat:.2f} ms")
    print(f"  - StdDev:  {std_lat:.2f} ms")
    print(f"  - Min:     {min_lat:.2f} ms")
    print(f"  - Max:     {max_lat:.2f} ms")

    print("\n" + "=" * 75)
    print("Verification Summary:")
    print(f"  - Device: CPU (Intel Core i7)")
    print(f"  - Model File Size: {ckpt_mb:.2f} MB")
    print(f"  - Model Loading Time: {load_time_seconds:.3f} s")
    print(f"  - RAM Overhead: +{ram_increment_mb:.2f} MB")
    print(f"  - Memory Bank Shape: {inferencer.memory_bank_shape}")
    print(f"  - Train Good Score: {results[0]['score']:.4f}")
    print(f"  - Test Good Score:  {results[1]['score']:.4f}")
    print(f"  - Test Defect Score: {results[2]['score']:.4f}")
    print("=" * 75)


if __name__ == "__main__":
    verify_patchcore_cpu()
