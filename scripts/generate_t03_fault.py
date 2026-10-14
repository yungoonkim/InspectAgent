"""Script to generate T03 fault-injected image (0.6x brightness reduction) from a normal sample.

Validates that:
1. Normal bottle image (T01) is chosen as source.
2. 0.6x factor is applied, clipped to [0, 255], and stored as uint8.
3. Target is saved in test_data/injected_images/IMG-BOTTLE-INJ-0001.png.
4. Source image is NEVER modified or overwritten (verified by SHA-256 hash).
"""

import hashlib
from pathlib import Path
import sys
import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.vision import analyze_brightness, inject_brightness_fault


def compute_file_sha256(filepath: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def generate_t03_image(
    source_path: Path,
    output_dir: Path,
    output_filename: str = "IMG-BOTTLE-INJ-0001.png",
    factor: float = 0.6,
) -> Path:
    """Generate T03 fault image and verify source image immutability via SHA-256."""
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(f"Source image not found: {source_path}")

    # 1. Compute pre-generation hash of source
    pre_hash = compute_file_sha256(source_path)

    # 2. Read image with OpenCV
    img = cv2.imread(str(source_path.resolve()))
    if img is None:
        raise ValueError(f"Failed to decode source image: {source_path}")

    # 3. Apply brightness fault (NumPy scaling + clip + uint8)
    faulty_img = inject_brightness_fault(img, factor=factor)

    # 4. Save to test_data/injected_images/
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / output_filename
    cv2.imwrite(str(target_path.resolve()), faulty_img)

    # 5. Compute post-generation hash of source
    post_hash = compute_file_sha256(source_path)

    # 6. Verify source immutability
    if pre_hash != post_hash:
        raise RuntimeError(
            f"CRITICAL SAFETY VIOLATION: Source image was mutated! Pre: {pre_hash}, Post: {post_hash}"
        )

    return target_path


def main():
    settings = get_settings()
    source_file = settings.absolute_dataset_path / "train" / "good" / "000.png"
    output_directory = settings.absolute_injected_images_path

    print(f"[1/4] Source Image: {source_file}")
    source_hash_before = compute_file_sha256(source_file)
    print(f"      Source SHA-256 (Before): {source_hash_before}")

    orig_img = cv2.imread(str(source_file.resolve()))
    orig_metrics = analyze_brightness(orig_img)
    print(f"      T01 Metrics: mean={orig_metrics['mean']}, std={orig_metrics['std']}, min={orig_metrics['min']}, max={orig_metrics['max']}")

    print(f"[2/4] Generating T03 0.6x brightness reduced copy...")
    target_path = generate_t03_image(
        source_path=source_file,
        output_dir=output_directory,
        output_filename="IMG-BOTTLE-INJ-0001.png",
        factor=0.6,
    )
    print(f"      Saved to: {target_path}")

    source_hash_after = compute_file_sha256(source_file)
    print(f"[3/4] Source SHA-256 (After):  {source_hash_after}")
    assert source_hash_before == source_hash_after, "Source hash mismatch!"
    print("      Verification SUCCESS: Source image is completely unchanged.")

    injected_img = cv2.imread(str(target_path.resolve()))
    inj_metrics = analyze_brightness(injected_img)
    print(f"[4/4] T03 Metrics: mean={inj_metrics['mean']}, std={inj_metrics['std']}, min={inj_metrics['min']}, max={inj_metrics['max']}")
    print(f"      Mean ratio: {inj_metrics['mean'] / orig_metrics['mean']:.4f} (Expected ~0.60)")


if __name__ == "__main__":
    main()
