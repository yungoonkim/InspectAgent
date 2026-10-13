"""Inspection domain service for VisionInsight.

Implements inspection ID generation, neutral image registry mapping,
and execution decoupled from ground truth or defect classifications.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
import cv2

from backend.config import Settings, get_settings


class InspectionIdGenerator:
    """Thread-safe sequential inspection ID generator.

    Generates non-colliding IDs in format: INSP-000001, INSP-000002, etc.
    """

    def __init__(self, start_idx: int = 1):
        self._lock = threading.Lock()
        self._counter = start_idx

    def next_id(self) -> str:
        """Generate the next unique inspection ID."""
        with self._lock:
            current = self._counter
            self._counter += 1
            return f"INSP-{current:06d}"

    def reset(self, start_idx: int = 1) -> None:
        """Reset counter (useful for test isolation)."""
        with self._lock:
            self._counter = start_idx


class ImageRegistry:
    """Server-side registry that maps neutral image IDs to internal dataset file paths.

    CRITICAL SAFETY RULE:
    Ground truth directories ('broken_large', 'contamination', etc.) are masked internally
    so that Agent tools and external clients only interact with neutral IDs (e.g. IMG-BOTTLE-0001).
    """

    def __init__(self, dataset_root: Optional[Path] = None):
        self._mapping: Dict[str, Path] = {}
        self._lock = threading.Lock()
        self._dataset_root = dataset_root
        if dataset_root is not None:
            self.refresh(dataset_root)

    def refresh(self, dataset_root: Path) -> None:
        """Scan dataset root and build deterministic neutral ID mappings."""
        with self._lock:
            self._mapping.clear()
            self._dataset_root = dataset_root

            if not dataset_root.exists() or not dataset_root.is_dir():
                return

            # Discover all PNG images deterministically across dataset subdirectories
            # Sorting ensures reproducible ID-to-image assignment
            discovered_paths: List[Path] = []
            for path in sorted(dataset_root.glob("**/*.png")):
                # Ensure ground_truth directory is strictly excluded if present
                if "ground_truth" not in path.parts:
                    discovered_paths.append(path)

            for idx, img_path in enumerate(discovered_paths, start=1):
                image_id = f"IMG-BOTTLE-{idx:04d}"
                self._mapping[image_id] = img_path.resolve()

    def get_path(self, image_id: str) -> Optional[Path]:
        """Resolve a neutral image_id to its absolute server-side filesystem path."""
        with self._lock:
            return self._mapping.get(image_id)

    def list_image_ids(self) -> List[str]:
        """Return list of all registered neutral image IDs without leaking file paths."""
        with self._lock:
            return list(self._mapping.keys())

    def contains(self, image_id: str) -> bool:
        """Check if an image_id is registered."""
        with self._lock:
            return image_id in self._mapping


# Singleton instances for application lifecycle
_id_generator = InspectionIdGenerator()
_image_registry: Optional[ImageRegistry] = None


def get_image_registry(settings: Optional[Settings] = None) -> ImageRegistry:
    """Retrieve or initialize the singleton image registry."""
    global _image_registry
    if _image_registry is None:
        curr_settings = settings or get_settings()
        _image_registry = ImageRegistry(curr_settings.absolute_dataset_path)
    return _image_registry


def execute_inspection(
    product_id: str,
    image_id: str,
    registry: Optional[ImageRegistry] = None,
    id_gen: Optional[InspectionIdGenerator] = None,
) -> Dict[str, Any]:
    """Execute Day 1 inspection workflow.

    1. Validates that image_id exists in server-side registry.
    2. Loads the image securely using OpenCV.
    3. Allocates a unique non-colliding inspection_id.
    4. Sets result='UNKNOWN' since a defect classifier is not yet integrated.
    5. Returns structured inspection details with KST (+09:00) ISO 8601 timestamp.

    Raises:
        KeyError: If image_id is not found in server registry.
        FileNotFoundError: If the mapped image file does not exist on disk.
        ValueError: If OpenCV fails to decode the image.
    """
    reg = registry or get_image_registry()
    generator = id_gen or _id_generator

    # 1. Resolve image path from neutral ID (Prevents arbitrary path traversal)
    image_path = reg.get_path(image_id)
    if image_path is None:
        raise KeyError(f"Image ID '{image_id}' is not registered or allowed by server.")

    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"Underlying image file for '{image_id}' not found on server.")

    # 2. Secure OpenCV image loading
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Failed to decode image file for '{image_id}'.")

    # 3. Generate non-colliding unique inspection ID
    inspection_id = generator.next_id()

    # 4. Determine dimensions and metadata
    height = int(image.shape[0])
    width = int(image.shape[1])
    channels = int(image.shape[2]) if len(image.shape) > 2 else 1

    # 5. Timestamp in KST (UTC+09:00)
    kst = timezone(timedelta(hours=9))
    timestamp = datetime.now(kst).isoformat()

    return {
        "inspection_id": inspection_id,
        "product_id": product_id,
        "image_id": image_id,
        "status": "COMPLETED",
        "result": "UNKNOWN",  # Fixed to UNKNOWN for Day 1 as classifier is pending
        "timestamp": timestamp,
        "image_metadata": {
            "filename": image_path.name,
            "width": width,
            "height": height,
            "channels": channels,
        },
    }
