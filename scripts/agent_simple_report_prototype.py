"""Offline-only selection report prototype; never switches the operating Agent."""

from dataclasses import asdict, dataclass
import json
from typing import get_args

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from backend.agent.schemas import CauseCode, CauseSelection, CheckCode, CheckSelection, DiagnosisDraft, ObservedFact
from backend.agent.service import AgentFailure, AgentService
from backend.agent.tools import ENUM_FIELDS, NUMBER_FIELDS, SIZE_FIELDS, _number, _timestamp


class SimpleReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overall_summary: StrictStr = Field(max_length=64)
    observed_fact_refs: list[StrictStr] = Field(min_length=1, max_length=40)
    possible_causes: list[StrictStr] = Field(max_length=4)
    recommended_checks: list[StrictStr] = Field(min_length=1, max_length=8)
    limitations: list[StrictStr] = Field(max_length=6)


@dataclass(frozen=True)
class CatalogEntry:
    token: str
    evidence_id: str
    source_tool: str
    source_field: str
    observed_value: object
    source_event: object


@dataclass(frozen=True)
class EvidenceCatalog:
    inspection_id: str
    entries: tuple[CatalogEntry, ...]


def simple_output_schema():
    return {"type": "object", "properties": {
        name: {"type": "string"} if name == "overall_summary" else {"type": "array", "items": {"type": "string"}}
        for name in SimpleReport.model_fields
    }, "required": list(SimpleReport.model_fields)}


def _allowed_value(name, value):
    if value is None:
        return name in ENUM_FIELDS or name in NUMBER_FIELDS or name in SIZE_FIELDS or name in {
            "timestamp", "timestamp_status", "threshold_status", "low_threshold", "high_threshold",
        }
    if name in ENUM_FIELDS:
        return isinstance(value, str) and value in ENUM_FIELDS[name]
    if name in NUMBER_FIELDS or name in {"low_threshold", "high_threshold"}:
        return _number(value) is not None
    if name in SIZE_FIELDS:
        return type(value) is int and 0 < value <= 100000
    if name == "timestamp":
        return _timestamp(value) is not None
    if name == "timestamp_status":
        return value in {"VALID", "INVALID_OR_MISSING"} if isinstance(value, str) else False
    if name == "threshold_status":
        return value in {"RECORDED", "NOT_RECORDED"} if isinstance(value, str) else False
    return False


def _leaves(record, prefix):
    for name in sorted(record):
        value = record[name]
        if name in {"metrics", "brightness_thresholds"} and isinstance(value, dict):
            for child in sorted(value):
                if _allowed_value(child, value[child]):
                    yield f"{prefix}/{name}/{child}", value[child]
        elif _allowed_value(name, value):
            yield f"{prefix}/{name}", value


def _build_catalog(state, max_entries, max_bytes):
    if state.snapshot is None:
        raise AgentFailure("INSUFFICIENT_EVIDENCE")
    successful = {}
    for trace in state.trace:
        if trace.executed and trace.success and trace.evidence_id:
            if trace.evidence_id in successful:
                raise AgentFailure("EVIDENCE_MISMATCH")
            successful[trace.evidence_id] = trace.tool_name
    entries = []
    for identifier, (tool, document) in state.evidence.items():
        if successful.get(identifier) != tool or document.get("ok") is not True or document.get("metadata", {}).get("evidence_id") != identifier:
            raise AgentFailure("EVIDENCE_MISMATCH")
        data = document["data"]
        records = list(enumerate(data)) if isinstance(data, list) else [(None, data)]
        for index, record in records:
            if not isinstance(record, dict):
                raise AgentFailure("EVIDENCE_MISMATCH")
            event = record.get("event_code") if tool == "get_execution_logs" else None
            if event is not None and (not isinstance(event, str) or event not in ENUM_FIELDS["event_code"]):
                raise AgentFailure("EVIDENCE_MISMATCH")
            prefix = "/data" if index is None else f"/data/{index}"
            for pointer, value in _leaves(record, prefix):
                try:
                    ObservedFact(fact_id="F0001", evidence_id=identifier, source_tool=tool,
                        source_field=pointer, source_event=event, observed_value=value)
                except ValidationError:
                    raise AgentFailure("EVIDENCE_MISMATCH") from None
                entries.append(CatalogEntry(f"K{len(entries) + 1:04d}", identifier, tool, pointer, value, event))
                if len(entries) > max_entries:
                    raise AgentFailure("CONTEXT_TOO_LARGE")
    catalog = EvidenceCatalog(state.inspection_id, tuple(entries))
    if len(catalog_json(catalog).encode("utf-8")) > max_bytes:
        raise AgentFailure("CONTEXT_TOO_LARGE")
    return catalog


def build_catalog(state, max_entries=512, max_bytes=65536):
    try:
        return _build_catalog(state, max_entries, max_bytes)
    except (KeyError, TypeError, ValueError, OverflowError):
        raise AgentFailure("EVIDENCE_MISMATCH") from None


def catalog_json(catalog):
    return json.dumps(asdict(catalog), ensure_ascii=False, allow_nan=False)


def _selection(encoded, fact_ids, allowed, model):
    if not isinstance(encoded, str) or ":" not in encoded:
        raise AgentFailure("RESPONSE_SCHEMA_INVALID")
    code, references = encoded.split(":", 1)
    tokens = references.split(",")
    if code not in allowed or not references or len(tokens) != len(set(tokens)):
        raise AgentFailure("RESPONSE_SCHEMA_INVALID")
    if any(token not in fact_ids for token in tokens):
        raise AgentFailure("EVIDENCE_MISMATCH")
    name = "cause_code" if model is CauseSelection else "check_code"
    return model(**{name: code, "evidence_refs": [fact_ids[token] for token in tokens]})


def convert_simple_report(raw, state, catalog):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 65536:
        raise AgentFailure("CONTEXT_TOO_LARGE")
    try:
        payload = json.loads(raw, parse_constant=AgentService._invalid_json_constant,
            object_pairs_hook=AgentService._unique_keys)
    except (ValueError, TypeError):
        raise AgentFailure("FINAL_JSON_INVALID") from None
    try:
        report = SimpleReport.model_validate(payload)
        if catalog_json(catalog) != catalog_json(build_catalog(state)):
            raise AgentFailure("EVIDENCE_MISMATCH")
        selected = report.observed_fact_refs
        if len(selected) != len(set(selected)):
            raise AgentFailure("RESPONSE_SCHEMA_INVALID")
        entries = {entry.token: entry for entry in catalog.entries}
        if any(token not in entries for token in selected):
            raise AgentFailure("EVIDENCE_MISMATCH")
        fact_ids = {token: f"F{index:04d}" for index, token in enumerate(selected, 1)}
        facts = [ObservedFact(fact_id=fact_ids[token], **{
            name: getattr(entries[token], name) for name in (
                "evidence_id", "source_tool", "source_field", "observed_value", "source_event",
            )}) for token in selected]
        return DiagnosisDraft(
            inspection_id=state.inspection_id, overall_summary=report.overall_summary, observed_facts=facts,
            possible_causes=[_selection(value, fact_ids, get_args(CauseCode), CauseSelection) for value in report.possible_causes],
            recommended_checks=[_selection(value, fact_ids, get_args(CheckCode), CheckSelection) for value in report.recommended_checks],
            limitations=report.limitations,
        )
    except ValidationError:
        raise AgentFailure("RESPONSE_SCHEMA_INVALID") from None


def verify_simple_report(raw, service, state, catalog):
    draft = convert_simple_report(raw, state, catalog)
    return service._verify_report(draft, state, service.settings.GEMINI_MODEL)
