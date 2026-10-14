"""Threshold Calibration Script for PatchCore Bottle Model.

Evaluates strictly the 29 validation normal images from models/patchcore/dataset_split.json.
Calculates Mean, Std, Min, Max, P95, P99, and candidate thresholds.
Documents small-sample (N=29) statistical limitations.
Selects conservative MVP threshold to prevent False Positives.
Does NOT access test images or defect labels.
"""

import json
import os
import sys
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

import numpy as np
from backend.ml.patchcore_inferencer import get_patchcore_inferencer, reset_patchcore_inferencer


def calibrate_threshold():
    print("=" * 75)
    print("VisionInsight — PatchCore Threshold Calibration (Step 4)")
    print("=" * 75)

    split_file = project_root / "models" / "patchcore" / "dataset_split.json"
    meta_file = project_root / "models" / "patchcore" / "model_metadata.json"
    train_good_dir = project_root / "dataset" / "bottle" / "train" / "good"

    if not split_file.exists():
        raise FileNotFoundError(f"Split specification not found: {split_file}")

    with open(split_file, "r", encoding="utf-8") as f:
        split_data = json.load(f)

    val_filenames = split_data.get("val_files", [])
    print(f"[Validation Set] Number of holdout normal images: {len(val_filenames)}")
    assert len(val_filenames) == 29, f"Expected 29 validation images, got {len(val_filenames)}"

    # Reset and load official 180-image model
    reset_patchcore_inferencer()
    inferencer = get_patchcore_inferencer()
    if inferencer is None:
        raise RuntimeError("Failed to load PatchCoreInferencer")

    print(f"[Model] Device: {inferencer.device}")
    print(f"[Model] Memory Bank Shape: {inferencer.memory_bank_shape}")
    assert inferencer.memory_bank_shape == (9216, 384), "Must use the retrained 180-image model"

    # Evaluate 29 validation images
    scores = []
    latencies = []
    print("\n[Inference] Evaluating 29 independent normal validation images...")
    for idx, fname in enumerate(val_filenames, start=1):
        img_path = train_good_dir / fname
        if not img_path.exists():
            raise FileNotFoundError(f"Validation image missing: {img_path}")

        res = inferencer.predict(img_path)
        score = float(res["anomaly_score"])
        latency = float(res["inference_time_ms"])
        scores.append(score)
        latencies.append(latency)
        print(f"  [{idx:02d}/29] {fname} -> Score: {score:.4f} ({latency:.1f}ms)")

    scores_arr = np.array(scores)
    latencies_arr = np.array(latencies)

    # Statistical Metrics
    score_mean = float(np.mean(scores_arr))
    score_std = float(np.std(scores_arr, ddof=1))
    score_min = float(np.min(scores_arr))
    score_max = float(np.max(scores_arr))
    score_p90 = float(np.percentile(scores_arr, 90))
    score_p95 = float(np.percentile(scores_arr, 95))
    score_p99 = float(np.percentile(scores_arr, 99))
    mu_plus_2sigma = float(score_mean + 2 * score_std)
    mu_plus_3sigma = float(score_mean + 3 * score_std)

    print("\n" + "=" * 75)
    print("Normal Validation Score Distribution (N=29):")
    print("=" * 75)
    print(f"  - Mean (μ):             {score_mean:.4f}")
    print(f"  - StdDev (σ):           {score_std:.4f}")
    print(f"  - Min:                  {score_min:.4f}")
    print(f"  - Max:                  {score_max:.4f}")
    print(f"  - 90th Percentile:      {score_p90:.4f}")
    print(f"  - 95th Percentile:      {score_p95:.4f}")
    print(f"  - 99th Percentile:      {score_p99:.4f}")
    print(f"  - Mean + 2σ:            {mu_plus_2sigma:.4f}")
    print(f"  - Mean + 3σ:            {mu_plus_3sigma:.4f}")
    print(f"  - Mean Inference Latency: {np.mean(latencies_arr):.2f} ms")

    print("\n" + "=" * 75)
    print("Candidate Thresholds Analysis:")
    print("=" * 75)
    candidates = [
        {
            "name": "P95 Percentile",
            "threshold": round(score_p95, 4),
            "policy": "Tolerates 5% false alarm in validation. Aggressive.",
            "val_false_positives": int(np.sum(scores_arr > score_p95)),
        },
        {
            "name": "P99 Percentile",
            "threshold": round(score_p99, 4),
            "policy": "Tolerates 1% false alarm (interpolated). Moderate.",
            "val_false_positives": int(np.sum(scores_arr > score_p99)),
        },
        {
            "name": "Normal Maximum",
            "threshold": round(score_max, 4),
            "policy": "Strict zero FP on validation set. Zero-margin boundary.",
            "val_false_positives": 0,
        },
        {
            "name": "Mean + 3σ (Conservative MVP)",
            "threshold": round(mu_plus_3sigma, 4),
            "policy": "99.7% Gaussian confidence interval. Robust safety margin against normal noise.",
            "val_false_positives": int(np.sum(scores_arr > mu_plus_3sigma)),
        },
    ]

    for c in candidates:
        print(f"  [{c['name']}] Threshold: {c['threshold']:.4f} | Val FPs: {c['val_false_positives']} | Policy: {c['policy']}")

    # Select Candidate: Mean + 3σ (or Max if Max > Mean + 3σ)
    # To prevent any normal sample false positive in MVP while retaining high defect sensitivity,
    # we select max(score_max, mu_plus_3sigma) rounded to 4 decimals.
    selected_threshold = round(max(score_max + 0.05, mu_plus_3sigma), 4)
    print(f"\n[Selection] Selected MVP Threshold: {selected_threshold:.4f}")
    print(f"  -> Rationale: Ensures 0 FP on validation set (Max={score_max:.4f}) with 3σ statistical safety margin ({mu_plus_3sigma:.4f}).")

    # Document statistical limitations of N=29 sample
    statistical_limitations = [
        "Small sample size (N=29) limits empirical percentile estimation accuracy (P99 is interpolated between top 2 samples).",
        "Normal distribution assumption for μ+3σ is an approximation; empirical distance distribution may exhibit mild skewness.",
        "Threshold does not account for unseen factory lighting fluctuations; image quality warnings must supplement decision confidence.",
    ]

    calibration_result = {
        "validation_sample_count": 29,
        "model_version": "PatchCore-ResNet18-180Train",
        "score_distribution": {
            "mean": round(score_mean, 4),
            "std": round(score_std, 4),
            "min": round(score_min, 4),
            "max": round(score_max, 4),
            "p90": round(score_p90, 4),
            "p95": round(score_p95, 4),
            "p99": round(score_p99, 4),
            "mu_plus_2sigma": round(mu_plus_2sigma, 4),
            "mu_plus_3sigma": round(mu_plus_3sigma, 4),
        },
        "candidate_thresholds": candidates,
        "selected_threshold": selected_threshold,
        "selection_rationale": "Conservative MVP zero-FP criterion: max(Max + 0.05, Mean + 3σ).",
        "statistical_limitations": statistical_limitations,
    }

    # Save to model_metadata.json
    if meta_file.exists():
        with open(meta_file, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    else:
        metadata = {}

    metadata["calibrated_threshold"] = selected_threshold
    metadata["calibration"] = calibration_result

    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"[Metadata] Updated metadata written to {meta_file}")
    return calibration_result


if __name__ == "__main__":
    calibrate_threshold()
