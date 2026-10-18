from unittest.mock import Mock

import cv2
import numpy as np
import pytest


@pytest.fixture(autouse=True)
def isolated_image_api(tmp_path_factory, monkeypatch):
    import backend.anomaly_map_store as maps
    import backend.inspection as inspection
    import backend.main as main
    import backend.storage as storage_module
    from backend.config import get_settings

    directory = tmp_path_factory.mktemp("synthetic_image_api")
    image_path = directory / "synthetic.png"
    image = np.random.default_rng(42).integers(32, 224, (900, 900, 3), dtype=np.uint8)
    assert cv2.imwrite(str(image_path), image)
    registry = inspection.ImageRegistry()
    registry.register_image("IMG-BOTTLE-0001", image_path)
    registry.register_image("IMG-BOTTLE-NONEXISTENT", directory / "missing.png")
    storage = storage_module.JsonlInspectionStorage(directory / "inspections.jsonl", directory / "logs.jsonl")
    monkeypatch.setattr(get_settings(), "DATASET_PATH", str(directory))
    monkeypatch.setattr(inspection, "_image_registry", registry)
    monkeypatch.setattr(inspection, "_id_generator", inspection.InspectionIdGenerator())
    monkeypatch.setattr(storage_module, "_storage_instance", storage)
    monkeypatch.setattr(main, "get_inspection_storage", lambda: storage)
    monkeypatch.setattr(main, "get_patchcore_inferencer", Mock(side_effect=AssertionError("Mock predictor required")))
    monkeypatch.setattr(maps, "get_anomaly_map_dir", lambda: directory / "maps")
    return directory
