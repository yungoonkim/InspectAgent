"""Real filesystem publication in isolated temporary directories only."""

from concurrent.futures import ThreadPoolExecutor
import errno
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from backend.quality_shadow_metrics import ShadowResult, measure_png
from backend.quality_shadow_store import ShadowStorageError, ShadowStore
from tests.quality_shadow_helpers import synthetic_input


def example():
    payload, source = synthetic_input()
    return ShadowResult.model_validate(measure_png(payload, source))


def test_read_only_lookup_does_not_create_directory(tmp_path):
    store = ShadowStore(tmp_path / "not-created")
    assert store.read(example().source) is None
    assert not store.root.exists()


def test_publication_is_immutable_idempotent_and_fully_validated(tmp_path):
    store = ShadowStore(tmp_path / "sidecars")
    first = example()
    store.publish(first)
    path = store.path(first.source)
    before = path.read_bytes()
    assert store.publish(example()).metrics == first.metrics
    assert path.read_bytes() == before
    assert store.read(first.source).source == first.source
    assert list(path.parent.glob("TMP-*")) == []
    assert json.loads(before)["quality_observability"]["source"]["crop_sha256"] == first.source.crop_sha256


def test_different_content_for_same_key_is_conflict_not_replacement(tmp_path):
    store = ShadowStore(tmp_path)
    first = example()
    store.publish(first)
    before = store.path(first.source).read_bytes()
    modified = first.model_dump(mode="json")
    modified["metrics"]["p10_gv"]["value"] += 1
    with pytest.raises(ShadowStorageError, match="SHADOW_RESULT_CONFLICT"):
        store.publish(ShadowResult.model_validate(modified))
    assert store.path(first.source).read_bytes() == before


@pytest.mark.parametrize("corruption", ["{", '{"quality_observability":NaN}', '{"quality_observability":{},"quality_observability":{}}'])
def test_corrupt_existing_files_are_preserved(tmp_path, corruption):
    store = ShadowStore(tmp_path)
    first = example()
    target = store.path(first.source)
    target.parent.mkdir(parents=True)
    target.write_text(corruption, encoding="utf-8")
    with pytest.raises(ShadowStorageError, match="SHADOW_RESULT_CONFLICT"):
        store.publish(first)
    assert target.read_text(encoding="utf-8") == corruption


@pytest.mark.parametrize("failure", ["partial_json", "permission", "disk", "unsupported_link"])
def test_failed_writes_never_publish_partial_json(tmp_path, monkeypatch, failure):
    import backend.quality_shadow_store as module

    store = ShadowStore(tmp_path)
    first = example()
    if failure == "partial_json":
        def partial(document, stream, **kwargs):
            stream.write('{"quality_observability":')
            raise OSError(errno.ENOSPC, "synthetic full disk")
        monkeypatch.setattr(module.json, "dump", partial)
    elif failure == "permission":
        original = Path.open
        def denied(path, *args, **kwargs):
            if path.name.startswith("TMP-"):
                raise PermissionError("synthetic denied")
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, "open", denied)
    elif failure == "disk":
        monkeypatch.setattr(module.os, "fsync", lambda descriptor: (_ for unused in ()).throw(OSError(errno.ENOSPC, "synthetic disk full")))
    else:
        monkeypatch.setattr(module.os, "link", lambda *args: (_ for unused in ()).throw(OSError(errno.ENOTSUP, "synthetic unsupported")))
    with pytest.raises(ShadowStorageError):
        store.publish(first)
    assert not store.path(first.source).exists()
    assert list(store.path(first.source).parent.glob("TMP-*")) == []


def test_actual_exclusive_hard_link_publication_does_not_replace_existing(tmp_path):
    source = tmp_path / "complete.tmp"
    target = tmp_path / "final.json"
    source.write_bytes(b"complete")
    os.link(source, target)
    assert os.path.samefile(source, target)
    other = tmp_path / "different.tmp"
    other.write_bytes(b"different")
    with pytest.raises(FileExistsError):
        os.link(other, target)
    assert target.read_bytes() == b"complete"


def test_same_instance_threads_publish_one_result(tmp_path):
    store = ShadowStore(tmp_path)
    first = example()
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda number: store.publish(first), range(12)))
    assert all(result.source == first.source for result in results)
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_process_os_lock_and_later_publication(tmp_path):
    store = ShadowStore(tmp_path / "sidecars")
    first = example()
    fixture = tmp_path / "synthetic-result.json"
    fixture.write_text(first.model_dump_json(), encoding="utf-8")
    code = """
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from backend.quality_shadow_metrics import ShadowResult
from backend.quality_shadow_store import ShadowStore,ShadowStorageError
document=ShadowResult.model_validate_json(Path(sys.argv[3]).read_text(encoding='utf-8'))
try:
    ShadowStore(sys.argv[2]).publish(document)
    print('PUBLISHED')
except ShadowStorageError as error:
    print(error.code)
"""
    command = [sys.executable, "-B", "-c", code, str(Path(__file__).resolve().parents[1]), str(store.root), str(fixture)]
    with store.locked(first.source):
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=True)
        assert result.stdout.strip() == "SHADOW_STORE_BUSY", result.stderr
    result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=True)
    assert result.stdout.strip() == "PUBLISHED", result.stderr
    before = store.path(first.source).read_bytes()
    assert store.publish(first).source == first.source
    assert store.path(first.source).read_bytes() == before


def test_wrong_image_identity_cannot_reuse_same_inspection_hash_path(tmp_path):
    store = ShadowStore(tmp_path)
    first = example()
    store.publish(first)
    wrong = first.source.model_copy(update={"image_id": "IMG-GRAB-" + "e" * 32})
    with pytest.raises(ShadowStorageError, match="SHADOW_RESULT_CONFLICT"):
        store.read(wrong)


def test_two_independent_store_instances_publish_different_ids_concurrently(tmp_path):
    first_payload, first_source = synthetic_input(990001)
    second_payload, second_source = synthetic_input(990002)
    documents = [ShadowResult.model_validate(measure_png(first_payload, first_source)),
                 ShadowResult.model_validate(measure_png(second_payload, second_source))]
    def publish(document):
        return ShadowStore(tmp_path).publish(document)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(publish, documents))
    assert {result.source.inspection_id for result in results} == {first_source.inspection_id, second_source.inspection_id}
    assert len(list(tmp_path.rglob("*.json"))) == 2


@pytest.mark.parametrize("different_content", [False, True])
def test_target_created_during_publication_is_not_overwritten(tmp_path, monkeypatch, different_content):
    store = ShadowStore(tmp_path)
    first = example()
    original = os.link
    published = []
    def competing(temporary, target):
        document = json.loads(temporary.read_text(encoding="utf-8"))
        if different_content:
            document["quality_observability"]["metrics"]["p10_gv"]["value"] += 1
        target.write_text(json.dumps(document), encoding="utf-8")
        published.append(target.read_bytes())
        original(temporary, target)
    monkeypatch.setattr(os, "link", competing)
    if different_content:
        with pytest.raises(ShadowStorageError, match="SHADOW_RESULT_CONFLICT"):
            store.publish(first)
    else:
        assert store.publish(first).source == first.source
    assert store.path(first.source).read_bytes() == published[0]
