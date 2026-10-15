"""Offline candidate validity, feature isolation and unchanged production models."""

import copy
from unittest.mock import patch

from google.genai import _api_client
from pydantic import ValidationError
import pytest

from backend.agent.schemas import DiagnosisDraft, diagnosis_response_json_schema
from scripts.agent_schema_candidates import (
    FIELD_GROUPS, audit_schema, build_candidates, c_schema, schema_nodes, serialized_request,
)
from tests.test_agent_schema_isolation import schema_cases
from tests.test_agent_service import report_payload


@pytest.fixture(autouse=True)
def forbid_network():
    with patch("google.genai.Client", side_effect=AssertionError("Offline only")) as client, \
         patch.object(_api_client.BaseApiClient, "request", side_effect=AssertionError("Offline only")) as sync_request, \
         patch.object(_api_client.BaseApiClient, "async_request", side_effect=AssertionError("Offline only")) as async_request:
        yield
        client.assert_not_called()
        sync_request.assert_not_called()
        async_request.assert_not_called()


def witness(root, node=None):
    node = root if node is None else node
    if "$ref" in node:
        return witness(root, root["$defs"][node["$ref"].split("/")[-1]])
    if "anyOf" in node:
        return witness(root, node["anyOf"][0])
    if "enum" in node:
        return node["enum"][0]
    if node["type"] == "object":
        return {name: witness(root, child) for name, child in node["properties"].items()}
    if node["type"] == "array":
        return [witness(root, node["items"]) for index in range(node.get("minItems", 1))]
    return {"string": "synthetic", "integer": 1, "number": 1.5, "boolean": True, "null": None}[node["type"]]


def assert_subset_conforms(value, root, node=None):
    node = root if node is None else node
    if "$ref" in node:
        return assert_subset_conforms(value, root, root["$defs"][node["$ref"].split("/")[-1]])
    if "anyOf" in node:
        for branch in node["anyOf"]:
            try:
                assert_subset_conforms(value, root, branch)
                return
            except AssertionError:
                pass
        raise AssertionError("No scalar union branch matches")
    expected = {"object": dict, "array": list, "string": str, "boolean": bool,
                "integer": int, "number": (int, float), "null": type(None)}[node["type"]]
    assert isinstance(value, expected)
    if node["type"] in {"number", "integer"}:
        assert type(value) is not bool
    if "enum" in node:
        assert value in node["enum"]
    if isinstance(value, dict):
        assert set(node.get("required", [])) <= set(value)
        if node.get("additionalProperties") is False:
            assert set(value) <= set(node["properties"])
        for name, child in value.items():
            if name in node["properties"]:
                assert_subset_conforms(child, root, node["properties"][name])
    elif isinstance(value, list):
        assert node.get("minItems", 0) <= len(value) <= node.get("maxItems", float("inf"))
        for child in value:
            assert_subset_conforms(child, root, node["items"])


def test_partition_covers_d_without_overlap_and_keeps_evidence_dependencies_together():
    full = diagnosis_response_json_schema()
    first, second = map(set, FIELD_GROUPS.values())
    assert not first & second
    assert first | second == set(full["properties"])
    assert {"observed_facts", "possible_causes", "recommended_checks"} <= second
    assert set(c_schema()["properties"]) & second == {"observed_facts"}


def test_sources_and_callers_cannot_mutate_c_d_or_production_model():
    base, full = c_schema(), diagnosis_response_json_schema()
    original = copy.deepcopy((base, full, DiagnosisDraft.model_json_schema()))
    candidates = build_candidates(base, full)
    assert c_schema() == schema_cases()["C"]
    assert (base, full, DiagnosisDraft.model_json_schema()) == original
    candidates["E1"]["properties"]["summary"]["type"] = "boolean"
    assert base["properties"]["summary"]["type"] == "string"
    assert candidates["E2"]["properties"]["summary"]["type"] == "string"
    assert diagnosis_response_json_schema() == full


