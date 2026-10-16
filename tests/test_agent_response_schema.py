"""Offline JSON Schema transport checks with unchanged strict report validation."""

import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import asyncio

from google.genai import _api_client, _common, models as sdk_models, types
from pydantic import ValidationError
import pytest

from backend.agent.schemas import (
    DiagnosisDraft, ObservedFact, _project_response_json_schema, diagnosis_response_json_schema,
)
from backend.storage import InspectionStorageBase
from tests.test_agent_service import call_response, normal_responses, report_payload, service_for, wire_transport
from backend.agent.reporting import simple_output_schema
from tests.test_agent_tools import make_record


@pytest.fixture(autouse=True)
def offline_only():
    with patch("backend.agent.service.genai.Client", side_effect=AssertionError("Offline only")), \
         patch.object(_api_client.BaseApiClient, "request", side_effect=AssertionError("Offline only")) as sync_request, \
         patch.object(_api_client.BaseApiClient, "async_request", side_effect=AssertionError("Offline only")) as async_request:
        yield
        sync_request.assert_not_called()
        async_request.assert_not_called()


@pytest.fixture
def storage():
    instance = Mock(spec=InspectionStorageBase)
    instance.get_inspection.return_value = make_record()
    return instance


def schema_nodes(schema):
    yield schema
    for name in ("properties", "$defs"):
        for child in schema.get(name, {}).values():
            yield from schema_nodes(child)
    if "items" in schema:
        yield from schema_nodes(schema["items"])
    for child in schema.get("anyOf", []):
        yield from schema_nodes(child)


def wire_body(config):
    parameters = types._GenerateContentParameters(model="gemini-mock", contents=[types.Content(
        role="user", parts=[types.Part(text="Offline schema check")])], config=config)
    converted = sdk_models._GenerateContentParameters_to_mldev(SimpleNamespace(vertexai=False), parameters)
    return _common.encode_unserializable_types(_common.convert_to_dict(converted))


def test_projection_preserves_all_fields_and_does_not_mutate_server_schema():
    original = DiagnosisDraft.model_json_schema()
    before = copy.deepcopy(original)
    schema = _project_response_json_schema(original)
    assert original == before
    assert diagnosis_response_json_schema() == schema
    assert set(schema["properties"]) == set(original["properties"])
    assert schema["required"] == original["required"]
    assert schema["$defs"].keys() == original["$defs"].keys()
    for name in original["$defs"]:
        assert schema["$defs"][name]["required"] == original["$defs"][name]["required"]
        assert schema["$defs"][name]["properties"].keys() == original["$defs"][name]["properties"].keys()
        assert schema["$defs"][name]["additionalProperties"] is False
    assert schema["additionalProperties"] is False


def test_new_wire_uses_json_schema_without_legacy_schema_conversion():
    schema = diagnosis_response_json_schema()
    body = wire_body(types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=schema))
    assert body["generationConfig"]["responseJsonSchema"] == schema
    assert "responseSchema" not in body["generationConfig"]
    assert schema["type"] == "object"
    assert all(not {"nullable", "any_of", "additional_properties", "property_ordering", "max_items"} & set(node)
               for node in schema_nodes(schema))
    assert all(not {"pattern", "maxLength", "default", "oneOf"} & set(node) for node in schema_nodes(schema))
    json.dumps(body, allow_nan=False)


def test_legacy_wire_reproduces_additional_properties_contract_mismatch():
    body = wire_body(types.GenerateContentConfig(response_mime_type="application/json", response_schema=DiagnosisDraft))
    schema = body["generationConfig"]["responseSchema"]
    assert schema["additional_properties"] is False
    fact = schema["properties"]["observed_facts"]["items"]
    assert fact["additional_properties"] is False
    assert fact["properties"]["source_event"]["nullable"] is True
    assert "any_of" in fact["properties"]["observed_value"]
    assert "$defs" not in schema
    assert schema["type"] == "OBJECT"


@pytest.mark.parametrize("attribute,value", [("oneOf", []), ("allOf", []), ("const", "fixed"),
    ("additional_properties", False), ("nullable", True), ("x-custom", True), ("max_length", 64)])
def test_unreviewed_schema_attributes_are_rejected_before_network(attribute, value):
    schema = DiagnosisDraft.model_json_schema()
    schema["$defs"]["ObservedFact"][attribute] = value
    with pytest.raises(ValueError, match="^UNSUPPORTED_DIAGNOSIS_SCHEMA$"):
        _project_response_json_schema(schema)


def test_nullable_and_scalar_union_remain_standard_json_schema():
    fact = diagnosis_response_json_schema()["$defs"]["ObservedFact"]
    assert fact["properties"]["source_event"]["anyOf"] == [{"type": "string"}, {"type": "null"}]
    assert [branch["type"] for branch in fact["properties"]["observed_value"]["anyOf"]] == [
        "boolean", "integer", "number", "string", "null"]
    assert "observed_value" in fact["required"]
    assert "source_event" not in fact["required"]


