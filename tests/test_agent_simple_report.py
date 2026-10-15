"""Mock-only selection conversion with the existing deterministic verifier."""

import asyncio
import copy
from dataclasses import replace
import json
from unittest.mock import Mock, patch

from google.genai import _api_client, errors
import pytest

from backend.agent.schemas import DiagnosisDraft
from backend.agent.service import AgentFailure, CORE_FIELDS, RequestState
from backend.storage import InspectionStorageBase
from scripts.agent_schema_candidates import serialized_request
from scripts.agent_simple_report_prototype import (
    build_catalog, catalog_json, convert_simple_report, simple_output_schema, verify_simple_report,
)
from tests.test_agent_service import call_response, service_for
from tests.test_agent_tools import make_log, make_record


@pytest.fixture(autouse=True)
def offline_only():
    with patch("google.genai.Client", side_effect=AssertionError("Offline only")) as client, \
         patch.object(_api_client.BaseApiClient, "request", side_effect=AssertionError("Offline only")) as sync_request, \
         patch.object(_api_client.BaseApiClient, "async_request", side_effect=AssertionError("Offline only")) as async_request:
        yield
        client.assert_not_called()
        sync_request.assert_not_called()
        async_request.assert_not_called()


def setup_report(changes=None, extra_tools=()):
    storage = Mock(spec=InspectionStorageBase)
    storage.get_inspection.return_value = make_record(**(changes or {}))
    storage.get_logs.return_value = [make_log(event_code="IMAGE_LOAD_FAILED")]
    storage.list_inspections.return_value = [storage.get_inspection.return_value]
    service, generator = service_for(storage, [])
    state = RequestState("INSP-000001")

    async def collect():
        for index, name in enumerate(("get_inspection_result", *extra_tools), 1):
            call = call_response((name, {"inspection_id": state.inspection_id})).candidates[0].content.parts[0].function_call
            await service._execute(call, state, index)

    asyncio.run(collect())
    catalog = build_catalog(state)
    core = {name: next(entry.token for entry in catalog.entries if entry.source_tool == "get_inspection_result"
                      and entry.source_field == f"/data/{name}") for name in CORE_FIELDS}
    summary = {"OK": "NORMAL_MODEL_RESULT", "NG": "PRODUCT_ANOMALY", "REINSPECT": "REINSPECTION_REQUIRED",
               "ERROR": "INSPECTION_FAILED"}.get(state.snapshot["final_result"], "INSUFFICIENT_DATA")
    check = "CONTINUE_MONITORING" if state.snapshot["final_result"] == "OK" else "MANUAL_REINSPECTION"
    payload = {"overall_summary": summary, "observed_fact_refs": list(core.values()), "possible_causes": [],
               "recommended_checks": [check + ":" + core["final_result"]], "limitations": []}
    return service, generator, state, catalog, payload, core, storage


def test_simple_wire_has_only_strings_and_string_arrays_not_refs_or_unions():
    schema = simple_output_schema()
    body = serialized_request(schema)
    assert body["generationConfig"]["responseJsonSchema"] == schema
    assert "tools" not in body and "toolConfig" not in body
    assert set(schema["properties"]) == set(schema["required"])
    assert {node["type"] for node in schema["properties"].values()} == {"string", "array"}
    assert all(node == {"type": "string"} or node == {"type": "array", "items": {"type": "string"}}
               for node in schema["properties"].values())


@pytest.mark.parametrize("changes", [None,
    {"image_quality_status": "WARNING_LOW_BRIGHTNESS", "final_result": "REINSPECT", "final_reason_code": "IMAGE_QUALITY_WARNING"},
    {"status": "FAILED", "result": "UNKNOWN", "image_quality_status": "ERROR", "defect_detection_status": "SKIPPED",
     "final_result": "ERROR", "final_reason_code": "INSPECTION_FAILED", "anomaly_score": None},
    {"final_reason_code": None},
])
def test_mock_conversion_preserves_pydantic_evidence_verdicts_trace_and_legacy_nulls(changes):
    service, generator, state, catalog, payload, core, storage = setup_report(changes)
    before = copy.deepcopy((state.evidence, state.snapshot, state.trace))
    draft = convert_simple_report(json.dumps(payload), state, catalog)
    assert DiagnosisDraft.model_validate(draft.model_dump()) == draft
    result = verify_simple_report(json.dumps(payload), service, state, catalog)
    assert result.analysis_status == "COMPLETED"
    assert result.inspection_snapshot["result"] == state.snapshot["result"]
    assert result.inspection_snapshot["final_result"] == state.snapshot["final_result"]
    assert result.inspection_snapshot["final_reason_code"] == state.snapshot["final_reason_code"]
    assert all(fact.evidence_id == "E0001" for fact in result.observed_facts)
    assert result.tool_execution_trace == state.trace and result.tools_used == ["get_inspection_result"]
    assert (state.evidence, state.snapshot, state.trace) == before
    generator.assert_not_called()
    storage.save_inspection.assert_not_called()
    storage.save_logs.assert_not_called()
    json.dumps(result.model_dump(mode="json"), allow_nan=False)


