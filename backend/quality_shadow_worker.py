"""One daemon calculation thread and one pending slot; no durable job queue."""

from collections import Counter
from dataclasses import dataclass
import logging
import threading
from time import perf_counter
from typing import Callable

from backend.quality_shadow_metrics import SourceIdentity, failed_result, measure_pixels, validate_png
from backend.quality_shadow_store import ShadowStorageError, ShadowStore


logger = logging.getLogger("vision_insight.quality_shadow")


def report_shadow_failure(code):
    try:
        logger.warning(code)
    except Exception:
        pass


@dataclass(frozen=True)
class ShadowJob:
    source: SourceIdentity
    load: Callable[[], bytes]


class QualityShadowWorker:
    def __init__(self, store, *, compute=measure_pixels):
        self.store = store
        self.compute = compute
        self._condition = threading.Condition()
        self._active = None
        self._pending = None
        self._running = False
        self._closed = False
        self._keys = set()
        self._counters = Counter()
        self._thread = threading.Thread(target=self._run, name="quality-shadow", daemon=True)
        self._thread.start()

    def observe(self, code):
        with self._condition:
            self._counters[code] += 1

    def snapshot(self):
        with self._condition:
            return {"counters": dict(self._counters), "active": int(self._active is not None),
                    "pending": int(self._pending is not None), "closed": self._closed, "alive": self._thread.is_alive()}

    def submit(self, job):
        key = (job.source.inspection_id, job.source.image_id, job.source.crop_sha256)
        with self._condition:
            if self._closed:
                self._counters["closed_rejected"] += 1
                return False
            if key in self._keys:
                self._counters["duplicate"] += 1
                return False
            if self._active is not None and self._pending is not None:
                self._counters["queue_full"] += 1
                return False
            self._keys.add(key)
            if self._active is None:
                self._active = job
            else:
                self._pending = job
            self._counters["accepted"] += 1
            self._condition.notify_all()
            return True

    def wait_idle(self, timeout=5):
        with self._condition:
            return self._condition.wait_for(lambda: self._active is None and self._pending is None, timeout)

    def _execute(self, job):
        pixels = validate_png(job.load(), job.source)
        previous = self.store.read(job.source)
        if previous is not None:
            self.observe("existing_reused")
            return
        started = perf_counter()
        try:
            result = self.compute(pixels, job.source)
        except Exception:
            self.observe("computation_failed")
            result = failed_result(job.source, (perf_counter() - started) * 1000)
        with self._condition:
            if self._closed:
                self._counters["shutdown_discarded"] += 1
                return
        self.store.publish(result)
        self.observe("published")

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._active is not None or self._closed)
                if self._active is None:
                    return
                job = self._active
                self._running = True
            try:
                self._execute(job)
            except ShadowStorageError as error:
                self.observe(error.code)
            except Exception:
                self.observe("job_failed")
            finally:
                with self._condition:
                    self._keys.discard((job.source.inspection_id, job.source.image_id, job.source.crop_sha256))
                    self._active = self._pending
                    self._pending = None
                    self._running = False
                    self._condition.notify_all()

    def close(self, timeout=1):
        with self._condition:
            self._closed = True
            if self._pending is not None:
                self._keys.discard((self._pending.source.inspection_id, self._pending.source.image_id, self._pending.source.crop_sha256))
                self._pending = None
                self._counters["shutdown_dropped"] += 1
            if self._active is not None and not self._running:
                self._keys.discard((self._active.source.inspection_id, self._active.source.image_id, self._active.source.crop_sha256))
                self._active = None
                self._counters["shutdown_dropped"] += 1
            self._condition.notify_all()
        self._thread.join(timeout)
        if self._thread.is_alive():
            self.observe("shutdown_unfinished")
            return False
        return True


def create_quality_shadow_worker(settings):
    if not getattr(settings, "QUALITY_SHADOW_ENABLED", False):
        return None
    try:
        return QualityShadowWorker(ShadowStore(settings.absolute_output_path / "quality_shadow_metrics"))
    except Exception:
        report_shadow_failure("QUALITY_SHADOW_START_FAILED")
        return None
