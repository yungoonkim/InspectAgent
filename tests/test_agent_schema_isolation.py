"""Offline schema reduction and privacy-preserving SDK error diagnostics."""

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from google.genai import _api_client, _common, errors, models as sdk_models, types
import pytest

from backend.agent.diagnostics import safe_gemini_error
from backend.agent.prompts import REPORT_SYSTEM_INSTRUCTION
from backend.agent.schemas import DiagnosisDraft, diagnosis_response_json_schema
from backend.storage import InspectionStorageBase
from tests.test_agent_service import call_response, normal_responses, service_for, wire_transport
from backend.agent.reporting import simple_output_schema
from tests.test_agent_tools import make_record


DOCUMENTED_SCHEMA_KEYS = frozenset({
    "$id", "$defs", "$ref", "$anchor", "type", "format", "title", "description", "enum",
    "items", "prefixItems", "minItems", "maxItems", "minimum", "maximum", "anyOf", "oneOf",
    "properties", "additionalProperties", "required", "propertyOrdering",
})


@pytest.fixture(autouse=True)
def offline_only():
    with patch("backend.agent.service.genai.Client", side_effect=AssertionError("Offline only")), \
         patch.object(_api_client.BaseApiClient, "request", side_effect=AssertionError("Offline only")) as sync_request, \
         patch.object(_api_client.BaseApiClient, "async_request", side_effect=AssertionError("Offline only")) as async_request:
        yield
        sync_request.assert_not_called()
        async_request.assert_not_called()


def schema_cases():
    return {
        "A": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
        "B": {"type": "object", "properties": {
            "summary": {"type": "string"}, "status": {"type": "string"},
            "recommended_checks": {"type": "array", "items": {"type": "string"}},
        }, "required": ["summary", "status", "recommended_checks"]},
        "C": {"type": "object", "properties": {
            "summary": {"type": "string"}, "observed_facts": {"type": "array", "items": {
                "type": "object", "properties": {
                    "evidence_id": {"type": "string"}, "source_field": {"type": "string"},
                    "observed_value": {"type": "string"},
                }, "required": ["evidence_id", "source_field", "observed_value"],
            }},
        }, "required": ["summary", "observed_facts"]},
        "D": diagnosis_response_json_schema(),
    }


def schema_nodes(schema):
    yield schema
    for name in ("properties", "$defs"):
        for child in schema.get(name, {}).values():
            yield from schema_nodes(child)
    if "items" in schema:
        yield from schema_nodes(schema["items"])
    for name in ("anyOf", "oneOf", "prefixItems"):
        for child in schema.get(name, []):
            yield from schema_nodes(child)


def schema_metadata(schema):
    nodes = list(schema_nodes(schema))

    def container_depth(node):
        if "$ref" in node:
            return container_depth(schema["$defs"][node["$ref"].split("/")[-1]])
        children = list(node.get("properties", {}).values())
        children += [node["items"]] if "items" in node else []
        children += node.get("anyOf", [])
        return int(node.get("type") in {"object", "array"}) + max([container_depth(child) for child in children] or [0])

    return {
        "schema_bytes": len(json.dumps(schema, ensure_ascii=False).encode("utf-8")),
        "container_depth": container_depth(schema),
        "definitions": len(schema.get("$defs", {})),
        "refs": sum("$ref" in node for node in nodes),
        "any_of": sum("anyOf" in node for node in nodes),
        "null_types": sum(node.get("type") == "null" for node in nodes),
        "arrays": sum(node.get("type") == "array" for node in nodes),
        "unsupported_keys": sorted(set().union(*(set(node) for node in nodes)) - DOCUMENTED_SCHEMA_KEYS),
    }


