"""Local, fail-closed reinspection history separate from inspection JSONL."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator
from typing import Literal

from backend.video_source import reject_links


JUDGE_ASSISTED_POLICY = "judge-assisted-v1"


class ReinspectionError(Exception):
    def __init__(self, status_code, code):
        self.status_code = status_code
        self.code = code
        super().__init__(code)


class ManualReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: StrictInt = Field(ge=1)
    request_id: StrictStr = Field(pattern=r"^[0-9a-f]{32}$")
    result: Literal["MANUAL_OK", "MANUAL_NG", "HOLD"]
    operator_id: StrictStr = Field(min_length=1, max_length=64)
    reason: StrictStr = Field(min_length=1, max_length=1000)

    @field_validator("operator_id", "reason")
    @classmethod
    def meaningful_text(cls, value):
        if not value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("Nonempty printable text required")
        return value.strip()


def now():
    return datetime.now(timezone.utc).isoformat()


def completed(record):
    return (record.status == "COMPLETED" and record.defect_detection_status == "COMPLETED"
            and record.final_result in {"OK", "NG", "REINSPECT"}
            and record.anomaly_score is not None and math.isfinite(record.anomaly_score))


class ReinspectionStore:
    def __init__(self, root):
        self.root = Path(root).absolute()

    @contextmanager
    def locked(self):
        handle = None
        acquired = False
        try:
            reject_links(self.root)
            self.root.mkdir(parents=True, exist_ok=True)
            lock_path = self.root / "workflow.lock"
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
                raise ReinspectionError(409, "REINSPECTION_BUSY") from None
            acquired = True
            yield
        except (OSError, ValueError, RuntimeError):
            raise ReinspectionError(503, "REINSPECTION_STORAGE_UNAVAILABLE") from None
        finally:
            if handle is not None:
                if acquired:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()

    def _read(self):
        path = self.root / "state.json"
        reject_links(path)
        if not path.exists():
            return {"schema_version": 1, "groups": {}, "captures": {}, "requests": {}}
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if (state["schema_version"] != 1
                    or not all(isinstance(state[key], dict) for key in ("groups", "captures", "requests"))):
                raise ValueError("Invalid history")
            return state
        except (ValueError, KeyError, TypeError):
            raise ReinspectionError(503, "REINSPECTION_STORAGE_UNAVAILABLE") from None

    def _write(self, state):
        target = self.root / "state.json"
        reject_links(target)
        temporary = self.root / f"TMP-{uuid4().hex}"
        try:
            with temporary.open("x", encoding="utf-8") as output:
                json.dump(state, output, ensure_ascii=False, allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
            for attempt in range(4):
                try:
                    os.replace(temporary, target)
                    break
                except PermissionError as error:
                    if os.name != "nt" or getattr(error, "winerror", None) not in {5, 32, 33} or attempt == 3:
                        raise
                    time.sleep(0.02 * (attempt + 1))
        finally:
            temporary.unlink(missing_ok=True)

    def _group(self, state, identifier, owner):
        if re.fullmatch(r"RIG-[0-9a-f]{32}", identifier or "") is None:
            raise ReinspectionError(404, "REINSPECTION_GROUP_NOT_FOUND")
        group = state["groups"].get(identifier)
        if group is None or not secrets.compare_digest(group["owner"], owner):
            raise ReinspectionError(404, "REINSPECTION_GROUP_NOT_FOUND")
        self._judge_assisted(group)
        return group

    @staticmethod
    def _judge_assisted(group):
        if "workflow_policy" not in group:
            return False
        if group["workflow_policy"] != JUDGE_ASSISTED_POLICY:
            raise ReinspectionError(503, "REINSPECTION_POLICY_UNSUPPORTED")
        return True

    @staticmethod
    def public(group):
        return {key: value for key, value in group.items() if key != "owner"}

    def get(self, identifier, owner):
        with self.locked():
            return self.public(self._group(self._read(), identifier, owner))

    def for_capture(self, capture_id, owner):
        if re.fullmatch(r"CAP-[0-9a-f]{32}", capture_id or "") is None:
            raise ReinspectionError(404, "REINSPECTION_GROUP_NOT_FOUND")
        with self.locked():
            state = self._read()
            claim = state["captures"].get(capture_id)
            if claim is None or not secrets.compare_digest(claim["owner"], owner):
                raise ReinspectionError(404, "REINSPECTION_GROUP_NOT_FOUND")
            return self.public(self._group(state, claim["group_id"], owner))

    def execute(self, owner, capture_id, payload, metadata, storage, operation, *, judge_assisted=False):
        with self.locked():
            state = self._read()
            fingerprint = hashlib.sha256(json.dumps({"product_id": payload.product_id,
                "source_revision": payload.source_revision, "roi": payload.roi.model_dump()},
                sort_keys=True).encode()).hexdigest()
            request_key = f"{owner}:{payload.request_id}" if payload.request_id else None
            if request_key in state["requests"] and state["requests"][request_key] != capture_id:
                raise ReinspectionError(409, "IDEMPOTENCY_CONFLICT")
            claim = state["captures"].get(capture_id)
            if claim:
                if (claim["owner"] != owner or claim["fingerprint"] != fingerprint
                        or (payload.group_id and payload.group_id != claim["group_id"])):
                    raise ReinspectionError(409, "CAPTURE_ALREADY_USED")
                if claim["status"] != "COMMITTED":
                    raise ReinspectionError(409, "REINSPECTION_RECOVERY_REQUIRED")
                self._group(state, claim["group_id"], owner)
                record = storage.get_inspection(claim["inspection_id"])
                if record is None:
                    raise ReinspectionError(503, "REINSPECTION_RECORD_MISSING")
                return record
            new_group = payload.group_id is None
            if new_group:
                identifier = f"RIG-{uuid4().hex}"
                group = {"group_id": identifier, "owner": owner, "product_id": payload.product_id,
                    "video_id": metadata["video_id"], "source_revision": metadata["source_revision"],
                    "source_width": metadata["width"], "source_height": metadata["height"],
                    "max_attempts": 3, "attempt_count": 0, "remaining_attempts": 3,
                    "version": 0, "status": "RETRY_ALLOWED", "first_inspection_id": None,
                    "current_inspection_id": None, "attempts": [], "failed_attempts": [], "manual_reviews": [],
                    "created_at": now(), "updated_at": now()}
                if judge_assisted is True:
                    group.update(workflow_policy=JUDGE_ASSISTED_POLICY, max_attempts=None,
                        remaining_attempts=None, status="INSPECTION_PENDING")
                state["groups"][identifier] = group
            else:
                group = self._group(state, payload.group_id, owner)
                identifier = group["group_id"]
                assisted = self._judge_assisted(group)
                if (assisted and (group["status"] != "INSPECTION_FAILED" or group["attempts"]
                        or group["current_inspection_id"] is not None)):
                    raise ReinspectionError(409, "REINSPECTION_GROUP_CLOSED")
                if not assisted and (group["status"] != "RETRY_ALLOWED" or group["attempt_count"] >= 3):
                    raise ReinspectionError(409, "REINSPECTION_GROUP_CLOSED")
                if ((not assisted and not payload.same_product_confirmed)
                        or payload.parent_inspection_id != group["current_inspection_id"]
                        or payload.expected_version != group["version"]):
                    raise ReinspectionError(409, "REINSPECTION_CONTINUITY_REQUIRED")
                if (payload.product_id != group["product_id"] or metadata["video_id"] != group["video_id"]
                        or metadata["source_revision"] != group["source_revision"]
                        or metadata["width"] != group["source_width"] or metadata["height"] != group["source_height"]):
                    raise ReinspectionError(409, "REINSPECTION_SOURCE_MISMATCH")
                previous_attempts = [] if assisted else [*group["attempts"], *group["failed_attempts"]]
                for previous in previous_attempts:
                    source = previous["input_provenance"]
                    if (source["frame_index"] == metadata["frame_index"]
                            or source["capture_sha256"] == metadata.get("capture_sha256")):
                        raise ReinspectionError(409, "REINSPECTION_SAME_RECORDED_IMAGE")
            assisted = self._judge_assisted(group)
            previous_status = group["status"]
            context = {"group_id": identifier, "parent_inspection_id": group["current_inspection_id"],
                       "attempt_number": group["attempt_count"] + 1,
                       "max_attempts": None if assisted else 3, "started": False}
            state["captures"][capture_id] = {"owner": owner, "fingerprint": fingerprint,
                "group_id": identifier, "status": "RESERVED"}
            if request_key:
                state["requests"][request_key] = capture_id
            group["status"] = "RECOVERY_REQUIRED"
            self._write(state)
            try:
                record = operation(context)
                saved = storage.get_inspection(record.inspection_id)
                logs = storage.get_logs(record.inspection_id)
                if saved is None or not any(log.event_code in {"INSPECTION_COMPLETED", "INSPECTION_FAILED"} for log in logs):
                    raise ReinspectionError(503, "REINSPECTION_COMMIT_UNCONFIRMED")
                entry = {"inspection_id": saved.inspection_id, "parent_inspection_id": context["parent_inspection_id"],
                    "timestamp": saved.timestamp, "image_id": saved.image_id, "product_id": saved.product_id,
                    "anomaly_score": saved.anomaly_score, "decision_threshold": saved.decision_threshold,
                    "image_quality_status": saved.image_quality_status, "result": saved.result,
                    "final_result": saved.final_result, "final_reason_code": saved.final_reason_code,
                    "input_provenance": saved.metrics["input_provenance"],
                    "attempt_number": context["attempt_number"] if completed(saved) else None}
                if completed(saved):
                    group["attempts"].append(entry)
                    group["attempt_count"] += 1
                    group["first_inspection_id"] = group["first_inspection_id"] or saved.inspection_id
                    group["current_inspection_id"] = saved.inspection_id
                else:
                    group["failed_attempts"].append(entry)
                if assisted:
                    group["status"] = ("INSPECTION_FAILED" if not completed(saved)
                        else "COMPLETED" if saved.final_result in {"OK", "NG"} else "MANUAL_REVIEW_REQUIRED")
                else:
                    group["status"] = ("COMPLETED" if completed(saved) and saved.final_result in {"OK", "NG"}
                        else "MANUAL_REVIEW_REQUIRED" if group["attempt_count"] == 3 else "RETRY_ALLOWED")
                    group["remaining_attempts"] = 3 - group["attempt_count"] if group["status"] == "RETRY_ALLOWED" else 0
                group["version"] += 1
                group["updated_at"] = now()
                state["captures"][capture_id].update(status="COMMITTED", inspection_id=saved.inspection_id)
                self._write(state)
                return record
            except Exception:
                if not context["started"]:
                    del state["captures"][capture_id]
                    if request_key:
                        state["requests"].pop(request_key, None)
                    if new_group:
                        del state["groups"][identifier]
                    else:
                        group["status"] = previous_status
                    self._write(state)
                raise

    def _review_record(self, state, group, owner, storage, authorize_record):
        if storage is None or authorize_record is None:
            raise ReinspectionError(503, "MANUAL_REVIEW_VERIFICATION_UNAVAILABLE")
        if len(group["attempts"]) != 1:
            raise ReinspectionError(409, "MANUAL_REVIEW_NOT_ALLOWED")
        entry = group["attempts"][0]
        try:
            record = storage.get_inspection(entry["inspection_id"])
        except Exception:
            raise ReinspectionError(503, "MANUAL_REVIEW_RECORD_UNAVAILABLE") from None
        if (record is None or not completed(record) or record.final_result != "REINSPECT"
                or record.inspection_id != group["current_inspection_id"]
                or record.inspection_id != group["first_inspection_id"]
                or record.product_id != group["product_id"] or record.image_id != entry["image_id"]
                or entry["final_result"] != record.final_result
                or record.metrics.get("input_source") != "LIVEVIEW_GRAB"
                or record.metrics.get("reinspection", {}).get("group_id") != group["group_id"]
                or record.metrics.get("input_provenance") != entry["input_provenance"]):
            raise ReinspectionError(409, "MANUAL_REVIEW_SOURCE_MISMATCH")
        source = record.metrics["input_provenance"]
        claim = state["captures"].get(source["capture_id"], {})
        if (claim.get("owner") != owner or claim.get("status") != "COMMITTED"
                or claim.get("group_id") != group["group_id"] or claim.get("inspection_id") != record.inspection_id
                or source.get("video_id") != group["video_id"]
                or source.get("source_revision") != group["source_revision"]
                or source.get("source_width") != group["source_width"]
                or source.get("source_height") != group["source_height"]
                or source.get("reinspection", {}).get("group_id") != group["group_id"]):
            raise ReinspectionError(409, "MANUAL_REVIEW_SOURCE_MISMATCH")
        try:
            authorize_record(record, owner)
        except Exception:
            raise ReinspectionError(409, "MANUAL_REVIEW_INPUT_UNAVAILABLE") from None
        return record

    def review(self, identifier, owner, payload, *, storage=None, authorize_record=None):
        with self.locked():
            state = self._read()
            group = self._group(state, identifier, owner)
            assisted = self._judge_assisted(group)
            record = self._review_record(state, group, owner, storage, authorize_record) if assisted else None
            for previous in group["manual_reviews"]:
                if previous["request_id"] == payload.request_id:
                    if any(previous[key] != getattr(payload, key) for key in ("result", "operator_id", "reason")):
                        raise ReinspectionError(409, "IDEMPOTENCY_CONFLICT")
                    return self.public(group)
            if group["status"] != "MANUAL_REVIEW_REQUIRED" or (not assisted and group["attempt_count"] != 3):
                raise ReinspectionError(409, "MANUAL_REVIEW_NOT_ALLOWED")
            if payload.expected_version != group["version"]:
                raise ReinspectionError(409, "REINSPECTION_VERSION_CONFLICT")
            review = {"review_id": f"REV-{uuid4().hex}", "timestamp": now(),
                "request_id": payload.request_id, "operator_id": payload.operator_id, "reason": payload.reason,
                "result": payload.result, "authority": "DEVELOPMENT_SELF_DECLARED_NOT_AUTHENTICATED",
                "inspection_ids": [entry["inspection_id"] for entry in group["attempts"]]}
            if assisted:
                review.update(workflow_policy=JUDGE_ASSISTED_POLICY, inspection_id=record.inspection_id,
                    image_id=record.image_id, crop_sha256=record.metrics["input_provenance"]["crop_sha256"],
                    server_final_result=record.final_result)
            group["manual_reviews"].append(review)
            if payload.result != "HOLD":
                group["status"] = "MANUAL_REVIEWED"
            group["version"] += 1
            group["updated_at"] = now()
            self._write(state)
            return self.public(group)
