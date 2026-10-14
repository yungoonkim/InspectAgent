"""Storage module for VisionInsight inspection records and execution logs.

Provides JSONL-based local storage implementation and an abstract storage interface
decoupled for future cloud migration (e.g. Google Cloud Storage).
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, ValidationError


# ==============================================================================
# Domain Constants & Event Codes
# ==============================================================================

class EventCode:
    """Standardized event codes for inspection lifecycle execution logs."""
    INSPECTION_STARTED = "INSPECTION_STARTED"
    IMAGE_LOADED = "IMAGE_LOADED"
    IMAGE_LOAD_FAILED = "IMAGE_LOAD_FAILED"
    ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
    INSPECTION_COMPLETED = "INSPECTION_COMPLETED"
    INSPECTION_FAILED = "INSPECTION_FAILED"
    BRIGHTNESS_LOW_WARNING = "BRIGHTNESS_LOW_WARNING"
    BRIGHTNESS_HIGH_WARNING = "BRIGHTNESS_HIGH_WARNING"


class LogLevel:
    """Log severity levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class InspectionStage:
    """Standard inspection execution stages."""
    INIT = "init"
    LOAD = "load"
    ANALYZE = "analyze"
    DECISION = "decision"
    COMPLETE = "complete"


def get_utc_now_iso() -> str:
    """Generate ISO 8601 formatted timestamp in UTC (+00:00)."""
    return datetime.now(timezone.utc).isoformat()


# ==============================================================================
# Storage Exceptions
# ==============================================================================

class StorageError(Exception):
    """Base exception for all storage related operations."""
    pass


class StorageFormatError(StorageError):
    """Raised when record data fails schema validation or serialization."""
    pass


class StorageWriteError(StorageError):
    """Raised when writing to the storage medium fails (I/O error, permissions)."""
    pass


# ==============================================================================
# Record Schemas (Pydantic Models)
# ==============================================================================

class InspectionRecord(BaseModel):
    """Inspection execution record schema for data/inspections.jsonl.

    Enforces strict separation between product defect verdict and image quality status.
    """
    model_config = ConfigDict(extra="ignore")

    inspection_id: str = Field(description="Unique collision-free inspection ID (e.g., INSP-000001)")
    product_id: str = Field(description="Product identifier (e.g., ABCD1541)")
    timestamp: str = Field(default_factory=get_utc_now_iso, description="UTC ISO 8601 timestamp")
    image_id: str = Field(description="Neutral image identifier (e.g., IMG-BOTTLE-0001)")
    result: str = Field(
        default="UNKNOWN",
        description="Product defect classification: UNKNOWN | OK | NG",
    )
    image_quality_status: str = Field(
        description="Environmental acquisition quality: NORMAL | WARNING_LOW_BRIGHTNESS | WARNING_HIGH_BRIGHTNESS",
    )
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Image analysis metrics including brightness mean, std, min, max, width, height",
    )
    status: str = Field(
        default="COMPLETED",
        description="Execution workflow status: COMPLETED | FAILED",
    )


class InspectionLogRecord(BaseModel):
    """Execution event log schema for data/inspection_logs.jsonl.

    Connected with inspection records strictly via inspection_id.
    """
    model_config = ConfigDict(extra="ignore")

    timestamp: str = Field(default_factory=get_utc_now_iso, description="UTC ISO 8601 timestamp")
    inspection_id: str = Field(description="Associated inspection ID")
    level: str = Field(description="Log level: DEBUG | INFO | WARN | ERROR")
    stage: str = Field(description="Execution stage: init | load | analyze | decision | complete")
    event_code: str = Field(description="Machine-readable event identifier code")
    message: str = Field(description="Human-readable event description")
    metrics: Optional[Dict[str, Any]] = Field(default=None, description="Optional measurement metrics")
    source: str = Field(default="vision", description="Component origin: vision | storage | api")


# ==============================================================================
# Storage Interface (Abstract Base Class)
# ==============================================================================