@pytest.mark.parametrize("mutation,code", [
    ("unknown_token", "EVIDENCE_MISMATCH"), ("raw_evidence_id", "EVIDENCE_MISMATCH"),
    ("duplicate_token", "RESPONSE_SCHEMA_INVALID"), ("omitted_core", "EVIDENCE_MISMATCH"),
    ("wrong_summary", "EVIDENCE_MISMATCH"), ("unsupported_cause", "EVIDENCE_MISMATCH"),
    ("unselected_reference", "EVIDENCE_MISMATCH"), ("invented_value", "RESPONSE_SCHEMA_INVALID"),
    ("extra_id", "RESPONSE_SCHEMA_INVALID"), ("bad_code", "RESPONSE_SCHEMA_INVALID"),
    ("bad_limitations", "RESPONSE_SCHEMA_INVALID"), ("missing_field", "RESPONSE_SCHEMA_INVALID"),
    ("wrong_type", "RESPONSE_SCHEMA_INVALID"), ("free_prose", "RESPONSE_SCHEMA_INVALID"),
])
def test_invalid_claims_are_rejected_without_repair_or_invented_core_facts(mutation, code):
    service, generator, state, catalog, payload, core, storage = setup_report()
    if mutation == "unknown_token":
        payload["observed_fact_refs"][0] = "K9999"
    elif mutation == "raw_evidence_id":
        payload["observed_fact_refs"][0] = "E9999"
    elif mutation == "duplicate_token":
        payload["observed_fact_refs"].append(payload["observed_fact_refs"][0])
    elif mutation == "omitted_core":
        payload["observed_fact_refs"].remove(core["status"])
    elif mutation == "wrong_summary":
        payload["overall_summary"] = "PRODUCT_ANOMALY"
    elif mutation == "unsupported_cause":
        payload["possible_causes"] = ["ILLUMINATION_CHANGE:" + core["image_quality_status"]]
    elif mutation == "unselected_reference":
        token = next(entry.token for entry in catalog.entries if entry.source_field == "/data/anomaly_score")
        payload["recommended_checks"] = ["CONTINUE_MONITORING:" + token]
    elif mutation == "invented_value":
        payload["observed_value"] = 999
    elif mutation == "extra_id":
        payload["inspection_id"] = "INSP-000002"
    elif mutation == "bad_code":
        payload["recommended_checks"] = ["RUN_SHELL:" + core["final_result"]]
    elif mutation == "bad_limitations":
        payload["limitations"] = ["PRIVATE-CLAIM"]
    elif mutation == "missing_field":
        payload.pop("limitations")
    elif mutation == "wrong_type":
        payload["observed_fact_refs"][0] = 1
    else:
        payload["overall_summary"] = "PRIVATE-INSTRUCTION"
    with pytest.raises(AgentFailure) as failure:
        verify_simple_report(json.dumps(payload), service, state, catalog)
    assert failure.value.code == code
    assert "PRIVATE" not in str(failure.value)
    generator.assert_not_called()


@pytest.mark.parametrize("raw", ["not json", '{"overall_summary":NaN}', '{"overall_summary":"A","overall_summary":"B"}'])
def test_invalid_json_and_duplicate_keys_are_not_normalized(raw):
    service, generator, state, catalog, payload, core, storage = setup_report()
    with pytest.raises(AgentFailure) as failure:
        convert_simple_report(raw, state, catalog)
    assert failure.value.code == "FINAL_JSON_INVALID"


@pytest.mark.parametrize("mutation", ["value", "pointer", "evidence_id", "owner", "state_value", "unexecuted_trace"])
def test_catalog_is_bound_to_real_values_pointers_ids_owner_and_executed_trace(mutation):
    service, generator, state, catalog, payload, core, storage = setup_report()
    row = catalog.entries[0]
    if mutation in {"value", "pointer", "evidence_id"}:
        replacement = {"value": {"observed_value": 999}, "pointer": {"source_field": "/data/unrecorded"},
                       "evidence_id": {"evidence_id": "E9999"}}[mutation]
        catalog = replace(catalog, entries=(replace(row, **replacement), *catalog.entries[1:]))
    elif mutation == "owner":
        catalog = replace(catalog, inspection_id="INSP-000002")
    elif mutation == "state_value":
        state.evidence["E0001"][1]["data"]["anomaly_score"] = 1
    else:
        state.trace[0].executed = False
    with pytest.raises(AgentFailure) as failure:
        verify_simple_report(json.dumps(payload), service, state, catalog)
    assert failure.value.code == "EVIDENCE_MISMATCH"