@pytest.mark.parametrize("case", ["A", "B", "C", "D"])
def test_reduced_schemas_are_only_offline_fixtures_not_production_replacements(case):
    before = diagnosis_response_json_schema()
    schema = schema_cases()[case]
    config = types.GenerateContentConfig(
        system_instruction="Use only the synthetic fixture and return JSON matching the supplied schema. No tools are available.",
        temperature=0, candidate_count=1, max_output_tokens=4096,
        response_mime_type="application/json", response_json_schema=schema,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True), automatic_continuation=False,
        http_options=types.HttpOptions(timeout=15000, retry_options=types.HttpRetryOptions(attempts=1)),
    )
    parameters = types._GenerateContentParameters(model="gemini-3.8-flash", config=config,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text="Use only the synthetic fixture supplied for this offline check.")])])
    converted = sdk_models._GenerateContentParameters_to_mldev(SimpleNamespace(vertexai=False), parameters)
    wire = _common.encode_unserializable_types(_common.convert_to_dict(converted))
    assert wire["generationConfig"]["responseJsonSchema"] == schema
    assert wire["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseSchema" not in wire["generationConfig"]
    assert "tools" not in wire and "toolConfig" not in wire
    assert set(wire["contents"][0]["parts"][0]) == {"text"}
    assert schema_metadata(schema)["unsupported_keys"] == []
    assert diagnosis_response_json_schema() == before
    json.dumps(wire, allow_nan=False)


@pytest.mark.parametrize("case,depth,definitions,refs,unions", [
    ("A", 1, 0, 0, 0), ("B", 2, 0, 0, 0), ("C", 3, 0, 0, 0), ("D", 4, 3, 3, 2),
])
def test_schema_complexity_is_measured_not_inferred_as_server_failure(case, depth, definitions, refs, unions):
    metadata = schema_metadata(schema_cases()[case])
    assert metadata["container_depth"] == depth
    assert metadata["definitions"] == definitions
    assert metadata["refs"] == refs
    assert metadata["any_of"] == unions
    assert metadata["unsupported_keys"] == []


def test_full_schema_has_valid_noncyclic_refs_and_all_required_diagnosis_fields():
    schema = schema_cases()["D"]
    assert schema == diagnosis_response_json_schema()
    assert schema["required"] == DiagnosisDraft.model_json_schema()["required"]
    for node in schema_nodes(schema):
        if "$ref" in node:
            assert set(node) == {"$ref"}
            assert node["$ref"].startswith("#/$defs/")
            assert node["$ref"].split("/")[-1] in schema["$defs"]
    assert not any("$ref" in node for definition in schema["$defs"].values() for node in schema_nodes(definition))


@pytest.mark.parametrize("keyword", ["additional_properties", "nullable", "allOf", "pattern", "x-secret"])
def test_schema_audit_detects_unreviewed_attributes_without_changing_live_schema(keyword):
    schema = copy.deepcopy(schema_cases()["D"])
    schema["$defs"]["ObservedFact"][keyword] = False
    assert schema_metadata(schema)["unsupported_keys"] == [keyword]
    assert keyword not in diagnosis_response_json_schema()["$defs"]["ObservedFact"]


def test_actual_sdk_final_request_options_and_api_version_are_offline_only():
    storage = Mock(spec=InspectionStorageBase)
    storage.get_inspection.return_value = make_record()
    service, generator = service_for(storage, [])
    transport = wire_transport(normal_responses())
    api_client = SimpleNamespace(vertexai=False, async_request=transport, _verify_response=Mock())
    service.client = SimpleNamespace(aio=SimpleNamespace(models=sdk_models.AsyncModels(api_client)))
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    assert transport.await_count == 2
    method, path, body, options = transport.call_args_list[-1].args
    assert method == "post" and path.endswith("gemini-mock:generateContent")
    builder = SimpleNamespace(vertexai=False, project=None, location=None, custom_base_url=None, api_key=None,
        _http_options=types.HttpOptions(api_version="v1beta", base_url="https://generativelanguage.googleapis.com/", headers={}))
    request = _api_client.BaseApiClient._build_request(builder, method, path, copy.deepcopy(body), options)
    body = request.data
    assert request.url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-mock:generateContent"
    assert request.timeout == 15
    assert set(body) == {"contents", "systemInstruction", "generationConfig"}
    assert [content["role"] for content in body["contents"]] == ["user"]
    assert set(body["contents"][0]["parts"][0]) == {"text"}
    assert body["generationConfig"] == {
        "temperature": 0, "candidateCount": 1, "maxOutputTokens": 4096,
        "responseMimeType": "application/json", "responseJsonSchema": simple_output_schema(),
    }
    assert body["systemInstruction"]["parts"][0]["text"] == REPORT_SYSTEM_INSTRUCTION
    assert options.timeout == 15000 and options.retry_options.attempts == 1
    assert options.api_version is None and options.extra_body is None and options.base_url is None
    assert result.tools_used == ["get_inspection_result"]
    assert result.tool_execution_trace[0].success
    generator.assert_not_called()


def api_error(details=None, message="PRIVATE-MESSAGE"):
    return errors.ClientError(400, {"error": {
        "code": 400, "status": "INVALID_ARGUMENT", "message": message, "details": details or [],
    }})


def bad_request(field, reason="INVALID_VALUE"):
    return {"@type": "type.googleapis.com/google.rpc.BadRequest", "fieldViolations": [
        {"field": field, "reason": reason, "description": "PRIVATE-DESCRIPTION"},
    ]}


def test_error_diagnostics_extract_only_standard_codes_reasons_and_known_field_paths():
    error = api_error([
        {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "INVALID_SCHEMA",
         "domain": "PRIVATE-DOMAIN", "metadata": {"private": "PRIVATE-METADATA"}},
        bad_request('generationConfig.responseJsonSchema.properties["observed_facts"].items'),
    ])
    before = copy.deepcopy(error.details)
    result = safe_gemini_error(error, "STRUCTURED_OUTPUT")
    assert result == {
        "http_status": 400, "google_api_code": "INVALID_ARGUMENT", "reason": "INVALID_SCHEMA",
        "field_violations": [{"field": 'generationConfig.responseJsonSchema.properties["observed_facts"].items', "reason": "INVALID_VALUE"}],
        "request_stage": "STRUCTURED_OUTPUT", "sdk_exception_type": "ClientError",
    }
    assert "PRIVATE" not in json.dumps(result)
    assert error.details == before


def test_second_request_failure_can_be_collected_without_changing_agent_error_contract():
    storage = Mock(spec=InspectionStorageBase)
    storage.get_inspection.return_value = make_record()
    service, generator = service_for(storage, [])
    captured = []

    async def generate(**kwargs):
        if kwargs["config"].response_mime_type == "application/json":
            try:
                raise api_error([bad_request("generationConfig.responseJsonSchema")])
            except errors.APIError as failure:
                captured.append(safe_gemini_error(failure, "STRUCTURED_OUTPUT"))
                raise
        return call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}))

    generator.side_effect = generate
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "GEMINI_REQUEST_FAILED" and result.analysis_status == "FAILED"
    assert generator.await_count == 2
    assert captured[0]["field_violations"][0]["field"] == "generationConfig.responseJsonSchema"
    assert captured[0]["request_stage"] == "STRUCTURED_OUTPUT"
    assert result.tool_execution_trace[0].success and result.tool_execution_trace[0].evidence_id == "E0001"
    assert "PRIVATE" not in result.model_dump_json() + json.dumps(captured)