class InspectionStorageBase(ABC):
    """Abstract interface defining storage contract for inspections and event logs.

    Enables drop-in replacement with cloud object storage (e.g. Cloud Storage)
    without altering business or Agent logic.
    """

    @abstractmethod
    def save_inspection(self, record: Union[InspectionRecord, Dict[str, Any]]) -> InspectionRecord:
        """Validate and append an inspection record."""
        pass

    @abstractmethod
    def save_log(self, log_record: Union[InspectionLogRecord, Dict[str, Any]]) -> InspectionLogRecord:
        """Validate and append an execution event log."""
        pass

    @abstractmethod
    def save_logs(self, log_records: List[Union[InspectionLogRecord, Dict[str, Any]]]) -> List[InspectionLogRecord]:
        """Validate and append multiple execution event logs atomically."""
        pass

    @abstractmethod
    def get_inspection(self, inspection_id: str) -> Optional[InspectionRecord]:
        """Retrieve an inspection record by its unique inspection_id."""
        pass

    @abstractmethod
    def get_logs(self, inspection_id: str) -> List[InspectionLogRecord]:
        """Retrieve all execution event logs for a given inspection_id sorted chronologically."""
        pass

    @abstractmethod
    def list_inspections(self, limit: int = 100, product_id: Optional[str] = None) -> List[InspectionRecord]:
        """List recent inspection records, optionally filtered by product_id."""
        pass


# ==============================================================================
# Local JSONL Storage Implementation
# ==============================================================================

