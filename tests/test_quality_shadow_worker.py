"""Bounded worker failures and shutdown; all images and files are synthetic."""

import json
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from backend.quality_shadow_metrics import measure_pixels
from backend.quality_shadow_store import ShadowStorageError, ShadowStore
from backend.quality_shadow_worker import QualityShadowWorker, ShadowJob, create_quality_shadow_worker
from tests.quality_shadow_helpers import synthetic_input


def job(number=990001):
    payload, source = synthetic_input(number)
    return ShadowJob(source, lambda: payload)


def test_off_starts_no_thread_and_creates_no_sidecar_root(tmp_path, monkeypatch):
    import backend.quality_shadow_worker as module

    monkeypatch.setattr(module, "QualityShadowWorker", lambda *args: pytest.fail("OFF must not construct a worker"))
    assert create_quality_shadow_worker(SimpleNamespace(QUALITY_SHADOW_ENABLED=False, absolute_output_path=tmp_path)) is None
    assert not list(tmp_path.iterdir())


def test_one_active_one_pending_third_rejected_duplicate_rejected(tmp_path):
    entered, release = threading.Event(), threading.Event()
    def blocked(image, source):
        entered.set()
        assert release.wait(5)
        return measure_pixels(image, source)
    worker = QualityShadowWorker(ShadowStore(tmp_path), compute=blocked)
    first, second, third = job(), job(990002), job(990003)
    try:
        assert worker.submit(first)
        assert entered.wait(3)
        assert not worker.submit(first)
        assert worker.submit(second)
        assert not worker.submit(third)
        assert worker.snapshot()["active"] == worker.snapshot()["pending"] == 1
        release.set()
        assert worker.wait_idle()
        assert worker.snapshot()["counters"]["published"] == 2
        assert worker.snapshot()["counters"]["queue_full"] == 1
        for expected in (first, second):
            assert worker.store.read(expected.source).source == expected.source
        assert worker.store.read(third.source) is None
    finally:
        release.set()
        worker.close()


def test_existing_result_is_reused_without_recalculation(tmp_path):
    worker = QualityShadowWorker(ShadowStore(tmp_path))
    first = job()
    try:
        assert worker.submit(first) and worker.wait_idle()
        original = worker.store.path(first.source).read_bytes()
        worker.compute = lambda *args: pytest.fail("must reuse immutable result")
        assert worker.submit(first) and worker.wait_idle()
        assert worker.snapshot()["counters"]["existing_reused"] == 1
        assert worker.store.path(first.source).read_bytes() == original
    finally:
        worker.close()


def test_computation_exception_is_an_explicit_failed_result(tmp_path):
    def broken(image, source):
        raise RuntimeError("private values must not be logged")
    worker = QualityShadowWorker(ShadowStore(tmp_path), compute=broken)
    first = job()
    try:
        assert worker.submit(first) and worker.wait_idle()
        result = worker.store.read(first.source)
        assert result.status == "NOT_MEASURED"
        assert result.elapsed_ms > 0
        assert all(metric.value is None and metric.reason == "COMPUTATION_FAILED" for metric in result.metrics.values())
        assert "private values" not in result.model_dump_json()
    finally:
        worker.close()


def test_invalid_crop_and_storage_failure_are_counted_without_retry(tmp_path, monkeypatch):
    worker = QualityShadowWorker(ShadowStore(tmp_path))
    first = job()
    try:
        assert worker.submit(ShadowJob(first.source, lambda: b"wrong crop")) and worker.wait_idle()
        assert worker.store.read(first.source) is None
        assert worker.snapshot()["counters"]["job_failed"] == 1
        calls = []
        def denied(result):
            calls.append(result)
            raise ShadowStorageError("SHADOW_STORAGE_UNAVAILABLE")
        monkeypatch.setattr(worker.store, "publish", denied)
        assert worker.submit(first) and worker.wait_idle()
        assert len(calls) == 1
        assert worker.snapshot()["counters"]["SHADOW_STORAGE_UNAVAILABLE"] == 1
    finally:
        worker.close()


def test_shutdown_drops_pending_and_reports_unfinished_native_work(tmp_path):
    entered, release = threading.Event(), threading.Event()
    def blocked(image, source):
        entered.set()
        assert release.wait(5)
        return measure_pixels(image, source)
    worker = QualityShadowWorker(ShadowStore(tmp_path), compute=blocked)
    first, second = job(), job(990002)
    try:
        assert worker.submit(first) and entered.wait(3)
        assert worker.submit(second)
        assert not worker.close(timeout=0.01)
        assert not worker.submit(job(990003))
        assert worker.snapshot()["counters"]["shutdown_dropped"] == 1
        assert worker.snapshot()["counters"]["shutdown_unfinished"] == 1
        release.set()
        assert worker.wait_idle()
        assert worker.close()
        assert worker.store.read(first.source) is None
        assert worker.store.read(second.source) is None
    finally:
        release.set()
        worker.close()


def test_process_exit_demonstrates_non_durable_queue_without_operating_processes(tmp_path):
    code = """
import os,sys,threading
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from backend.quality_shadow_worker import QualityShadowWorker,ShadowJob
from backend.quality_shadow_store import ShadowStore
from tests.quality_shadow_helpers import synthetic_input
entered=threading.Event()
def blocked(image,source):
    entered.set()
    threading.Event().wait(60)
worker=QualityShadowWorker(ShadowStore(Path(sys.argv[2])/'sidecars'),compute=blocked)
payload,source=synthetic_input()
assert worker.submit(ShadowJob(source,lambda:payload))
assert entered.wait(5)
Path(sys.argv[2],'accepted.txt').write_text('SYNTHETIC_QUEUE_ACCEPTED',encoding='utf-8')
os._exit(0)
"""
    result = subprocess.run([sys.executable, "-B", "-c", code, str(Path(__file__).resolve().parents[1]), str(tmp_path)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "accepted.txt").exists()
    assert not list((tmp_path / "sidecars").rglob("*.json"))


def test_worker_start_failure_is_fail_open_only_for_shadow(tmp_path, monkeypatch):
    import backend.quality_shadow_worker as module

    monkeypatch.setattr(module, "QualityShadowWorker", lambda *args: (_ for unused in ()).throw(RuntimeError("secret")))
    assert module.create_quality_shadow_worker(SimpleNamespace(QUALITY_SHADOW_ENABLED=True, absolute_output_path=tmp_path)) is None
