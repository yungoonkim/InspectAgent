"""Synthetic PNG fixtures, never operating captures."""

import hashlib

import cv2
import numpy as np

from backend.quality_shadow_metrics import SourceIdentity


def synthetic_input(number=990001, height=32, width=40, image=None):
    if image is None:
        image = np.random.default_rng(number).integers(20, 240, (height, width, 3), dtype=np.uint8)
    success, encoded = cv2.imencode(".png", image)
    assert success
    payload = encoded.tobytes()
    source = SourceIdentity(inspection_id=f"INSP-{number:06d}", image_id=f"IMG-GRAB-{number:032x}",
        crop_sha256=hashlib.sha256(payload).hexdigest(), width=image.shape[1], height=image.shape[0])
    return payload, source
