"""Vision inspection and image quality analysis module using OpenCV and NumPy.

Focuses on image quality evaluation (e.g. brightness analysis and fault injection)
completely decoupled from product anomaly/defect (OK/NG) inspection decisions.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np


def analyze_brightness(image: np.ndarray) -> Dict[str, float]:
    """Analyze the brightness statistics of an image.

    Converts the image to grayscale and computes mean, standard deviation,
    minimum, and maximum pixel intensity values.

    Args:
        image: BGR or Grayscale image array (NumPy ndarray).

    Returns:
        Dict with keys: 'mean', 'std', 'min', 'max' (all floats rounded to 2 decimals).

    Raises:
        ValueError: If the input image is empty or not a valid NumPy array.
    """
    if image is None or not isinstance(image, np.ndarray) or image.size == 0:
        raise ValueError("Invalid image provided for brightness analysis.")

    # Convert to grayscale if image has color channels
    if len(image.shape) == 3 and image.shape[2] in (3, 4):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif len(image.shape) == 2:
        gray = image
    else:
        raise ValueError(f"Unsupported image shape for brightness analysis: {image.shape}")

    mean_val = float(np.mean(gray))
    std_val = float(np.std(gray))
    min_val = float(np.min(gray))
    max_val = float(np.max(gray))

    return {
        "mean": round(mean_val, 2),
        "std": round(std_val, 2),
        "min": round(min_val, 2),
        "max": round(max_val, 2),
    }


# In-memory cache for baseline statistics to avoid re-reading the entire dataset on every request
_BASELINE_CACHE: Optional[Dict[str, Any]] = None


def compute_baseline_statistics(train_good_dir: Path, force_refresh: bool = False) -> Dict[str, Any]:
    """Compute normal brightness distribution statistics from dataset/bottle/train/good/.

    Calculates mean, std, percentiles (p1, p5, p50, p95, p99), min, and max across
    all normal training images.

    Args:
        train_good_dir: Directory containing normal training bottle images.
        force_refresh: Whether to bypass in-memory cached statistics.

    Returns:
        Dict containing baseline distribution metrics and sample count.
    """
    global _BASELINE_CACHE
    if _BASELINE_CACHE is not None and not force_refresh:
        return _BASELINE_CACHE

    if not train_good_dir.exists() or not train_good_dir.is_dir():
        return {
            "status": "unavailable",
            "message": f"Dataset directory not found: {train_good_dir}",
            "sample_count": 0,
        }

    image_paths = sorted([
        p for p in train_good_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".png"
    ])

    if not image_paths:
        return {
            "status": "unavailable",
            "message": f"No PNG images found in {train_good_dir}",
            "sample_count": 0,
        }

    means: List[float] = []
    stds: List[float] = []

    for path in image_paths:
        img = cv2.imread(str(path))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        means.append(float(np.mean(gray)))
        stds.append(float(np.std(gray)))

    if not means:
        return {
            "status": "unavailable",
            "message": "Failed to decode any images in dataset directory.",
            "sample_count": 0,
        }

    means_arr = np.array(means)
    stds_arr = np.array(stds)

    baseline = {
        "status": "ready",
        "sample_count": len(means_arr),
        "mean_of_means": round(float(np.mean(means_arr)), 2),
        "std_of_means": round(float(np.std(means_arr)), 2),
        "min_mean": round(float(np.min(means_arr)), 2),
        "max_mean": round(float(np.max(means_arr)), 2),
        "average_internal_std": round(float(np.mean(stds_arr)), 2),
        "percentiles": {
            "p1": round(float(np.percentile(means_arr, 1)), 2),
            "p5": round(float(np.percentile(means_arr, 5)), 2),
            "p50": round(float(np.percentile(means_arr, 50)), 2),
            "p95": round(float(np.percentile(means_arr, 95)), 2),
            "p99": round(float(np.percentile(means_arr, 99)), 2),
        },
    }

    _BASELINE_CACHE = baseline
    return baseline


def inject_brightness_fault(image: np.ndarray, factor: float = 0.6) -> np.ndarray:
    """Inject an artificial brightness reduction fault using NumPy.

    Scales all pixel values by factor (default 0.6) and clips to [0, 255].
    Guarantees the original image array is not mutated in-place.

    Args:
        image: Original input image array.
        factor: Brightness multiplier (e.g. 0.6 for 40% reduction).

    Returns:
        New NumPy ndarray with reduced brightness.
    """
    if image is None or not isinstance(image, np.ndarray) or image.size == 0:
        raise ValueError("Invalid image array provided for fault injection.")

    # Convert to float for safe arithmetic scaling, clip, and cast back to uint8
    scaled = np.clip(image.astype(np.float32) * float(factor), 0.0, 255.0)
    return scaled.astype(np.uint8)


def save_modified_image(image: np.ndarray, output_dir: Path, filename: str) -> Path:
    """Save a modified (fault-injected) image to a designated output folder.

    Ensures the original dataset image is NEVER overwritten.

    Args:
        image: Image array to save.
        output_dir: Target output directory (e.g. data/outputs/injected).
        filename: Destination filename.

    Returns:
        Absolute Path of the saved image file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    save_path = output_dir / filename
    success = cv2.imwrite(str(save_path.resolve()), image)
    if not success:
        raise IOError(f"Failed to save modified image to {save_path}")
    return save_path.resolve()


def evaluate_image_quality(
    metrics: Dict[str, float],
    low_threshold: float,
    high_threshold: float,
) -> Dict[str, Any]:
    """Evaluate image quality status strictly separated from product defect inspection.

    IMPORTANT SAFETY & DOMAIN RULES:
    1. A low brightness warning indicates environmental lighting or occlusion suspicion;
       it does NOT confirm a physical hardware failure of the lighting device.
    2. Quality warnings represent acquisition environment health, NOT the product's OK/NG status.

    Args:
        metrics: Brightness metrics (must contain 'mean').
        low_threshold: Lower bound threshold for normal brightness.
        high_threshold: Upper bound threshold for normal brightness.

    Returns:
        Dict containing quality_status, warning_triggered, description,
        and decoupled product_defect_inspection status.
    """
    mean_val = metrics["mean"]

    if mean_val < low_threshold:
        quality_status = "WARNING_LOW_BRIGHTNESS"
        warning_triggered = True
        description = (
            f"Image brightness ({mean_val}) is below lower threshold ({low_threshold}). "
            "Suspected low illumination or optical occlusion (hardware failure not confirmed)."
        )
    elif mean_val > high_threshold:
        quality_status = "WARNING_HIGH_BRIGHTNESS"
        warning_triggered = True
        description = (
            f"Image brightness ({mean_val}) exceeds upper threshold ({high_threshold}). "
            "Suspected overexposure or excessive ambient illumination."
        )
    else:
        quality_status = "NORMAL"
        warning_triggered = False
        description = f"Image brightness ({mean_val}) is within normal operating limits [{low_threshold}, {high_threshold}]."

    return {
        "quality_status": quality_status,
        "warning_triggered": warning_triggered,
        "description": description,
        "applied_thresholds": {
            "low_threshold": low_threshold,
            "high_threshold": high_threshold,
        },
        # Decoupled inspection result: Product anomaly inspection is intentionally separate
        "product_defect_inspection": {
            "status": "UNINSPECTED",
            "message": "Product defect/contamination inspection is separate from image quality assessment.",
        },
    }
