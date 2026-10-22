"""Immutable local sidecars, published with atomic exclusive hard links."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import threading
from uuid import uuid4

from backend.quality_shadow_metrics import ALGORITHM_VERSION, SCHEMA_VERSION, ShadowResult, SourceIdentity
from backend.video_source import reject_links


_DIRECTORY_MUTEX = threading.Lock()


class ShadowStorageError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def no_duplicates(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("DUPLICATE_JSON_FIELD")
        result[name] = value
    return result


def stable_content(result):
    return result.model_dump(mode="json", exclude={"measured_at", "elapsed_ms"})


class ShadowStore:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self._mutex = threading.RLock()

    def path(self, source):
        source = SourceIdentity.model_validate(source)
        target = self.root / SCHEMA_VERSION / ALGORITHM_VERSION / source.inspection_id / f"{source.crop_sha256}.json"
        reject_links(target)
        return target

    @contextmanager
    def locked(self, source):
        with self._mutex:
            handle = None
            acquired = False
            try:
                with _DIRECTORY_MUTEX:
                    target = self.path(source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    reject_links(target)
                lock_path = target.parent / "publication.lock"
                reject_links(lock_path)
                handle = lock_path.open("a+b")
                if lock_path.stat().st_size == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                try:
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise ShadowStorageError("SHADOW_STORE_BUSY") from None
                acquired = True
                yield target
            except ShadowStorageError:
                raise
            except (OSError, ValueError, RuntimeError):
                raise ShadowStorageError("SHADOW_STORAGE_UNAVAILABLE") from None
            finally:
                if handle is not None:
                    try:
                        if acquired:
                            handle.seek(0)
                            if os.name == "nt":
                                import msvcrt
                                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                            else:
                                import fcntl
                                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    finally:
                        handle.close()

    def read(self, source):
        source = SourceIdentity.model_validate(source)
        target = self.path(source)
        if not target.exists():
            return None
        try:
            if target.stat().st_size > 262144:
                raise ValueError("OVERSIZED_SHADOW")
            document = json.loads(target.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)
            if set(document) != {"quality_observability"}:
                raise ValueError("INVALID_ENVELOPE")
            result = ShadowResult.model_validate(document["quality_observability"])
            if result.source != source:
                raise ValueError("DIFFERENT_SOURCE")
            return result
        except OSError:
            raise ShadowStorageError("SHADOW_STORAGE_UNAVAILABLE") from None
        except (ValueError, TypeError, KeyError):
            raise ShadowStorageError("SHADOW_RESULT_CONFLICT") from None

    def publish(self, result):
        result = ShadowResult.model_validate(result)
        with self.locked(result.source) as target:
            previous = self.read(result.source)
            if previous is not None:
                if stable_content(previous) != stable_content(result):
                    raise ShadowStorageError("SHADOW_RESULT_CONFLICT")
                return previous
            temporary = target.parent / f"TMP-{uuid4().hex}"
            try:
                with temporary.open("x", encoding="utf-8") as stream:
                    json.dump({"quality_observability": result.model_dump(mode="json")}, stream, ensure_ascii=False, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                reject_links(temporary)
                reject_links(target)
                try:
                    os.link(temporary, target)
                except FileExistsError:
                    previous = self.read(result.source)
                    if previous is None or stable_content(previous) != stable_content(result):
                        raise ShadowStorageError("SHADOW_RESULT_CONFLICT") from None
                    return previous
                except OSError:
                    raise ShadowStorageError("SHADOW_ATOMIC_PUBLICATION_FAILED") from None
                return result
            finally:
                temporary.unlink(missing_ok=True)