def test_nested_arrays_refs_enums_and_limits_are_preserved():
    original = DiagnosisDraft.model_json_schema()
    schema = diagnosis_response_json_schema()
    assert schema["properties"]["observed_facts"]["items"] == {"$ref": "#/$defs/ObservedFact"}
    assert schema["properties"]["observed_facts"]["maxItems"] == 40
    assert schema["properties"]["recommended_checks"]["minItems"] == 1
    assert schema["$defs"]["CheckSelection"]["properties"]["evidence_refs"]["items"]["type"] == "string"
    before_enums = [node["enum"] for node in schema_nodes(original) if "enum" in node]
    assert [node["enum"] for node in schema_nodes(schema) if "enum" in node] == before_enums
    for node in schema_nodes(schema):
        if "$ref" in node:
            assert set(node) == {"$ref"}
            assert node["$ref"].split("/")[-1] in schema["$defs"]


@pytest.mark.parametrize("value", [None, False, 7, 7.25, "recorded"])
def test_server_scalar_validation_preserves_types_and_optional_null(value):
    fact = copy.deepcopy(report_payload()["observed_facts"][0])
    fact["observed_value"] = value
    validated = ObservedFact.model_validate(fact)
    assert type(validated.observed_value) is type(value)
    assert validated.source_event is None


@pytest.mark.parametrize("mutation", ["root_extra", "fact_extra", "bad_id", "long_source_event", "bad_pointer", "bad_enum", "missing_required"])
def test_server_validation_retains_constraints_not_sent_to_gemini(mutation):
    payload = report_payload()
    if mutation == "root_extra":
        payload["unrequested"] = True
    elif mutation == "fact_extra":
        payload["observed_facts"][0]["unrequested"] = True
    elif mutation == "bad_id":
        payload["observed_facts"][0]["fact_id"] = "invalid"
    elif mutation == "long_source_event":
        payload["observed_facts"][0]["source_event"] = "A" * 65
    elif mutation == "bad_pointer":
        payload["observed_facts"][0]["source_field"] = "invalid"
    elif mutation == "bad_enum":
        payload["overall_summary"] = "UNSUPPORTED"
    else:
        del payload["inspection_id"]
    with pytest.raises(ValidationError):
        DiagnosisDraft.model_validate(payload)


@pytest.mark.parametrize("mutation", ["value", "evidence", "duplicate_fact"])
def test_projected_schema_does_not_bypass_trace_or_evidence_checks(storage, mutation):
    payload = report_payload()
    if mutation == "value":
        payload["observed_facts"][0]["observed_value"] = "FAILED"
    elif mutation == "evidence":
        payload["observed_facts"][0]["evidence_id"] = "E9999"
    else:
        payload["observed_facts"].append(copy.deepcopy(payload["observed_facts"][0]))
    service, generator = service_for(storage, normal_responses(payload))
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == ("RESPONSE_SCHEMA_INVALID" if mutation == "duplicate_fact" else "EVIDENCE_MISMATCH")
    assert generator.await_count == 2
    assert result.observed_facts == []
    assert result.tool_execution_trace[0].evidence_id == "E0001"
    assert result.tool_execution_trace[0].executed and result.tool_execution_trace[0].success


def test_sdk_transport_serializes_schema_and_keeps_fast_path_and_evidence(storage):
    responses = normal_responses()
    responses[0] = call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}), signature=b"offline-only-signature")
    transport = wire_transport(responses)
    api_client = SimpleNamespace(vertexai=False, async_request=transport, _verify_response=Mock())
    service, generator = service_for(storage, [])
    service.client = SimpleNamespace(aio=SimpleNamespace(models=sdk_models.AsyncModels(api_client)))
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    assert transport.await_count == 2
    final = transport.call_args_list[1].args[2]
    assert final["generationConfig"]["responseJsonSchema"] == simple_output_schema()
    assert "responseSchema" not in final["generationConfig"]
    assert "tools" not in final
    assert [content["role"] for content in final["contents"]] == ["user"]
    envelope = json.loads(final["contents"][0]["parts"][0]["text"])
    assert {entry["evidence_id"] for entry in envelope["catalog"]} == {"E0001"}
    assert result.tools_used == ["get_inspection_result"]
    assert {fact.evidence_id for fact in result.observed_facts} == {result.tool_execution_trace[0].evidence_id}
    storage.get_inspection.assert_called_once_with("INSP-000001")
    storage.get_logs.assert_not_called()
    storage.list_inspections.assert_not_called()
    json.dumps(result.model_dump(mode="json"), allow_nan=False)


def test_unreviewed_generated_schema_fails_safely_before_final_request(storage):
    service, generator = service_for(storage, normal_responses())
    with patch("backend.agent.service.simple_output_schema", side_effect=ValueError("UNSUPPORTED_DIAGNOSIS_SCHEMA")):
        result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "RESPONSE_SCHEMA_INVALID"
    assert generator.await_count == 1
    assert result.tools_used == ["get_inspection_result"]
