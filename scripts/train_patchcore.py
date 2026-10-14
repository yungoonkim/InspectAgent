"""PatchCore Training Script for MVTec AD Bottle dataset with Train/Val Pre-split.

Key Specifications:
1. Strictly uses the 180 normal images from the pre-split defined in models/patchcore/dataset_split.json.
2. 29 validation normal images are strictly excluded from memory bank construction.
3. Pre-trained ResNet-18 backbone (frozen weights).
4. Coreset sub-sampling (ratio: 0.05) for high CPU inference efficiency.
5. Saves official Anomalib Lightning checkpoint to models/patchcore/patchcore_bottle.ckpt.
6. Saves detailed metadata including split parameters to models/patchcore/model_metadata.json.
7. Does NOT access ground_truth masks or test labels.
"""

import json
import os
import shutil
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

import torch
from anomalib.data import Folder
from anomalib.data.utils import TestSplitMode, ValSplitMode
from anomalib.engine import Engine
from anomalib.models import Patchcore


def train_patchcore():
    project_root = Path(__file__).resolve().parent.parent
    train_good_dir = project_root / "dataset" / "bottle" / "train" / "good"
    output_dir = project_root / "models" / "patchcore"
    output_dir.mkdir(parents=True, exist_ok=True)

    split_file = output_dir / "dataset_split.json"
    ckpt_target_path = output_dir / "patchcore_bottle.ckpt"
    meta_target_path = output_dir / "model_metadata.json"

    print("=" * 70)
    print("VisionInsight — PatchCore Bottle Training (180 Train / 29 Val Split)")
    print("=" * 70)

    # 1. Dataset Split Verification
    if not split_file.exists():
        raise FileNotFoundError(f"Split file not found: {split_file}")

    with open(split_file, "r", encoding="utf-8") as f:
        split_meta = json.load(f)

    train_filenames = set(split_meta["train_files"])
    val_filenames = set(split_meta["val_files"])

    print(f"[Dataset Split] Total source images: {split_meta['total_count']}")
    print(f"[Dataset Split] Training normal images: {len(train_filenames)}")
    print(f"[Dataset Split] Validation normal images (isolated): {len(val_filenames)}")
    assert len(train_filenames) == 180, f"Expected 180 train images, got {len(train_filenames)}"
    assert len(val_filenames) == 29, f"Expected 29 val images, got {len(val_filenames)}"
    assert train_filenames.isdisjoint(val_filenames), "Train and validation splits must not overlap"

    # Prepare isolated training directory: data/splits/train_good
    isolated_train_dir = project_root / "data" / "splits" / "train_good"
    isolated_train_dir.mkdir(parents=True, exist_ok=True)

    # Clear existing and populate only the 180 train files
    for existing_file in isolated_train_dir.glob("*.png"):
        existing_file.unlink()

    for fname in sorted(train_filenames):
        src_path = train_good_dir / fname
        dst_path = isolated_train_dir / fname
        if not src_path.exists():
            raise FileNotFoundError(f"Source image not found: {src_path}")
        # Use hard link if possible, fallback to copy
        try:
            os.link(src_path, dst_path)
        except Exception:
            shutil.copy2(src_path, dst_path)

    actual_train_count = len(list(isolated_train_dir.glob("*.png")))
    print(f"[Dataset Split] Prepared isolated train directory: {isolated_train_dir} ({actual_train_count} files)")
    if actual_train_count != 180:
        raise ValueError(f"Expected 180 isolated train images, found {actual_train_count}")

    # 2. Hardware / Device Check
    use_cuda = torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0) if use_cuda else "CPU"
    accelerator = "gpu" if use_cuda else "cpu"
    print(f"[Hardware] Accelerator: {accelerator.upper()} ({device_name})")
    if use_cuda:
        torch.cuda.reset_peak_memory_stats()
        start_vram = torch.cuda.memory_allocated() / (1024 ** 2)
        print(f"[Hardware] Initial VRAM: {start_vram:.2f} MB")

    # 3. DataModule Configuration (Strictly 180 train images, no test/val split inside anomalib)
    datamodule = Folder(
        name="bottle_patchcore_split",
        normal_dir=isolated_train_dir,
        normal_split_ratio=0.0,
        test_split_mode=TestSplitMode.NONE,
        val_split_mode=ValSplitMode.NONE,
        train_batch_size=16,
        eval_batch_size=16,
        num_workers=0,  # Stability on Windows
    )

    # 4. PatchCore Model Configuration
    backbone = "resnet18"
    coreset_ratio = 0.05
    layers = ["layer2", "layer3"]

    print(f"[Model] Backbone: {backbone} (ImageNet pre-trained, weights frozen)")
    print(f"[Model] Feature Extraction Layers: {layers}")
    print(f"[Model] Coreset Sampling Ratio: {coreset_ratio}")

    model = Patchcore(
        backbone=backbone,
        layers=layers,
        pre_trained=True,
        coreset_sampling_ratio=coreset_ratio,
    )

    # 5. Engine Setup & Fitting
    temp_engine_root = output_dir / "temp_engine"
    engine = Engine(
        accelerator=accelerator,
        devices=1,
        max_epochs=1,
        default_root_dir=temp_engine_root,
        limit_val_batches=0,
    )

    start_time = time.perf_counter()
    print("\n[Training] Starting memory bank feature extraction & coreset selection...")
    engine.fit(model=model, datamodule=datamodule)
    training_time = time.perf_counter() - start_time
    print(f"[Training] Feature extraction & coreset selection completed in {training_time:.2f} seconds.")

    # 6. Peak VRAM Check
    peak_vram_mb = 0.0
    if use_cuda:
        peak_vram_mb = torch.cuda.max_memory_allocated() / (1024 ** 2)
        print(f"[Hardware] Peak VRAM used: {peak_vram_mb:.2f} MB")

    # 7. Checkpoint Extraction & Saving
    found_ckpts = list(temp_engine_root.rglob("*.ckpt"))
    if not found_ckpts:
        raise RuntimeError("No checkpoint file generated by Anomalib Engine.fit()")

    latest_ckpt = max(found_ckpts, key=lambda p: p.stat().st_mtime)
    print(f"[Checkpoint] Generated checkpoint: {latest_ckpt}")

    # Copy to standardized location: models/patchcore/patchcore_bottle.ckpt
    shutil.copy2(latest_ckpt, ckpt_target_path)
    file_size_mb = ckpt_target_path.stat().st_size / (1024 ** 2)
    print(f"[Checkpoint] Standardized checkpoint saved: {ckpt_target_path} ({file_size_mb:.2f} MB)")

    # Clean up temp engine artifacts
    try:
        shutil.rmtree(temp_engine_root)
    except Exception as e:
        print(f"[Cleanup] Warning: could not delete temp engine dir: {e}")

    # 8. Verify Memory Bank Shape in Model
    memory_bank_shape = list(model.model.memory_bank.shape) if hasattr(model.model, "memory_bank") else None
    print(f"[Memory Bank] Stored vectors shape: {memory_bank_shape}")

    # 9. Save Metadata for Inference
    metadata = {
        "model_name": "PatchCore",
        "category": "bottle",
        "framework": "anomalib",
        "anomalib_version": "2.7.0",
        "torch_version": torch.__version__,
        "backbone": backbone,
        "layers": layers,
        "coreset_sampling_ratio": coreset_ratio,
        "train_image_count": len(train_filenames),
        "val_image_count": len(val_filenames),
        "dataset_split_file": "dataset_split.json",
        "split_seed": split_meta.get("random_seed", 42),
        "train_image_dir": "data/splits/train_good",
        "image_size": [256, 256],
        "normalization": {
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
        },
        "training_device": f"{accelerator.upper()} ({device_name})",
        "training_time_seconds": round(training_time, 2),
        "peak_vram_mb": round(peak_vram_mb, 2),
        "checkpoint_file": "patchcore_bottle.ckpt",
        "checkpoint_size_mb": round(file_size_mb, 2),
        "memory_bank_shape": memory_bank_shape,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    with open(meta_target_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"[Metadata] Metadata written: {meta_target_path}")
    print("=" * 70)
    print("PatchCore retraining (180 Train images) finished successfully!")
    print("=" * 70)


if __name__ == "__main__":
    train_patchcore()
