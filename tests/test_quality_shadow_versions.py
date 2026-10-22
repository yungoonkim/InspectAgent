"""Explicit immutable sidecar versions; synthetic PNGs and temporary files only."""

import json

import pytest
from pydantic import ValidationError

from backend.quality_shadow_metrics import ALGORITHM_VERSION, SCHEMA_VERSION, ShadowResult, failed_result, measure_png
from backend.quality_shadow_store import ShadowStorageError, ShadowStore
from backend.quality_shadow_worker import QualityShadowWorker, ShadowJob
from tests.quality_shadow_helpers import synthetic_input


VERSION_FIELDS = ["schema_version", "algorithm_version"]


def assert_rejected(tmp_path, document, source, operation):
    store = ShadowStore(tmp_path / "sidecars")
    if operation == "model":
        with pytest.raises(ValidationError):
            ShadowResult.model_validate(document)
    elif operation == "publish":
        with pytest.raises(ValidationError):
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


@pytest.mark.parametrize("operation", ["model", "publish", "read"])
@pytest.mark.parametrize("field", VERSION_FIELDS)
@pytest.mark.parametrize("value", [None, "", " ", "\t\n", 0, 1.0, True, [], {}, "unsupported-version"])
def test_invalid_explicit_versions_are_rejected(tmp_path, operation, field, value):
    payload, source = synthetic_input()
    document = measure_png(payload, source)
    document[field] = value
    assert_rejected(tmp_path, document, source, operation)


@pytest.mark.parametrize("operation", ["model", "publish", "read"])
@pytest.mark.parametrize("fields", [["schema_version"], ["algorithm_version"], VERSION_FIELDS])
def test_missing_versions_are_rejected_on_all_validation_paths(tmp_path, operation, fields):
    payload, source = synthetic_input()
    document = measure_png(payload, source)
    for field in fields:
        del document[field]
    assert_rejected(tmp_path, document, source, operation)


@pytest.mark.parametrize("kind,status", [("normal", "MEASURED"), ("small", "MEASURED_PARTIALLY"), ("failed", "NOT_MEASURED")])
def test_internal_generation_explicitly_supplies_versions_for_every_status(tmp_path, kind, status):
    payload, source = synthetic_input(height=3, width=3) if kind == "small" else synthetic_input()
    document = failed_result(source, 1.0).model_dump(mode="json") if kind == "failed" else measure_png(payload, source)
    assert document["schema_version"] == SCHEMA_VERSION
    assert document["algorithm_version"] == ALGORITHM_VERSION
    assert document["status"] == status
    assert set(VERSION_FIELDS) <= set(ShadowResult.model_json_schema()["required"])
    store = ShadowStore(tmp_path / "sidecars")
    first = store.publish(document)
    original = store.path(source).read_bytes()
    assert store.read(source) == first
    assert store.publish(document) == first
    assert store.path(source).read_bytes() == original
    assert list(store.path(source).parent.glob("TMP-*")) == []


@pytest.mark.parametrize("fields", [["schema_version"], ["algorithm_version"], VERSION_FIELDS])
def test_unversioned_existing_file_is_neither_overwritten_nor_reused(tmp_path, fields):
    payload, source = synthetic_input()
    valid = measure_png(payload, source)
    corrupt = dict(valid)
    for field in fields:
        del corrupt[field]
    store = ShadowStore(tmp_path / "sidecars")
    target = store.path(source)
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"quality_observability": corrupt}), encoding="utf-8")
    original = target.read_bytes()
    with pytest.raises(ShadowStorageError, match="SHADOW_RESULT_CONFLICT"):
        store.publish(valid)
    assert target.read_bytes() == original
    assert list(target.parent.glob("TMP-*")) == []
    def must_not_compute(image, identity):
        pytest.fail("An invalid existing sidecar must not be replaced by recomputation")
    worker = QualityShadowWorker(store, compute=must_not_compute)
    try:
        assert worker.submit(ShadowJob(source, lambda: payload))
        assert worker.wait_idle()
        counters = worker.snapshot()["counters"]
        assert counters["SHADOW_RESULT_CONFLICT"] == 1
        assert counters.get("existing_reused", 0) == counters.get("published", 0) == 0
        assert target.read_bytes() == original
    finally:
        assert worker.close()