@pytest.mark.parametrize("name", ["E1", "E2", "E3", "E4", "E5", "E6"])
def test_sdk_serialization_has_valid_subset_schema_and_no_tools(name):
    schema = build_candidates()[name]
    before = copy.deepcopy(schema)
    body = serialized_request(schema)
    wire = body["generationConfig"]["responseJsonSchema"]
    assert wire == before and schema == before
    assert set(body) == {"contents", "systemInstruction", "generationConfig"}
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseSchema" not in body["generationConfig"]
    assert [content["role"] for content in body["contents"]] == ["user"]
    assert set(body["contents"][0]["parts"][0]) == {"text"}
    assert audit_schema(wire)["server_acceptance"] == "NOT TESTED"
    assert_subset_conforms(witness(wire), wire)


@pytest.mark.parametrize("name", ["E1", "E2", "E3", "E4", "E5", "E6"])
def test_missing_required_fields_and_broken_references_are_rejected(name):
    schema = build_candidates()[name]
    example = witness(schema)
    for field in schema["required"]:
        trial = copy.deepcopy(example)
        trial.pop(field)
        with pytest.raises(AssertionError):
            assert_subset_conforms(trial, schema)
    for path, node in schema_nodes(schema):
        if "$ref" in node:
            assert node["$ref"].split("/")[-1] in schema["$defs"]


@pytest.mark.parametrize("name", ["E1", "E2"])
def test_group_properties_and_required_fields_match_the_full_wire_schema(name):
    full = serialized_request(diagnosis_response_json_schema())["generationConfig"]["responseJsonSchema"]
    candidate = build_candidates()[name]
    assert set(candidate["properties"]) == set(c_schema()["properties"]) | set(FIELD_GROUPS[name])
    assert set(candidate["required"]) == set(c_schema()["required"]) | set(FIELD_GROUPS[name])
    for field in FIELD_GROUPS[name]:
        assert candidate["properties"][field] == full["properties"][field]
    assert "additionalProperties" not in candidate


def test_e2_has_fact_ids_and_selection_references_without_unused_definitions():
    schema = build_candidates()["E2"]
    assert set(schema["$defs"]) == {"ObservedFact", "CauseSelection", "CheckSelection"}
    assert "fact_id" in schema["$defs"]["ObservedFact"]["required"]
    assert "evidence_refs" in schema["$defs"]["CauseSelection"]["required"]
    assert "evidence_refs" in schema["$defs"]["CheckSelection"]["required"]
    payload = report_payload()
    example = {"summary": "synthetic", **{name: payload[name] for name in FIELD_GROUPS["E2"]}}
    assert_subset_conforms(example, schema)
    fact_ids = {fact["fact_id"] for fact in example["observed_facts"]}
    assert all(set(selection["evidence_refs"]) <= fact_ids for selection in example["recommended_checks"])


def test_e3_is_enum_scalar_union_and_nullable_without_refs_or_array_bounds():
    schema = build_candidates()["E3"]
    full = diagnosis_response_json_schema()
    fact = schema["properties"]["observed_facts"]["items"]
    assert schema["properties"]["overall_summary"] == full["properties"]["overall_summary"]
    for field in ("source_tool", "source_event", "observed_value"):
        assert fact["properties"][field] == full["$defs"]["ObservedFact"]["properties"][field]
    assert "source_event" not in fact["required"]
    assert audit_schema(schema)["unions"] == 2
    assert all(not {"$ref", "minItems", "maxItems", "additionalProperties"} & set(node) for path, node in schema_nodes(schema))
    example = witness(schema)
    example["observed_facts"][0]["source_event"] = None
    example["observed_facts"][0]["observed_value"] = None
    assert_subset_conforms(example, schema)


def test_e4_changes_only_the_existing_array_bounds_and_enforces_them():
    schema = build_candidates()["E4"]
    array = schema["properties"]["observed_facts"]
    assert (array.pop("minItems"), array.pop("maxItems")) == (1, 40)
    assert schema == c_schema()
    schema = build_candidates()["E4"]
    for count in (0, 41):
        example = witness(schema)
        example["observed_facts"] = example["observed_facts"] * count
        with pytest.raises(AssertionError):
            assert_subset_conforms(example, schema)