class JsonlInspectionStorage(InspectionStorageBase):
    """Thread-safe local filesystem JSONL implementation.

    Guarantees:
    1. Each line is a single, valid, self-contained JSON object terminated with '\\n'.
    2. Strict Pydantic validation before saving; raises StorageFormatError on invalid structure.
    3. Thread lock prevents race conditions or interleaved log writes.
    4. Handles file creation and directory existence automatically.
    """

    def __init__(self, inspections_path: Path, logs_path: Path):
        self._inspections_path = Path(inspections_path).resolve()
        self._logs_path = Path(logs_path).resolve()
        self._lock = threading.Lock()
        self._ensure_storage_files()

    def _ensure_storage_files(self) -> None:
        """Create target directories and touch files if they do not exist."""
        try:
            self._inspections_path.parent.mkdir(parents=True, exist_ok=True)
            self._logs_path.parent.mkdir(parents=True, exist_ok=True)
            if not self._inspections_path.exists():
                self._inspections_path.touch()
            if not self._logs_path.exists():
                self._logs_path.touch()
        except OSError as e:
            raise StorageWriteError(f"Failed to initialize storage paths: {e}") from e

    def save_inspection(self, record: Union[InspectionRecord, Dict[str, Any]]) -> InspectionRecord:
        """Validate and append an inspection record to inspections.jsonl."""
        if isinstance(record, dict):
            try:
                validated_record = InspectionRecord.model_validate(record)
            except ValidationError as err:
                raise StorageFormatError(f"Invalid inspection record format: {err}") from err
        elif isinstance(record, InspectionRecord):
            validated_record = record
        else:
            raise StorageFormatError(f"Unsupported record type: {type(record)}")

        line = validated_record.model_dump_json() + "\n"

        with self._lock:
            try:
                with open(self._inspections_path, "a", encoding="utf-8") as f:
                    f.write(line)
            except OSError as err:
                raise StorageWriteError(f"Failed to append to {self._inspections_path}: {err}") from err

        return validated_record

    def save_log(self, log_record: Union[InspectionLogRecord, Dict[str, Any]]) -> InspectionLogRecord:
        """Validate and append an execution event log to inspection_logs.jsonl."""
        if isinstance(log_record, dict):
            try:
                validated_log = InspectionLogRecord.model_validate(log_record)
            except ValidationError as err:
                raise StorageFormatError(f"Invalid inspection log format: {err}") from err
        elif isinstance(log_record, InspectionLogRecord):
            validated_log = log_record
        else:
            raise StorageFormatError(f"Unsupported log type: {type(log_record)}")

        line = validated_log.model_dump_json() + "\n"

        with self._lock:
            try:
                with open(self._logs_path, "a", encoding="utf-8") as f:
                    f.write(line)
            except OSError as err:
                raise StorageWriteError(f"Failed to append to {self._logs_path}: {err}") from err

        return validated_log

    def save_logs(self, log_records: List[Union[InspectionLogRecord, Dict[str, Any]]]) -> List[InspectionLogRecord]:
        """Validate all logs and append them in a single file operation under lock."""
        validated_logs: List[InspectionLogRecord] = []
        lines_to_write: List[str] = []

        for item in log_records:
            if isinstance(item, dict):
                try:
                    val = InspectionLogRecord.model_validate(item)
                except ValidationError as err:
                    raise StorageFormatError(f"Invalid log format in batch: {err}") from err
            elif isinstance(item, InspectionLogRecord):
                val = item
            else:
                raise StorageFormatError(f"Unsupported item type in batch: {type(item)}")

            validated_logs.append(val)
            lines_to_write.append(val.model_dump_json() + "\n")

        with self._lock:
            try:
                with open(self._logs_path, "a", encoding="utf-8") as f:
                    f.writelines(lines_to_write)
            except OSError as err:
                raise StorageWriteError(f"Failed to append logs batch to {self._logs_path}: {err}") from err

        return validated_logs

    def get_inspection(self, inspection_id: str) -> Optional[InspectionRecord]:
        """Retrieve an inspection record by its inspection_id.

        Scans the JSONL file backwards (latest record takes precedence in case of updates).
        """
        if not self._inspections_path.exists():
            return None

        with self._lock:
            try:
                with open(self._inspections_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError as err:
                raise StorageError(f"Failed to read from {self._inspections_path}: {err}") from err

        for line in reversed(lines):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                data = json.loads(line_str)
                if data.get("inspection_id") == inspection_id:
                    return InspectionRecord.model_validate(data)
            except (json.JSONDecodeError, ValidationError):
                # Skip corrupted lines gracefully
                continue

        return None

    def get_logs(self, inspection_id: str) -> List[InspectionLogRecord]:
        """Retrieve all execution event logs for a given inspection_id sorted chronologically."""
        if not self._logs_path.exists():
            return []

        matched_logs: List[InspectionLogRecord] = []

        with self._lock:
            try:
                with open(self._logs_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError as err:
                raise StorageError(f"Failed to read from {self._logs_path}: {err}") from err

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                data = json.loads(line_str)
                if data.get("inspection_id") == inspection_id:
                    matched_logs.append(InspectionLogRecord.model_validate(data))
            except (json.JSONDecodeError, ValidationError):
                continue

        return matched_logs

    def list_inspections(self, limit: int = 100, product_id: Optional[str] = None) -> List[InspectionRecord]:
        """List up to limit recent inspection records, optionally filtered by product_id."""
        if not self._inspections_path.exists():
            return []

        results: List[InspectionRecord] = []

        with self._lock:
            try:
                with open(self._inspections_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError as err:
                raise StorageError(f"Failed to read from {self._inspections_path}: {err}") from err

        for line in reversed(lines):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                data = json.loads(line_str)
                if product_id is None or data.get("product_id") == product_id:
                    results.append(InspectionRecord.model_validate(data))
                    if len(results) >= limit:
                        break
            except (json.JSONDecodeError, ValidationError):
                continue

        return results


# ==============================================================================
# Singleton Factory for Application Lifecycle
# ==============================================================================

_storage_instance: Optional[InspectionStorageBase] = None
_storage_lock = threading.Lock()


def get_inspection_storage(
    inspections_path: Optional[Path] = None,
    logs_path: Optional[Path] = None,
    force_new: bool = False,
) -> InspectionStorageBase:
    """Retrieve or initialize the inspection storage singleton instance.

    Args:
        inspections_path: Optional override path for data/inspections.jsonl.
        logs_path: Optional override path for data/inspection_logs.jsonl.
        force_new: If True, forces creating a new storage instance (useful for test isolation).
    """
    global _storage_instance
    with _storage_lock:
        if _storage_instance is None or force_new:
            from backend.config import get_settings
            settings = get_settings()
            insp_p = inspections_path or settings.absolute_inspections_path
            log_p = logs_path or settings.absolute_inspection_logs_path
            storage = JsonlInspectionStorage(inspections_path=insp_p, logs_path=log_p)
            if not force_new:
                _storage_instance = storage
            return storage
        return _storage_instance
