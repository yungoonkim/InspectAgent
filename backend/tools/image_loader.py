"""Image loading and metadata extraction utilities using OpenCV.

This module provides functions to locate and load PNG images strictly from
designated dataset directories, without allowing arbitrary user-supplied file paths.
"""

from pathlib import Path
from typing import Any, Dict, Optional
import cv2


def find_first_png(target_dir: Path) -> Optional[Path]:
    """Find the first PNG image file in the specified directory.

    Sorts file names alphabetically to guarantee deterministic behavior.
    Returns None if the directory does not exist or contains no PNG files.
    """
    if not target_dir.exists() or not target_dir.is_dir():
        return None

    png_files = sorted([
        f for f in target_dir.iterdir()
        if f.is_file() and f.suffix.lower() == ".png"
    ])
    return png_files[0] if png_files else None


def load_image_metadata(image_path: Path) -> Dict[str, Any]:
    """Load an image using OpenCV and return its dimensions and channel count.

    Args:
        image_path: Path to the image file to read.

    Returns:
        Dict containing filename, width, height, and channels.

    Raises:
        FileNotFoundError: If the image file does not exist.
        ValueError: If OpenCV fails to decode the image (corrupted or unreadable file).
    """
    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    # cv2.imread returns None if the file is invalid, corrupted, or unsupported
    image = cv2.imread(str(image_path.resolve()))
    if image is None:
        raise ValueError(f"Failed to decode image file (corrupted or unreadable): {image_path.name}")

    height = int(image.shape[0])
    width = int(image.shape[1])
    channels = int(image.shape[2]) if len(image.shape) > 2 else 1

    return {
        "filename": image_path.name,
        "width": width,
        "height": height,
        "channels": channels,
    }
