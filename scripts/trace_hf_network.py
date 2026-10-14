"""Identify exact function call that triggers Hugging Face Hub unauthenticated warning."""

import sys
import time
from pathlib import Path

def print_step(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

print_step("Step 1: Importing Patchcore...")
from anomalib.models import Patchcore

ckpt_path = PROJECT_ROOT / "models" / "patchcore" / "patchcore_bottle.ckpt"

print_step(f"Step 2: Calling Patchcore.load_from_checkpoint({ckpt_path.name})...")
model = Patchcore.load_from_checkpoint(str(ckpt_path), map_location="cpu")

print_step("Step 3: Checkpoint loaded!")

print_step("Step 4: Setting model to eval...")
model.eval()

print_step("Step 5: Testing single prediction...")
import torch
dummy_input = torch.zeros(1, 3, 256, 256)
with torch.no_grad():
    out = model(dummy_input)

print_step(f"Step 6: Prediction finished. Anomaly score: {out.pred_score if hasattr(out, 'pred_score') else out}")
