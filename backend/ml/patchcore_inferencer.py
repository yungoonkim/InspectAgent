"""PatchCore CPU Inference Engine for VisionInsight.

Provides fast, robust anomaly score calculation and anomaly map extraction
on CPU without requiring GPU or external cloud dependencies.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import cv2
import numpy as np
import torch
import torchvision.transforms.v2 as T
from PIL import Image

logger = logging.getLogger("vision_insight.ml.patchcore_inferencer")


class PatchCoreInferencer:
    """CPU-friendly PatchCore inference wrapper using Anomalib checkpoint."""

    def __init__(
        self,
        checkpoint_path: Union[str, Path],
        metadata_path: Optional[Union[str, Path]] = None,
        device: str = "cpu",
    ):
        """Initialize and load the PatchCore model.

        Args:
            checkpoint_path: Path to the .ckpt checkpoint file.
            metadata_path: Optional path to model_metadata.json.
            device: Computing device ('cpu' or 'cuda'). Defaults to 'cpu'.
        """
        self.checkpoint_path = Path(checkpoint_path)
        self.device = torch.device(device)
        self.metadata: Dict = {}
        self.load_time_seconds: float = 0.0

        if not self.checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint file not found: {self.checkpoint_path}")

        # Load metadata if available
        if metadata_path is not None and Path(metadata_path).exists():
            with open(metadata_path, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)

        # Standard Preprocessing Transform for PatchCore (256x256, ImageNet Norm)
        self.transform = T.Compose([
            T.Resize((256, 256)),
            T.ToImage(),
            T.ToDtype(torch.float32, scale=True),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

        # Load Model
        self._load_model()

    def _load_model(self) -> None:
        """Load the model onto the target device (CPU)."""
        from anomalib.models import Patchcore

        t0 = time.perf_counter()
        logger.info(f"Loading PatchCore checkpoint from {self.checkpoint_path} on {self.device}...")

        # Load weights and reconstructed memory bank
        self.model = Patchcore.load_from_checkpoint(
            str(self.checkpoint_path),
            map_location=self.device,
        )
        self.model.to(self.device)
        self.model.eval()

        self.load_time_seconds = time.perf_counter() - t0
        logger.info(
            f"Model loaded in {self.load_time_seconds:.3f}s. "
            f"Memory bank shape: {self.memory_bank_shape}"
        )

    @property
    def memory_bank_shape(self) -> Optional[Tuple[int, ...]]:
        """Return the shape of the internal coreset memory bank."""
        if hasattr(self.model, "model") and hasattr(self.model.model, "memory_bank"):
            mb = self.model.model.memory_bank
            return tuple(mb.shape) if mb is not None else None
        return None

    def verify_compatibility(self, expected_threshold: Optional[float] = None) -> Dict[str, Any]:
        """Verify model checkpoint integrity, metadata alignment, and threshold compatibility."""
        import hashlib

        status = {
            "verified": True,
            "reasons": [],
            "checkpoint_sha256": None,
            "memory_bank_matched": False,
            "threshold_matched": False,
        }

        # 1. Compute checkpoint SHA256
        if self.checkpoint_path.exists():
            h = hashlib.sha256()
            with open(self.checkpoint_path, "rb") as f:
                while chunk := f.read(8192):
                    h.update(chunk)
            status["checkpoint_sha256"] = h.hexdigest()
            meta_hash = self.metadata.get("checkpoint_sha256")
            if meta_hash and meta_hash != status["checkpoint_sha256"]:
                status["verified"] = False
                status["reasons"].append(f"Checksum mismatch: expected {meta_hash[:8]}, got {status['checkpoint_sha256'][:8]}")

        # 2. Check memory bank shape
        meta_mb = self.metadata.get("memory_bank_shape")
        actual_mb = list(self.memory_bank_shape) if self.memory_bank_shape else None
        if meta_mb and actual_mb == meta_mb:
            status["memory_bank_matched"] = True
        else:
            status["verified"] = False
            status["reasons"].append(f"Memory bank shape mismatch: meta={meta_mb}, actual={actual_mb}")

        # 3. Check threshold alignment
        calibrated_th = self.metadata.get("calibrated_threshold")
        if expected_threshold is not None and calibrated_th is not None:
            if abs(float(expected_threshold) - float(calibrated_th)) < 1e-3:
                status["threshold_matched"] = True
            else:
                status["verified"] = False
                status["reasons"].append(f"Threshold mismatch: expected {expected_threshold}, calibrated {calibrated_th}")

        return status

    def _prepare_image(self, image_input: Union[str, Path, np.ndarray, Image.Image]) -> torch.Tensor:
        """Convert various image formats into a normalized RGB Tensor [1, 3, 256, 256]."""
        if isinstance(image_input, (str, Path)):
            pil_img = Image.open(image_input).convert("RGB")
        elif isinstance(image_input, np.ndarray):
            # If BGR from cv2.imread
            if len(image_input.shape) == 3 and image_input.shape[2] == 3:
                rgb_array = cv2.cvtColor(image_input, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb_array)
            elif len(image_input.shape) == 2:
                # Grayscale to RGB
                rgb_array = cv2.cvtColor(image_input, cv2.COLOR_GRAY2RGB)
                pil_img = Image.fromarray(rgb_array)
            else:
                raise ValueError(f"Unsupported numpy image shape: {image_input.shape}")
        elif isinstance(image_input, Image.Image):
            pil_img = image_input.convert("RGB")
        else:
            raise TypeError(f"Unsupported image input type: {type(image_input)}")

        # Apply transforms
        tensor = self.transform(pil_img)  # [3, 256, 256]
        return tensor.unsqueeze(0).to(self.device)  # [1, 3, 256, 256]

    def predict(
        self,
        image_input: Union[str, Path, np.ndarray, Image.Image],
    ) -> Dict[str, Union[float, np.ndarray]]:
        """Run PatchCore inference on a single image.

        Args:
            image_input: File path, cv2 numpy array (BGR), or PIL Image.

        Returns:
            Dict containing:
                - 'anomaly_score': float, higher indicates higher anomaly likelihood
                - 'anomaly_map': 2D float32 numpy array [256, 256]
                - 'inference_time_ms': float, latency in milliseconds
        """
        input_tensor = self._prepare_image(image_input)

        t0 = time.perf_counter()
        with torch.no_grad():
            output = self.model(input_tensor)
        inference_time_ms = (time.perf_counter() - t0) * 1000.0

        # Extract score and map from InferenceBatch
        pred_score = float(output.pred_score.detach().cpu().item())
        anomaly_map = output.anomaly_map.detach().cpu().squeeze().numpy()

        return {
            "anomaly_score": pred_score,
            "anomaly_map": anomaly_map,
            "inference_time_ms": round(inference_time_ms, 2),
            "model_name": self.metadata.get("model_name", "PatchCore"),
            "backbone": self.metadata.get("backbone", "resnet18"),
        }

    @staticmethod
    def generate_heatmap_overlay(
        image_bgr: np.ndarray,
        anomaly_map: np.ndarray,
        alpha: float = 0.4,
    ) -> np.ndarray:
        """Create a COLORMAP_JET heatmap overlay on top of original BGR image."""
        # Normalize anomaly map to 0-255
        map_min, map_max = float(np.min(anomaly_map)), float(np.max(anomaly_map))
        if map_max > map_min:
            norm_map = ((anomaly_map - map_min) / (map_max - map_min) * 255.0).astype(np.uint8)
        else:
            norm_map = np.zeros_like(anomaly_map, dtype=np.uint8)

        # Resize heatmap to match image dimensions
        heatmap = cv2.resize(norm_map, (image_bgr.shape[1], image_bgr.shape[0]))
        heatmap_color = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)

        # Overlay blend
        overlay = cv2.addWeighted(image_bgr, 1.0 - alpha, heatmap_color, alpha, 0)
        return overlay


# ==============================================================================
# Singleton Inferencer Cache
# ==============================================================================

import threading

_inferencer_instance: Optional[PatchCoreInferencer] = None
_inferencer_lock = threading.Lock()


def get_patchcore_inferencer(
    checkpoint_path: Optional[Union[str, Path]] = None,
    metadata_path: Optional[Union[str, Path]] = None,
    device: str = "cpu",
    force_reload: bool = False,
) -> Optional[PatchCoreInferencer]:
    """Thread-safe singleton accessor for PatchCoreInferencer.

    Reuses the already loaded model in memory across FastAPI requests.
    """
    global _inferencer_instance

    with _inferencer_lock:
        if _inferencer_instance is not None and not force_reload:
            return _inferencer_instance

        if checkpoint_path is None:
            from backend.config import get_settings
            settings = get_settings()
            if not getattr(settings, "ENABLE_PATCHCORE", True):
                return None
            checkpoint_path = settings.absolute_patchcore_checkpoint_path
            metadata_path = settings.absolute_patchcore_metadata_path
            device = getattr(settings, "PATCHCORE_DEVICE", "cpu")

        ckpt_p = Path(checkpoint_path)
        if not ckpt_p.exists():
            logger.warning(f"PatchCore checkpoint not found at {ckpt_p}. Model inference disabled.")
            return None

        try:
            _inferencer_instance = PatchCoreInferencer(
                checkpoint_path=ckpt_p,
                metadata_path=metadata_path,
                device=device,
            )
            return _inferencer_instance
        except Exception as e:
            logger.error(f"Failed to initialize PatchCoreInferencer from {ckpt_p}: {e}")
            _inferencer_instance = None
            raise e


def reset_patchcore_inferencer() -> None:
    """Reset singleton instance (useful for test isolation)."""
    global _inferencer_instance
    with _inferencer_lock:
        _inferencer_instance = None
