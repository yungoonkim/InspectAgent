"""Immutable local publication of validated Agent reports."""

import json
import os
from pathlib import Path
import re
from uuid import uuid4

from fastapi import Depends

from backend.config import get_settings
from backend.video_source import reject_links


class ReportStoreError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class AgentReportStore:
    def __init__(self, root):
        self.root = Path(root)

    def path(self, identifier):
        if not isinstance(identifier, str) or re.fullmatch(r"INSP-[0-9]{6,12}", identifier) is None:
            raise ReportStoreError("INVALID_ARGUMENT")
        path = self.root / f"{identifier}.json"
        try:
            reject_links(path)
        except Exception:
            raise ReportStoreError("AGENT_REPORT_STORAGE_FAILED") from None
        return path

    def ensure_absent(self, identifier):
        try:
            if self.path(identifier).exists():
                raise ReportStoreError("AGENT_REPORT_EXISTS")
        except OSError:
            raise ReportStoreError("AGENT_REPORT_STORAGE_FAILED") from None

    def read(self, identifier):
        path = self.path(identifier)
        try:
            if not path.exists():
                return None
            if path.stat().st_size > 4 * 1024 * 1024:
                raise ValueError("Report too large")
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("inspection_id") != identifier:
                raise ValueError("Report identity mismatch")
            return value
        except (OSError, ValueError):
            raise ReportStoreError("AGENT_REPORT_STORAGE_FAILED") from None

    def save(self, report):
        destination = self.path(report["inspection_id"])
        temporary = self.root / f".report-{uuid4().hex}.tmp"
        try:
            self.ensure_absent(report["inspection_id"])
            payload = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)
            self.root.mkdir(parents=True, exist_ok=True)
            reject_links(self.root)
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, destination)
        except FileExistsError:
            raise ReportStoreError("AGENT_REPORT_EXISTS") from None
        except ReportStoreError:
            raise
        except Exception:
            raise ReportStoreError("AGENT_REPORT_STORAGE_FAILED") from None
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                raise ReportStoreError("AGENT_REPORT_STORAGE_FAILED") from None


def get_agent_report_store(settings=Depends(get_settings)):
    return AgentReportStore(Path(settings.absolute_output_path) / "agent_reports")
