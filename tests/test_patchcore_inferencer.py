from pathlib import Path
import numpy as np
import pytest
from PIL import Image

from backend.ml.patchcore_inferencer import PatchCoreInferencer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CKPT_PATH = PROJECT_ROOT / "models" / "patchcore" / "patchcore_bottle.ckpt"
META_PATH = PROJECT_ROOT / "models" / "patchcore" / "model_metadata.json"
SAMPLE_IMAGE = PROJECT_ROOT / "dataset" / "bottle" / "train" / "good" / "000.png"


@pytest.fixture(scope="module")
def cpu_inferencer():
    """Module-level fixture to load PatchCoreInferencer once on CPU."""
    if not CKPT_PATH.exists():
        pytest.skip(f"PatchCore checkpoint not found at {CKPT_PATH}. Run training first.")
    return PatchCoreInferencer(checkpoint_path=CKPT_PATH, metadata_path=META_PATH, device="cpu")


def test_inferencer_initialization(cpu_inferencer):
    """Verify model initialization on CPU and memory bank shape."""
    assert cpu_inferencer.device.type == "cpu"
    assert cpu_inferencer.memory_bank_shape is not None
    assert len(cpu_inferencer.memory_bank_shape) == 2
    assert cpu_inferencer.memory_bank_shape[1] == 384  # ResNet18 patch embedding dimension
    assert cpu_inferencer.memory_bank_shape[0] > 0
    assert cpu_inferencer.load_time_seconds > 0.0


def test_inferencer_predict_file_path(cpu_inferencer):
    """Verify inference using a file path directly."""
    if not SAMPLE_IMAGE.exists():
        pytest.skip(f"Sample image not found: {SAMPLE_IMAGE}")

    result = cpu_inferencer.predict(SAMPLE_IMAGE)
    assert "anomaly_score" in result
    assert "anomaly_map" in result
    assert "inference_time_ms" in result
    assert isinstance(result["anomaly_score"], float)
    assert isinstance(result["anomaly_map"], np.ndarray)
    assert result["anomaly_map"].shape == (256, 256)
    assert result["inference_time_ms"] > 0.0


def test_inferencer_predict_numpy_bgr(cpu_inferencer):
    """Verify inference using OpenCV BGR numpy array."""
    dummy_bgr = np.zeros((900, 900, 3), dtype=np.uint8)
    dummy_bgr[300:600, 300:600] = [128, 128, 128]

    result = cpu_inferencer.predict(dummy_bgr)
    assert isinstance(result["anomaly_score"], float)
    assert result["anomaly_map"].shape == (256, 256)


def test_inferencer_predict_pil_image(cpu_inferencer):
    """Verify inference using a PIL Image."""
    pil_img = Image.new("RGB", (256, 256), color=(200, 200, 200))
    result = cpu_inferencer.predict(pil_img)
    assert isinstance(result["anomaly_score"], float)
    assert result["anomaly_map"].shape == (256, 256)


def test_inferencer_missing_checkpoint_raises():
    """Verify that a nonexistent checkpoint file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        PatchCoreInferencer(checkpoint_path=PROJECT_ROOT / "models" / "nonexistent.ckpt")


def test_inferencer_invalid_image_input_raises(cpu_inferencer):
    """Verify that an unsupported image input type raises TypeError."""
    with pytest.raises(TypeError):
        cpu_inferencer.predict(12345)
