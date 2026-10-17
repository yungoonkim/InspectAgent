"""Offline comparison of native investigation and independent report requests."""

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from google.genai import _api_client, _common, models as sdk_models, types
import pytest

from backend.agent.prompts import REPORT_SYSTEM_INSTRUCTION, SYSTEM_INSTRUCTION
from backend.agent.schemas import AgentLimits, diagnosis_response_json_schema
from backend.agent.reporting import simple_output_schema
from backend.agent.service import AgentFailure, PRODUCT_ALIAS, RequestState, _report_contents, function_declarations
from backend.agent.tools import InspectionTools
from backend.storage import InspectionStorageBase
from tests.test_agent_service import report_response, call_response, normal_responses, report_payload, service_for, text_response, with_quality_facts
from tests.test_agent_tools import make_log, make_record
from tests.agent_error_fixtures import error_logs, error_record, with_error_facts


@pytest.fixture(autouse=True)
def no_network():
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
    instance.get_logs.return_value = [make_log()]
    instance.list_inspections.return_value = [make_record()]
    return instance


def serialize(contents, schema):
    config = types.GenerateContentConfig(
        system_instruction=REPORT_SYSTEM_INSTRUCTION, response_mime_type="application/json",
        response_json_schema=schema, temperature=0, candidate_count=1,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    parameters = types._GenerateContentParameters(model="gemini-mock", contents=contents, config=config)
    converted = sdk_models._GenerateContentParameters_to_mldev(SimpleNamespace(vertexai=False), parameters)
    return _common.encode_unserializable_types(_common.convert_to_dict(converted))


@pytest.mark.parametrize("case", ["simple", "full", "function_call", "function_response", "evidence"])
def test_five_request_shapes_serialize_without_proving_server_acceptance(storage, case):
    service, generator = service_for(storage, normal_responses())
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    schema = diagnosis_response_json_schema()
    contents = [types.Content(role="user", parts=[types.Part.from_text(text="Create a report.")])]
    if case == "simple":
        schema = {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}
    if case in {"function_call", "function_response"}:
        model = call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}),
                              signature=b"offline-signature").candidates[0].content
        contents.append(model)
        if case == "function_response":
            document = {"ok": True, "data": {"result": storage.get_inspection.return_value.result}}
            contents.append(types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
                name=model.parts[0].function_call.name, id=model.parts[0].function_call.id, response=document,
            ))]))
    if case == "evidence":
        contents = generator.call_args_list[-1].kwargs["contents"]
    wire = serialize(contents, schema)
    assert wire["generationConfig"]["responseJsonSchema"] == schema
    assert "tools" not in wire and "toolConfig" not in wire
    assert "responseSchema" not in wire["generationConfig"]
    assert "additional_properties" not in json.dumps(wire)
    assert [item["role"] for item in wire["contents"]] == (
        ["user", "model"] if case == "function_call" else
        ["user", "model", "user"] if case == "function_response" else ["user"]
    )
    if case == "evidence":
        assert set(wire["contents"][0]["parts"][0]) == {"text"}
    json.dumps(wire, allow_nan=False)


def test_report_uses_actual_server_evidence_and_safe_provenance_not_generated_text(storage):
    record = make_record(final_reason_code=None, product_id="PRIVATE-PRODUCT", image_id="PRIVATE-IMAGE")
    storage.get_inspection.return_value = record
    storage.get_logs.return_value = [make_log(message="UNTRUSTED-LOG-COMMAND", metrics={"private": "PRIVATE-METRIC"})]
    first = call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}),
                          ("get_execution_logs", {"inspection_id": "INSP-000001"}), signature=b"PRIVATE-SIGNATURE")
    first.candidates[0].content.parts.insert(0, types.Part(text="PRIVATE-MODEL-THOUGHT", thought=True))
    service, generator = service_for(storage, [first, text_response("UNTRUSTED-MODEL-INSTRUCTION"),
                                              report_response(report_payload(record))])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    native = generator.call_args_list[1].kwargs["contents"]
    assert native[1] is first.candidates[0].content
    assert native[1].parts[1].thought_signature == b"PRIVATE-SIGNATURE"
    for call_part, response_part in zip(native[1].parts[1:], native[2].parts):
        assert (call_part.function_call.name, call_part.function_call.id) == (
            response_part.function_response.name, response_part.function_response.id,
        )
    text = generator.call_args_list[-1].kwargs["contents"][0].parts[0].text
    envelope = json.loads(text)
    for identifier, response_part in zip(("E0001", "E0002"), native[2].parts):
        entries = [entry for entry in envelope["catalog"] if entry["evidence_id"] == identifier]
        assert entries and all(entry["source_tool"] == response_part.function_response.name for entry in entries)
        for entry in entries:
            observed = response_part.function_response.response
            for component in entry["source_field"].split("/")[1:]:
                observed = observed[int(component)] if isinstance(observed, list) else observed[component]
            assert observed == entry["observed_value"]
    assert all(not entry["source_field"].endswith("/product_id") for entry in envelope["catalog"])
    expected_keys = {"sequence", "tool_name", "executed", "success", "error_code", "evidence_id", "origin", "comparison_inspection_id"}
    for entry, trace in zip(envelope["tool_execution_trace"], result.tool_execution_trace):
        assert set(entry) == expected_keys
        assert entry == {name: getattr(trace, name) for name in expected_keys}
    for forbidden in ("PRIVATE-PRODUCT", "PRIVATE-IMAGE", "PRIVATE-SIGNATURE", "PRIVATE-MODEL-THOUGHT",
                      "UNTRUSTED-MODEL-INSTRUCTION", "UNTRUSTED-LOG-COMMAND", "PRIVATE-METRIC"):
        assert forbidden not in text
    storage.save_inspection.assert_not_called()
    storage.save_logs.assert_not_called()