@pytest.mark.parametrize("field", [
    "generation_config.response_json_schema.properties.observed_facts.items.anyOf[0].type",
    "generationConfig.responseJsonSchema.$defs.ObservedFact.properties.observed_value.anyOf[4].type",
    "contents[0].parts[0].text", "generationConfig.responseMimeType",
])
def test_known_request_field_paths_are_preserved_without_values(field):
    result = safe_gemini_error(api_error([bad_request(field)]), "STRUCTURED_OUTPUT")
    assert result["field_violations"] == [{"field": field, "reason": "INVALID_VALUE"}]


@pytest.mark.parametrize("field", [
    "C:\\private\\key", "/home/private/key", "generationConfig.responseJsonSchema.properties.PRIVATE_LABEL",
    'generationConfig.responseJsonSchema.properties["PRIVATE_LABEL"]', "contents[0].parts[0].text\nPRIVATE",
    "generationConfig." + "a" * 250, None, {"private": "PRIVATE-DATA"}, "contents[-1].parts",
])
def test_unknown_or_sensitive_field_paths_are_not_echoed(field):
    result = safe_gemini_error(api_error([bad_request(field, reason="PRIVATE_REASON")]), "STRUCTURED_OUTPUT")
    assert result["field_violations"] == [{"field": "UNKNOWN", "reason": "UNKNOWN"}]
    assert "PRIVATE" not in json.dumps(result)


def test_reason_is_never_inferred_from_free_form_error_messages():
    result = safe_gemini_error(api_error(message="Invalid response schema private data"), "STRUCTURED_OUTPUT")
    assert result["reason"] == "UNKNOWN" and result["field_violations"] == []
    assert "schema" not in json.dumps(result).lower()


@pytest.mark.parametrize("details", [None, "PRIVATE", {"private": "PRIVATE"}, [None, "PRIVATE", {}]])
def test_missing_malformed_or_unrecognized_error_details_fail_closed(details):
    error = api_error()
    error.details = {"error": {"details": details}}
    result = safe_gemini_error(error, "PRIVATE-STAGE")
    assert result["field_violations"] == [] and result["reason"] == "UNKNOWN"
    assert result["request_stage"] == "UNKNOWN"
    assert "PRIVATE" not in json.dumps(result)


def test_oversized_violation_lists_are_bounded_and_unknown_details_are_ignored():
    detail = bad_request("generationConfig.responseJsonSchema")
    detail["fieldViolations"] *= 1000
    error = api_error([detail, {"@type": "PRIVATE-TYPE", "text": "PRIVATE-DATA"}])
    result = safe_gemini_error(error, "STRUCTURED_OUTPUT")
    assert len(result["field_violations"]) == 10
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("error", [RuntimeError("PRIVATE"), TimeoutError("PRIVATE"),
    errors.ServerError(503, {"error": {"status": "UNAVAILABLE", "message": "PRIVATE"}})])
def test_exception_names_and_status_are_closed_enums(error):
    result = safe_gemini_error(error, "FUNCTION_CALLING")
    assert result["sdk_exception_type"] in {"UNKNOWN", "ServerError"}
    assert result["google_api_code"] in {"UNKNOWN", "UNAVAILABLE"}
    assert "PRIVATE" not in json.dumps(result)
