"""Dependency-aware E2 partitioning; all server acceptance remains untested."""

import copy
from unittest.mock import patch

from google.genai import _api_client
import pytest

from backend.agent.schemas import DiagnosisDraft, diagnosis_response_json_schema
from scripts.agent_schema_candidates import (
    audit_schema, build_candidates, build_e2_partitions, build_e2_subcandidate, c_schema, serialized_request,
)
from tests.test_agent_schema_candidates import assert_subset_conforms, witness


@pytest.fixture(autouse=True)
def offline_only():
    with patch("google.genai.Client", side_effect=AssertionError("Offline only")) as client, \
         patch.object(_api_client.BaseApiClient, "request", side_effect=AssertionError("Offline only")) as sync_request, \
         patch.object(_api_client.BaseApiClient, "async_request", side_effect=AssertionError("Offline only")) as async_request:
        yield
        client.assert_not_called()
        sync_request.assert_not_called()
        async_request.assert_not_called()


def test_parent_c_d_and_pydantic_are_preserved_and_reconstructable():
    parent = build_candidates()["E2"]
    before = copy.deepcopy((parent, c_schema(), diagnosis_response_json_schema(), DiagnosisDraft.model_json_schema()))
    parts = build_e2_partitions(parent)
    assert (parent, c_schema(), diagnosis_response_json_schema(), DiagnosisDraft.model_json_schema()) == before
    restored = copy.deepcopy(parts["E2-A"])
    for name in ("possible_causes", "recommended_checks"):
        restored["properties"][name] = copy.deepcopy(parts["E2-B"]["properties"][name])
        restored["required"].append(name)
    restored["$defs"].update(copy.deepcopy(parts["E2-B"]["$defs"]))
    assert restored == parent
    parts["E2-A"]["properties"]["summary"]["type"] = "boolean"
    assert parts["E2-B"]["properties"]["summary"]["type"] == "string"


@pytest.mark.parametrize("name", ["E2-A", "E2-B"])
def test_partition_serializes_and_accepts_parent_valid_data_without_new_constraints(name):
    parent = build_candidates()["E2"]
    child = build_e2_partitions()[name]
    wire = serialized_request(child)
    assert wire["generationConfig"]["responseJsonSchema"] == child
    assert "responseSchema" not in wire["generationConfig"]
    assert "tools" not in wire and "toolConfig" not in wire
    assert audit_schema(child)["server_acceptance"] == "NOT TESTED"
    assert_subset_conforms(witness(parent), child)
    example = witness(child)
    for field in child["required"]:
        trial = copy.deepcopy(example)
        trial.pop(field)
        with pytest.raises(AssertionError):
            assert_subset_conforms(trial, child)


def test_a_is_full_facts_and_b_has_only_the_fact_id_dependency_carrier():
    parent = build_candidates()["E2"]
    first, second = build_e2_partitions().values()
    assert set(first["properties"]) == {"summary", "observed_facts"}
    assert set(first["$defs"]) == {"ObservedFact"}
    assert first["properties"]["observed_facts"] == parent["properties"]["observed_facts"]
    assert set(second["$defs"]) == {"CauseSelection", "CheckSelection"}
    carrier = second["properties"]["observed_facts"]["items"]
    assert set(carrier["properties"]) == {"fact_id"} and carrier["required"] == ["fact_id"]
    assert "additionalProperties" not in carrier
    assert (second["properties"]["observed_facts"]["minItems"], second["properties"]["observed_facts"]["maxItems"]) == (1, 40)
    assert carrier["properties"]["fact_id"] == parent["$defs"]["ObservedFact"]["properties"]["fact_id"]


@pytest.mark.parametrize("fields", [("possible_causes",), ("recommended_checks",), ("observed_facts", "recommended_checks")])
def test_smaller_children_are_prepared_on_demand_not_enumerated_automatically(fields):
    schema = build_e2_subcandidate(fields)
    assert set(schema["properties"]) == {"summary", "observed_facts", *fields}
    assert_subset_conforms(witness(schema), schema)
    assert audit_schema(schema)["server_acceptance"] == "NOT TESTED"


@pytest.mark.parametrize("fields", [(), ("unknown",), ("observed_facts", "observed_facts")])
def test_invalid_field_selection_is_rejected(fields):
    with pytest.raises(ValueError, match="^INVALID_E2_FIELD_SELECTION$"):
        build_e2_subcandidate(fields)


@pytest.mark.parametrize("mutation", ["reference", "required", "unsupported"])
def test_parent_schema_errors_are_not_hidden_by_partitioning(mutation):
    source = build_candidates()["E2"]
    if mutation == "reference":
        source["properties"]["observed_facts"]["items"]["$ref"] = "#/$defs/Missing"
    elif mutation == "required":
        source["required"].append("unknown")
    else:
        source["const"] = "synthetic"
    with pytest.raises(ValueError):
        build_e2_partitions(source)


def test_foreign_key_types_and_structure_remain_present_but_do_not_prove_grounding():
    source = build_e2_partitions()["E2-B"]
    example = witness(source)
    example["observed_facts"][0]["fact_id"] = "F0001"
    example["recommended_checks"][0]["evidence_refs"] = ["F0001"]
    assert_subset_conforms(example, source)
    example["recommended_checks"][0]["evidence_refs"] = [1]
    with pytest.raises(AssertionError):
        assert_subset_conforms(example, source)