def test_decoded_report_packet_cannot_mutate_server_evidence(storage):
    service, generator = service_for(storage, [])
    state = RequestState("INSP-000001")
    call = types.FunctionCall(name="get_inspection_result", args={"inspection_id": state.inspection_id})
    asyncio.run(service._execute(call, state, 1))
    original = copy.deepcopy(state.evidence)
    contents = _report_contents(state)
    envelope = json.loads(contents[0].parts[0].text)
    next(entry for entry in envelope["catalog"] if entry["source_field"] == "/data/result")["observed_value"] = "NG"
    envelope["tool_execution_trace"][0]["success"] = False
    assert state.evidence == original
    assert state.snapshot["result"] == "OK"
    assert state.trace[0].success is True
    generator.assert_not_called()


def test_report_excludes_private_evaluation_fields_from_stored_metrics(storage):
    record = make_record(metrics={"mean": 138.37, "ground_truth": "OFFLINE-ONLY-LABEL",
                                 "injection_factor": 0.25, "source_path": "PRIVATE-SOURCE"})
    storage.get_inspection.return_value = record
    before = record.model_dump()
    service, generator = service_for(storage, normal_responses(report_payload(record)))
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    contents = generator.call_args_list[-1].kwargs["contents"]
    text = contents[0].parts[0].text
    for forbidden in ("ground_truth", "OFFLINE-ONLY-LABEL", "injection_factor", "source_path", "PRIVATE-SOURCE"):
        assert forbidden not in text
    envelope = json.loads(text)
    assert next(entry for entry in envelope["catalog"] if entry["source_field"] == "/data/metrics/mean")["observed_value"] == 138.37
    assert record.model_dump() == before


@pytest.mark.parametrize("mutation", ["evidence_id", "source_tool", "source_field", "observed_value", "inspection_id", "overall_summary"])
def test_report_claims_remain_deterministically_bound_to_server_evidence(storage, mutation):
    payload = report_payload()
    if mutation in {"inspection_id", "overall_summary"}:
        payload[mutation] = "INSP-000002" if mutation == "inspection_id" else "PRODUCT_ANOMALY"
    else:
        payload["observed_facts"][0][mutation] = {
            "evidence_id": "E9999", "source_tool": "analyze_image_quality",
            "source_field": "/data/unrecorded", "observed_value": "FAILED",
        }[mutation]
    service, generator = service_for(storage, normal_responses(payload))
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "FAILED"
    assert result.error_code == ("RESPONSE_SCHEMA_INVALID" if mutation == "inspection_id" else "EVIDENCE_MISMATCH")
    assert result.observed_facts == []
    assert result.tool_execution_trace[0].success
    assert generator.await_count == 2


@pytest.mark.parametrize("mutation", ["history", "model_role", "signature", "multiple_parts", "function_response"])
def test_structured_stage_rejects_non_text_or_conversation_content_before_sdk(storage, mutation):
    contents = [types.Content(role="user", parts=[types.Part.from_text(text="{}")])]
    if mutation == "history":
        contents.extend([types.Content(role="model", parts=[types.Part.from_text(text="Ready")]),
                         types.Content(role="user", parts=[types.Part.from_text(text="{}")])])
    elif mutation == "model_role":
        contents[0].role = "model"
    elif mutation == "signature":
        contents[0].parts[0].thought_signature = b"offline-signature"
    elif mutation == "multiple_parts":
        contents[0].parts.append(types.Part.from_text(text="extra"))
    else:
        contents[0].parts = [types.Part.from_function_response(name="get_inspection_result", response={"ok": True})]
    service, generator = service_for(storage, [])
    with pytest.raises(AgentFailure) as failure:
        asyncio.run(service._generate(service.client, "gemini-mock", contents, RequestState("INSP-000001"), 2, structured=True))
    assert failure.value.code == "MODEL_RESPONSE_INVALID"
    generator.assert_not_called()