def test_catalog_allowlist_excludes_private_fields_paths_ids_messages_and_commands():
    changes = {"product_id": "PRIVATE-PRODUCT", "image_id": "PRIVATE-IMAGE",
        "metrics": {"mean": 125, "ground_truth": "PRIVATE-LABEL", "injection_factor": 0.1,
                    "private_path": "PRIVATE-PATH", "model_version": "PRIVATE-INSTRUCTION"}}
    service, generator, state, catalog, payload, core, storage = setup_report(changes)
    state.evidence["E0001"][1]["data"]["ground_truth"] = "PRIVATE-LABEL"
    state.evidence["E0001"][1]["data"]["metrics"]["private_path"] = "PRIVATE-PATH"
    text = catalog_json(build_catalog(state))
    for forbidden in ("PRIVATE", "ground_truth", "injection_factor", "product_id", "image_id", "private_path"):
        assert forbidden not in text


def test_log_pointers_and_events_remain_grounded_in_the_executed_log_tool():
    service, generator, state, catalog, payload, core, storage = setup_report(
        {"status": "FAILED", "result": "UNKNOWN", "image_quality_status": "ERROR", "defect_detection_status": "SKIPPED",
         "final_result": "ERROR", "final_reason_code": "INSPECTION_FAILED"}, ("get_execution_logs",))
    event = next(entry for entry in catalog.entries if entry.source_tool == "get_execution_logs" and entry.source_field == "/data/0/event_code")
    payload["observed_fact_refs"].append(event.token)
    payload["possible_causes"] = ["IMAGE_ACQUISITION:" + event.token]
    payload["recommended_checks"].append("IMAGE_REGISTRATION_ACCESS_CHECK:" + event.token)
    result = verify_simple_report(json.dumps(payload), service, state, catalog)
    assert result.observed_facts[-1].source_event == "IMAGE_LOAD_FAILED"
    assert result.observed_facts[-1].evidence_id == "E0002"
    assert result.possible_causes[0].is_hypothesis is True
    assert result.tools_used == ["get_inspection_result", "get_execution_logs"]


def test_warning_hypotheses_need_observed_warning_not_just_selected_code():
    service, generator, state, catalog, payload, core, storage = setup_report(
        {"image_quality_status": "WARNING_LOW_BRIGHTNESS", "final_result": "REINSPECT", "final_reason_code": "IMAGE_QUALITY_WARNING"})
    payload["possible_causes"] = ["ILLUMINATION_CHANGE:" + core["image_quality_status"]]
    payload["recommended_checks"].append("LIGHTING_EXPOSURE_CHECK:" + core["image_quality_status"])
    result = verify_simple_report(json.dumps(payload), service, state, catalog)
    assert result.possible_causes[0].is_hypothesis is True
    assert result.inspection_snapshot["final_result"] == "REINSPECT"


@pytest.mark.parametrize("limit", ["entries", "bytes", "report"])
def test_size_limits_fail_closed_without_trimming_evidence_or_retrying(limit):
    service, generator, state, catalog, payload, core, storage = setup_report()
    with pytest.raises(AgentFailure) as failure:
        if limit == "entries":
            build_catalog(state, max_entries=1)
        elif limit == "bytes":
            build_catalog(state, max_bytes=1)
        else:
            convert_simple_report("x" * 65537, state, catalog)
    assert failure.value.code == "CONTEXT_TOO_LARGE"
    generator.assert_not_called()


def test_missing_or_forged_evidence_is_not_given_catalog_tokens():
    with pytest.raises(AgentFailure) as failure:
        build_catalog(RequestState("INSP-000001"))
    assert failure.value.code == "INSUFFICIENT_EVIDENCE"
    service, generator, state, catalog, payload, core, storage = setup_report()
    state.evidence["E0001"][1]["metadata"]["evidence_id"] = "E9999"
    with pytest.raises(AgentFailure) as failure:
        build_catalog(state)
    assert failure.value.code == "EVIDENCE_MISMATCH"


def test_original_service_still_uses_its_full_schema_and_safe_failure_contract():
    storage = Mock(spec=InspectionStorageBase)
    storage.get_inspection.return_value = make_record()
    failure = errors.ClientError(400, {"error": {"status": "INVALID_ARGUMENT", "message": "PRIVATE"}})
    service, generator = service_for(storage, [call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})), failure])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "GEMINI_REQUEST_FAILED" and generator.await_count == 2
    assert generator.call_args_list[-1].kwargs["config"].response_json_schema != simple_output_schema()
    assert result.tools_used == ["get_inspection_result"]
    assert "PRIVATE" not in result.model_dump_json()
