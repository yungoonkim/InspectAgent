"""Offline final-request reconstruction and metadata-only size comparisons."""

import copy
import hashlib
import json
from types import SimpleNamespace

from google.genai import _api_client, _common, models, types

from backend.agent.reporting import build_catalog
from backend.agent.service import RequestState, _report_contents


async def reconstruct_final_request(service, inspection_id, tool_names):
    state = RequestState(inspection_id)
    for round_number, tool in enumerate(tool_names, 1):
        await service._execute(types.FunctionCall(name=tool, args={"inspection_id": inspection_id}), state, round_number)
    captured = {}

    async def capture(**kwargs):
        captured.update(kwargs)
        return types.GenerateContentResponse(candidates=[types.Candidate(
            content=types.Content(role="model", parts=[types.Part.from_text(text="{}")]),
            finish_reason=types.FinishReason.STOP,
        )])

    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=capture)))
    catalog = build_catalog(state)
    await service._generate(client, service.settings.GEMINI_MODEL,
        _report_contents(state, catalog, service.required_warning_event_codes), state, len(tool_names) + 1, structured=True)
    return captured, state


def compact_contents(contents):
    result = copy.deepcopy(contents)
    packet = json.loads(result[0].parts[0].text)
    result[0].parts[0].text = json.dumps(packet, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return result


def request_metrics(request):
    parameters = types._GenerateContentParameters(**request)
    wire = _common.encode_unserializable_types(_common.convert_to_dict(
        models._GenerateContentParameters_to_mldev(SimpleNamespace(vertexai=False), parameters)))
    config = request["config"]
    text = request["contents"][0].parts[0].text
    packet = json.loads(text)
    entries = packet["catalog"]
    schema = wire["generationConfig"]["responseJsonSchema"]
    schema_bytes = json.dumps(schema, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    fingerprints = [(entry["source_field"], json.dumps(entry["observed_value"], sort_keys=True)) for entry in entries]
    seconds = _api_client.get_timeout_in_seconds(config.http_options.timeout)
    derived_headers = {}
    _api_client.populate_server_timeout_header(derived_headers, seconds)
    return {
        "origin": "CURRENT_CODE_RECONSTRUCTION_NOT_HISTORICAL_CAPTURE",
        "model": request["model"], "response_mime_type": config.response_mime_type,
        "schema_sha256": hashlib.sha256(schema_bytes).hexdigest(), "schema_bytes": len(schema_bytes),
        "system_instruction_chars": len(config.system_instruction), "user_chars": len(text),
        "user_utf8_bytes": len(text.encode("utf-8")),
        "catalog_entries": len(entries), "evidence_count": len({entry["evidence_id"] for entry in entries}),
        "catalog_fields": sorted(entries[0]) if entries else [],
        "trace_entries": len(packet["tool_execution_trace"]),
        "repeated_field_value_pairs": len(fingerprints) - len(set(fingerprints)),
        "serialized_request_bytes": len(json.dumps(wire, ensure_ascii=False, separators=(",", ":")).encode("utf-8")),
        "tools_present": "tools" in wire, "tool_config_present": "toolConfig" in wire,
        "roles": [content["role"] for content in wire["contents"]],
        "max_output_tokens": config.max_output_tokens, "thinking_explicit": config.thinking_config is not None,
        "http_timeout_ms": config.http_options.timeout, "retry_attempts": config.http_options.retry_options.attempts,
        "httpx_timeout_seconds": seconds,
        "sdk_default_server_timeout_header": derived_headers.get("X-Server-Timeout"),
        "server_acceptance": "NOT TESTED",
    }
