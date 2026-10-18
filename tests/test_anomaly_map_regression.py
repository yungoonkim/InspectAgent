from pathlib import Path
import json
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from backend import anomaly_map_store as maps
from tests.safe_image_api_fixtures import isolated_image_api


def write_bundle(directory, identifier="INSP-TEST-ALIGN", width=900, height=900):
    signal = np.zeros((256, 256), dtype=np.float32)
    signal[57, 203] = 9
    return maps.save_anomaly_map_artifact(identifier, "IMG-BOTTLE-0001", signal, width, height, custom_dir=directory)


def test_get_missing_overlay_never_writes(tmp_path):
    write_bundle(tmp_path)
    overlay = tmp_path / "INSP-TEST-ALIGN_overlay.png"
    overlay.unlink()
    before = sorted(path.name for path in tmp_path.iterdir())
    assert maps.get_anomaly_map_overlay_path("INSP-TEST-ALIGN", custom_dir=tmp_path) is None
    assert not overlay.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_repeated_save_cannot_replace_existing_bundle(tmp_path):
    write_bundle(tmp_path)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    with pytest.raises((FileExistsError, ValueError)):
        write_bundle(tmp_path)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_metadata_with_wrong_identity_is_unavailable(tmp_path):
    write_bundle(tmp_path)
    target = tmp_path / "INSP-TEST-ALIGN.json"
    metadata = json.loads(target.read_text())
    metadata["inspection_id"] = "INSP-OTHER"
    target.write_text(json.dumps(metadata))
    assert maps.get_anomaly_map_metadata("INSP-TEST-ALIGN", custom_dir=tmp_path) is None
    assert maps.get_anomaly_map_overlay_path("INSP-TEST-ALIGN", custom_dir=tmp_path) is None


@pytest.mark.parametrize("identifier", [" INSP-123", "INSP-123 ", "INSP-123\n"])
def test_inspection_ids_are_exact_not_trimmed(identifier):
    assert not maps.is_valid_inspection_id(identifier)


@pytest.mark.parametrize("failing_link", [1, 2, 3])
def test_partial_publication_is_rolled_back(tmp_path, monkeypatch, failing_link):
    original = maps.os.link
    calls = 0

    def failing(source, target):
        nonlocal calls
        calls += 1
        if calls == failing_link:
            raise OSError("simulated disk publication failure")
        return original(source, target)

    monkeypatch.setattr(maps.os, "link", failing)
    with pytest.raises(OSError):
        write_bundle(tmp_path)
    assert list(tmp_path.iterdir()) == []
    assert maps.get_anomaly_map_metadata("INSP-TEST-ALIGN", custom_dir=tmp_path) is None


def test_failed_encoding_publishes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(maps.cv2, "imencode", lambda *arguments: (False, None))
    with pytest.raises(RuntimeError):
        write_bundle(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_concurrent_duplicate_save_has_single_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    def attempt():
        try:
            write_bundle(tmp_path)
            return True
        except FileExistsError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda index: attempt(), range(2)))
    assert sorted(results) == [False, True]
    assert maps.get_anomaly_map_metadata("INSP-TEST-ALIGN", custom_dir=tmp_path) is not None
    assert len(list(tmp_path.iterdir())) == 3


@pytest.mark.parametrize("width,height", [(900, 900), (640, 360), (1920, 480)])
def test_asymmetric_peak_uses_pixel_centers_not_transposed_axes(tmp_path, width, height):
    metadata = write_bundle(tmp_path, width=width, height=height)
    decoded = cv2.imread(str(tmp_path / metadata["overlay_filename"]), cv2.IMREAD_UNCHANGED)
    assert decoded.shape == (height, width, 4)
    peak_row, peak_column = np.unravel_index(np.argmax(decoded[:, :, 3]), (height, width))
    expected_column = (203 + 0.5) * width / 256 - 0.5
    expected_row = (57 + 0.5) * height / 256 - 0.5
    assert abs(peak_column - expected_column) <= 1.1
    assert abs(peak_row - expected_row) <= 1.1
    assert metadata["spatial_transform"]["coordinate_convention"] == "pixel_centers_half_open_edges"
    with np.load(tmp_path / metadata["npz_filename"], allow_pickle=False) as loaded:
        assert np.unravel_index(np.argmax(loaded["anomaly_map"]), (256, 256)) == (57, 203)


@pytest.mark.parametrize("suffix", ["npz", "json", "_overlay.png"])
def test_incomplete_or_corrupt_bundle_unavailable(tmp_path, suffix):
    write_bundle(tmp_path)
    filename = f"INSP-TEST-ALIGN{suffix}" if suffix.startswith("_") else f"INSP-TEST-ALIGN.{suffix}"
    (tmp_path / filename).write_bytes(b"corrupt")
    assert maps.get_anomaly_map_metadata("INSP-TEST-ALIGN", custom_dir=tmp_path) is None
    assert maps.get_anomaly_map_overlay_path("INSP-TEST-ALIGN", custom_dir=tmp_path) is None