def test_e5_is_a_reference_encoding_of_exactly_the_successful_c_object():
    schema = build_candidates()["E5"]
    assert schema["$defs"]["ObservedFact"] == c_schema()["properties"]["observed_facts"]["items"]
    restored = copy.deepcopy(schema)
    restored["properties"]["observed_facts"]["items"] = restored.pop("$defs")["ObservedFact"]
    assert restored == c_schema()


def test_e6_is_only_object_closure_and_rejects_arbitrary_extra_properties():
    schema = build_candidates()["E6"]
    example = witness(schema)
    example["unrequested"] = "synthetic"
    with pytest.raises(AssertionError):
        assert_subset_conforms(example, schema)
    assert schema.pop("additionalProperties") is False
    assert schema["properties"]["observed_facts"]["items"].pop("additionalProperties") is False
    assert schema == c_schema()


@pytest.mark.parametrize("mutation,code", [
    ("required", "INVALID_REQUIRED_FIELDS"), ("duplicate", "INVALID_REQUIRED_FIELDS"),
    ("missing_ref", "UNRESOLVED_REFERENCE"), ("external_ref", "INVALID_LOCAL_REFERENCE"),
    ("siblings", "REFERENCE_SIBLINGS"), ("cycle", "CYCLIC_REFERENCE"),
    ("bounds", "INCONSISTENT_ARRAY_BOUNDS"), ("unsupported", "UNREVIEWED_SCHEMA_KEY"),
    ("empty_union", "EMPTY_UNION"), ("invalid_type", "INVALID_SCHEMA_TYPE"), ("empty_enum", "INVALID_ENUM"),
])
def test_partition_errors_cannot_be_mistaken_for_server_rejections(mutation, code):
    schema = build_candidates()["E5"]
    if mutation == "required":
        schema["required"].append("missing")
    elif mutation == "duplicate":
        schema["required"].append("summary")
    elif mutation in {"missing_ref", "external_ref"}:
        schema["properties"]["observed_facts"]["items"]["$ref"] = "#/$defs/Missing" if mutation == "missing_ref" else "https://example.invalid/schema"
    elif mutation == "siblings":
        schema["properties"]["observed_facts"]["items"]["title"] = "synthetic"
    elif mutation == "cycle":
        schema["$defs"]["ObservedFact"] = {"$ref": "#/$defs/ObservedFact"}
    elif mutation == "bounds":
        schema["properties"]["observed_facts"].update(minItems=2, maxItems=1)
    elif mutation == "unsupported":
        schema["const"] = "synthetic"
    elif mutation == "empty_union":
        schema["properties"]["summary"] = {"anyOf": []}
    elif mutation == "invalid_type":
        schema["properties"]["summary"]["type"] = "unsupported"
    else:
        schema["properties"]["summary"]["enum"] = []
    with pytest.raises(ValueError, match=f"^{code}$"):
        audit_schema(schema)


def test_unknown_d_fields_fail_closed_instead_of_silently_disappearing():
    full = diagnosis_response_json_schema()
    full["properties"]["future_field"] = {"type": "string"}
    with pytest.raises(ValueError, match="^FIELD_PARTITION_MISMATCH$"):
        build_candidates(d_source=full)


def test_experiment_variants_do_not_weaken_server_pydantic_validation():
    payload = report_payload()
    DiagnosisDraft.model_validate(payload)
    for mutation in ("extra", "invalid_id", "invalid_enum"):
        trial = copy.deepcopy(payload)
        if mutation == "extra":
            trial["summary"] = "synthetic"
        elif mutation == "invalid_id":
            trial["observed_facts"][0]["evidence_id"] = "not-valid"
        else:
            trial["overall_summary"] = "not-valid"
        with pytest.raises(ValidationError):
            DiagnosisDraft.model_validate(trial)