@pytest.mark.parametrize("state", [RequestState("INSP-000001"), RequestState("INSP-000001", snapshot={})])
def test_report_packet_requires_actual_collected_evidence(state):
    with pytest.raises(AgentFailure) as failure:
        _report_contents(state)
    assert failure.value.code == "INSUFFICIENT_EVIDENCE"


def test_report_config_has_no_leftover_tools_or_investigation_instruction(storage):
    service, generator = service_for(storage, normal_responses())
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    first, final = [call.kwargs for call in generator.call_args_list]
    assert first["config"].system_instruction == SYSTEM_INSTRUCTION
    assert len(first["config"].tools[0].function_declarations) == 4
    assert first["config"].tool_config.function_calling_config.mode == "AUTO"
    config = final["config"]
    assert config.system_instruction == REPORT_SYSTEM_INSTRUCTION
    assert "Request get_inspection_result" not in config.system_instruction
    assert config.tools is None and config.tool_config is None and config.thinking_config is None
    assert config.response_schema is None
    assert config.response_json_schema == simple_output_schema()
    assert config.http_options.retry_options.attempts == 1
    assert config.http_options.timeout == 15000
    assert service.limits == AgentLimits()
    assert {declaration.name for declaration in function_declarations()} == set(result.tools_used) | {
        "get_execution_logs", "analyze_image_quality", "get_inspection_history",
    }


def test_independent_report_packet_keeps_payload_limit_before_sdk(storage):
    service, generator = service_for(storage, [], AgentLimits(max_payload_bytes=1024))
    state = RequestState("INSP-000001")
    asyncio.run(service._execute(types.FunctionCall(name="get_inspection_result",
        args={"inspection_id": state.inspection_id}), state, 1))
    with pytest.raises(AgentFailure) as failure:
        asyncio.run(service._generate(service.client, "gemini-mock", _report_contents(state), state, 2, structured=True))
    assert failure.value.code == "CONTEXT_TOO_LARGE"
    generator.assert_not_called()
    assert state.trace[0].executed and state.trace[0].success


@pytest.mark.parametrize("scenario", ["T01", "T03", "T05", "T06"])
def test_scenario_mocks_keep_investigation_verdicts_and_independent_report(storage, scenario):
    changes = {}
    additional = None
    summary = "NORMAL_MODEL_RESULT"
    if scenario == "T03":
        changes = {"image_quality_status": "WARNING_LOW_BRIGHTNESS", "final_result": "REINSPECT",
                   "final_reason_code": "IMAGE_QUALITY_WARNING"}
        additional, summary = "analyze_image_quality", "REINSPECTION_REQUIRED"
    elif scenario == "T05":
        changes = {"status": "FAILED", "result": "UNKNOWN", "image_quality_status": "ERROR",
                   "defect_detection_status": "SKIPPED", "final_result": "ERROR",
                   "final_reason_code": "INSPECTION_FAILED", "anomaly_score": None}
        additional, summary = "get_execution_logs", "INSPECTION_FAILED"
        storage.get_logs.return_value = [make_log(event_code="IMAGE_LOAD_FAILED")]
    record = make_record(**changes)
    if scenario == "T05":
        record = error_record()
        storage.get_logs.return_value = error_logs()
    storage.get_inspection.return_value = record
    original = record.model_dump()
    payload = report_payload(record, summary)
    if additional:
        payload["recommended_checks"] = [{"check_code": "MANUAL_REINSPECTION", "evidence_refs": ["F0005"]}]
        payload["observed_facts"].append({
            "fact_id": "F0007", "evidence_id": "E0002", "source_tool": additional,
            "source_field": "/data/image_quality_status" if scenario == "T03" else "/data/0/event_code",
            "observed_value": "WARNING_LOW_BRIGHTNESS" if scenario == "T03" else "IMAGE_LOAD_FAILED",
            "source_event": None if scenario == "T03" else "IMAGE_LOAD_FAILED",
        })
    responses = [call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}))]
    if additional:
        responses.append(call_response((additional, {"inspection_id": "INSP-000001"})))
        if scenario == "T03":
            payload = with_quality_facts(payload, record)
        else:
            payload = with_error_facts(payload, record)
    responses.append(report_response(payload))
    service, generator = service_for(storage, responses)
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    assert result.inspection_snapshot["result"] == record.result
    assert result.inspection_snapshot["final_result"] == record.final_result
    assert result.inspection_snapshot["final_reason_code"] == record.final_reason_code
    assert record.model_dump() == original
    assert generator.await_count == (3 if additional else 2)
    final = generator.call_args_list[-1].kwargs
    assert [item.role for item in final["contents"]] == ["user"]
    envelope = json.loads(final["contents"][0].parts[0].text)
    evidence_ids = {entry["evidence_id"] for entry in envelope["catalog"]}
    assert evidence_ids == {entry.evidence_id for entry in result.tool_execution_trace if entry.success}
    assert {fact.evidence_id for fact in result.observed_facts} <= evidence_ids
    storage.save_inspection.assert_not_called()
    storage.save_logs.assert_not_called()