def test_missing_directory_get_is_read_only(tmp_path, monkeypatch):
    missing = tmp_path / "not-created"
    monkeypatch.setenv("ANOMALY_MAP_DIR", str(missing))
    assert maps.get_anomaly_map_metadata("INSP-999") is None
    assert not missing.exists()


def test_symlink_artifact_is_not_followed(tmp_path):
    write_bundle(tmp_path)
    metadata_file = tmp_path / "INSP-TEST-ALIGN.json"
    alternate = tmp_path / "elsewhere.json"
    alternate.write_bytes(metadata_file.read_bytes())
    metadata_file.unlink()
    try:
        metadata_file.symlink_to(alternate)
    except OSError:
        pytest.skip("Windows symlink creation not permitted")
    assert maps.get_anomaly_map_metadata("INSP-TEST-ALIGN", custom_dir=tmp_path) is None


def test_mock_ng_never_gets_a_map(tmp_path):
    with pytest.raises(ValueError):
        write_bundle(tmp_path, identifier="INSP-001391")
    assert maps.get_anomaly_map_metadata("INSP-001391", custom_dir=tmp_path) is None


@pytest.mark.parametrize("field,value", [
    ("crop", [0, 0, 100, 100]), ("flip", True), ("padding", [1, 1]),
    ("model_input_resolution", [512, 256]), ("original_resolution", [900, 800]),
])
def test_incompatible_spatial_metadata_is_not_rendered(tmp_path, field, value):
    write_bundle(tmp_path)
    target = tmp_path / "INSP-TEST-ALIGN.json"
    metadata = json.loads(target.read_text())
    metadata["spatial_transform"][field] = value
    target.write_text(json.dumps(metadata))
    assert maps.get_anomaly_map_metadata("INSP-TEST-ALIGN", custom_dir=tmp_path) is None


@pytest.mark.parametrize("hashes", [None, {}, {"npz": "wrong", "overlay": "wrong"}])
def test_new_schema_requires_checksums_and_preserves_null_threshold(tmp_path, hashes):
    metadata = write_bundle(tmp_path)
    assert metadata["decision_threshold"] is None
    metadata["artifact_sha256"] = hashes
    (tmp_path / "INSP-TEST-ALIGN.json").write_text(json.dumps(metadata))
    assert maps.get_anomaly_map_metadata("INSP-TEST-ALIGN", custom_dir=tmp_path) is None


def test_complete_legacy_bundle_is_read_without_rewriting(tmp_path):
    metadata = write_bundle(tmp_path)
    metadata["schema_version"] = "1.0.0"
    metadata.pop("artifact_sha256")
    metadata["spatial_transform"]["type"] = "isotropic_linear_resize"
    (tmp_path / "INSP-TEST-ALIGN.json").write_text(json.dumps(metadata))
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    assert maps.get_anomaly_map_metadata("INSP-TEST-ALIGN", custom_dir=tmp_path) is not None
    assert maps.get_anomaly_map_overlay_path("INSP-TEST-ALIGN", custom_dir=tmp_path) is not None
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_api_checks_record_image_identity_and_dimensions(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app, get_inspection_storage
    from backend.storage import InspectionRecord

    write_bundle(tmp_path)
    monkeypatch.setattr(maps, "get_anomaly_map_dir", lambda: tmp_path)
    storage = get_inspection_storage()
    client = TestClient(app)
    prefix = "/inspections/INSP-TEST-ALIGN/anomaly-map"
    for changes in (None, {"image_id": "IMG-BOTTLE-OTHER"}, {"metrics": {"width": 640, "height": 900}}):
        if changes is not None:
            storage.save_inspection(InspectionRecord(
                inspection_id="INSP-TEST-ALIGN", product_id="TEST", image_quality_status="NORMAL",
                **({"image_id": "IMG-BOTTLE-0001", "metrics": {"width": 900, "height": 900}} | changes),
            ))
        assert client.get(prefix).status_code == 404
        assert client.get(prefix + "/overlay.png").status_code == 404


def test_sidecar_failure_does_not_change_verdict_or_repeat_predict(monkeypatch):
    from fastapi.testclient import TestClient
    import backend.main as main
    import backend.inspection as inspection

    predictor = Mock()
    predictor.predict.return_value = {
        "anomaly_score": 45.0, "inference_time_ms": 1.0, "model_name": "MockPatchCore",
        "anomaly_map": np.ones((256, 256), dtype=np.float32),
    }
    monkeypatch.setattr(main, "get_patchcore_inferencer", lambda: predictor)
    monkeypatch.setattr(inspection, "save_anomaly_map_artifact", Mock(side_effect=OSError("disk failure")))
    response = TestClient(main.app).post("/inspections", json={
        "product_id": "TEST", "image_id": "IMG-BOTTLE-0001", "capture_anomaly_map": True,
    })
    assert response.status_code == 201
    payload = response.json()
    assert payload["result"] == payload["final_result"] == "NG"
    assert payload["anomaly_score"] == 45.0 and payload["decision_threshold"] == 34.1442
    assert payload["defect_detection_status"] == "COMPLETED"
    assert predictor.predict.call_count == 1
