import hashlib
import subprocess
import os
from pathlib import Path

import cv2
import numpy as np

from backend.video_source import VideoEntry


def synthetic_video(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    path = root / "clip.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (64, 48))
    assert writer.isOpened()
    try:
        for index in range(240):
            frame = np.full((48, 64, 3), (index % 240, 60, 180), dtype=np.uint8)
            frame[:, index % 64, :] = (20, 200, 40)
            writer.write(frame)
    finally:
        writer.release()
    entry = VideoEntry("VID-000001", path.name, hashlib.sha256(path.read_bytes()).hexdigest(), 64, 48, 30, 240, "mpeg4")
    return path, entry


def directory_link(link: Path, target: Path):
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(target, target_is_directory=True)
