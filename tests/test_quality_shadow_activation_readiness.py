"""A-3-2 activation gates; synthetic inputs and isolated files only."""

import json

import pytest
from pydantic import ValidationError

from backend.config import Settings
from backend.quality_shadow_metrics import measure_png
from backend.quality_shadow_store import ShadowStorageError, ShadowStore
from tests.quality_shadow_helpers import synthetic_input


def test_settings_precedence_without_reading_project_dotenv(tmp_path, monkeypatch):
    settings_file = tmp_path / "synthetic-settings.txt"
    settings_file.write_text("QUALITY_SHADOW_ENABLED=true\n", encoding="utf-8")
    monkeypatch.delenv("QUALITY_SHADOW_ENABLED", raising=False)
    assert Settings(_env_file=settings_file).QUALITY_SHADOW_ENABLED is True
    monkeypatch.setenv("QUALITY_SHADOW_ENABLED", "false")
    assert Settings(_env_file=settings_file).QUALITY_SHADOW_ENABLED is False
    assert Settings(_env_file=settings_file, QUALITY_SHADOW_ENABLED=True).QUALITY_SHADOW_ENABLED is True


def prepared_document():
    payload, source = synthetic_input()
    return measure_png(payload, source), source


@pytest.mark.parametrize("field", ["inspection_id", "crop_sha256"])
@pytest.mark.parametrize("operation", ["read", "publish"])
def test_missing_source_identity_is_rejected(tmp_path, field, operation):
    document, source = prepared_document()
    del document["source"][field]
    store = ShadowStore(tmp_path / "sidecars")
    if operation == "publish":
        with pytest.raises((ValidationError, ShadowStorageError)):
            store.publish(document)
        assert not store.root.exists()
    else:
        target = store.path(source)
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"quality_observability": document}), encoding="utf-8")
        original = target.read_bytes()
        with pytest.raises(ShadowStorageError, match="SHADOW_RESULT_CONFLICT"):
            store.read(source)
        assert target.read_bytes() == original


@pytest.mark.parametrize("field", ["schema_version", "algorithm_version"])
@pytest.mark.parametrize("operation", ["read", "publish"])
def test_explicit_versions_are_required_for_storage(tmp_path, field, operation):
    document, source = prepared_document()
    del document[field]
    store = ShadowStore(tmp_path / "sidecars")
    if operation == "publish":
        with pytest.raises((ValidationError, ShadowStorageError)):
            store.publish(document)
        assert not store.root.exists()
    else:
        target = store.path(source)
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"quality_observability": document}), encoding="utf-8")
        original = target.read_bytes()
        with pytest.raises(ShadowStorageError, match="SHADOW_RESULT_CONFLICT"):
            store.read(source)
        assert target.read_bytes() == original


@pytest.mark.parametrize("field", ["schema_version", "algorithm_version"])
def test_unrecognized_version_is_rejected_without_publishing(tmp_path, field):
    document, source = prepared_document()
    document[field] = "unsupported-synthetic-version"
    store = ShadowStore(tmp_path / "sidecars")
    with pytest.raises((ValidationError, ShadowStorageError)):
        store.publish(document)
    assert not store.root.exists()
