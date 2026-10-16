"""Narrow image-loading failure completion with real validators and offline transport."""

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import patch

from google.genai import _common, models, types
import httpx
import pytest

from backend.agent import error_policy, service as operating
from backend.agent.error_policy import error_required_facts, image_load_failure_evidence_ready
from backend.agent.schemas import AgentLimits
from tests.test_agent_error_policy import draft_for, verify
from tests.test_agent_service import call_response, service_for, text_response
from tests.test_agent_t05_preflight import (
    collect_state, failed_storage, final_report, prohibit_external_calls, responses_with_logs,
)
from tests.test_agent_tools import make_log


def test_ready_uses_existing_required_facts_without_mutating_evidence(failed_storage):
    service, state = collect_state(failed_storage)
    before = copy.deepcopy(state)
    assert len(error_required_facts(state)) == 17
    with patch.object(error_policy, "error_required_facts", wraps=error_required_facts) as required:
        assert image_load_failure_evidence_ready(state)
        required.assert_called_once_with(state)
    assert service._investigation_ready(state)
    assert state == before
    assert verify(service, state, draft_for(state)).analysis_status == "COMPLETED"


@pytest.mark.parametrize("failure", [operating.AgentFailure("INSUFFICIENT_EVIDENCE"), RuntimeError("OFFLINE")])
def test_updated_or_unavailable_validator_cannot_be_bypassed(failed_storage, failure):
    service, state = collect_state(failed_storage)
    with patch.object(error_policy, "error_required_facts", side_effect=failure):
        assert not image_load_failure_evidence_ready(state)
        assert not service._investigation_ready(state)


@pytest.mark.parametrize("mutation", [
    "no_snapshot", "invalid_snapshot", "wrong_id", "wrong_record_id", "no_record", "no_logs",
    "no_trace", "wrong_trace_id", "wrong_metadata", "unexecuted", "failed", "trace_error",
    "orphan_trace", "wrong_tool", "missing_field", "wrong_type", "measured_score", "measured_mean",
    "missing_load", "missing_failure", "invalid_time", "reversed_time", "wrong_stage", "wrong_level",
    "inference_failure", "unknown_error", "unknown_only", "skipped_only",
])
def test_incomplete_or_ambiguous_state_never_stops(failed_storage, mutation):
    service, state = collect_state(failed_storage)
    if mutation == "no_snapshot":
        state.snapshot = None
    elif mutation == "invalid_snapshot":
        state.snapshot = []
    elif mutation == "wrong_id":
        state.inspection_id = "INSP-000002"
    elif mutation == "wrong_record_id":
        state.snapshot["inspection_id"] = "INSP-000002"
    elif mutation in {"no_record", "no_logs"}:
        state.evidence.pop("E0001" if mutation == "no_record" else "E0002")
    elif mutation == "no_trace":
        state.trace.clear()
    elif mutation == "wrong_trace_id":
        state.trace[-1].arguments = {"inspection_id": "INSP-000002"}
    elif mutation == "wrong_metadata":
        state.evidence["E0002"][1]["metadata"]["evidence_id"] = "E9999"
    elif mutation == "unexecuted":
        state.trace[-1].executed = False
    elif mutation == "failed":
        state.trace[-1].success = False
    elif mutation == "trace_error":
        state.trace[-1].error_code = "DATA_UNAVAILABLE"
    elif mutation == "orphan_trace":
        state.trace.append(state.trace[-1].model_copy(update={"sequence": 3, "evidence_id": "E0003"}))
    elif mutation == "wrong_tool":
        state.evidence["E0002"] = ("analyze_image_quality", state.evidence["E0002"][1])
    elif mutation == "missing_field":
        state.snapshot.pop("inference_time_ms")
    elif mutation == "wrong_type":
        state.snapshot["metrics"] = []
    elif mutation == "measured_score":
        state.snapshot["anomaly_score"] = 0
    elif mutation == "measured_mean":
        state.snapshot["metrics"]["mean"] = 0
    elif mutation in {"unknown_only", "skipped_only"}:
        state.evidence.pop("E0002")
        state.snapshot = {"result": "UNKNOWN"} if mutation == "unknown_only" else {"defect_detection_status": "SKIPPED"}
    else:
        events = state.evidence["E0002"][1]["data"]
        if mutation in {"missing_load", "missing_failure"}:
            events.pop(1 if mutation == "missing_load" else 2)
        elif mutation == "invalid_time":
            events[1]["timestamp"] = None
        elif mutation == "reversed_time":
            events[1]["timestamp"] = "2026-10-15T00:00:00+00:00"
        elif mutation == "wrong_stage":
            events[1]["stage"] = "inference"
        elif mutation == "wrong_level":
            events[1]["level"] = "INFO"
        else:
            event = copy.deepcopy(events[1])
            event.update(event_code="INFERENCE_FAILED" if mutation == "inference_failure" else "UNSUPPORTED_ERROR", stage="inference")
            events.append(event)
    assert not image_load_failure_evidence_ready(state)
    assert not service._investigation_ready(state)


def test_extra_investigation_contract_or_tool_is_not_silently_discarded(failed_storage):
    service, state = collect_state(failed_storage)
    service.required_warning_event_codes = ("INSPECTION_COMPLETED",)
    assert image_load_failure_evidence_ready(state)
    assert not service._investigation_ready(state)
    service, state = collect_state(failed_storage, with_quality=True)
    assert not image_load_failure_evidence_ready(state)
    assert not service._investigation_ready(state)


@pytest.mark.parametrize("parallel", [False, True])
@pytest.mark.parametrize("final_timeout", [15, 30])
def test_last_function_response_is_local_but_all_evidence_reaches_independent_final(failed_storage, parallel, final_timeout):
    names = ("get_inspection_result", "get_execution_logs")
    responses = [call_response(*[(name, {"inspection_id": "INSP-000001"}) for name in names], signature=b"offline")]
    if not parallel:
        responses = [call_response((name, {"inspection_id": "INSP-000001"}), signature=b"offline") for name in names]
    model_contents = [response.candidates[0].content for response in responses]
    original_models = [content.model_dump() for content in model_contents]
    service, generator = service_for(failed_storage, [*responses, final_report],
        limits=AgentLimits(final_model_timeout_seconds=final_timeout))
    created = []
    states = []
    wires = []
    real_content = types.Content
    original_ready = service._investigation_ready

    def content(**kwargs):
        value = real_content(**kwargs)
        created.append(value)
        return value

    def ready(state):
        states.append(state)
        return original_ready(state)

    def transport(request):
        wires.append(json.loads(request.content))
        return httpx.Response(200, json={"offline": True})

    async def generate(**kwargs):
        parameters = types._GenerateContentParameters(**kwargs)
        wire = _common.encode_unserializable_types(_common.convert_to_dict(
            models._GenerateContentParameters_to_mldev(SimpleNamespace(vertexai=False), parameters)))
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            await client.post("https://mock.invalid/generate", json=wire)
        return await generator(**kwargs)

    service.client.aio.models.generate_content = generate
    service._investigation_ready = ready
    local_types = SimpleNamespace(**vars(types))
    local_types.Content = content
    with patch.object(operating, "types", local_types):
        result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    assert len(wires) == generator.await_count == (2 if parallel else 3)
    assert ["responseJsonSchema" in wire["generationConfig"] for wire in wires] == [False] * len(responses) + [True]
    assert [entry.round_number for entry in result.tool_execution_trace] == ([1, 1] if parallel else [1, 2])
    assert result.tools_used == list(names)
    assert all(entry.executed and entry.success for entry in result.tool_execution_trace)
    state = states[-1]
    required = error_required_facts(state)
    assert len(required) == len(result.observed_facts) == 17
    assert set(state.evidence) == {"E0001", "E0002"}
    replies = [value for value in created if any(part.function_response for part in value.parts)]
    history = [created[0]]
    for model, reply in zip(model_contents, replies):
        history.extend((model, reply))
        assert [(part.function_response.name, part.function_response.id) for part in reply.parts] == [
            (part.function_call.name, part.function_call.id) for part in model.parts if part.function_call]
    operating._validate_history(history)
    assert [content.model_dump() for content in model_contents] == original_models
    assert sum("functionResponse" in part for wire in wires for item in wire["contents"] for part in item["parts"]) == (0 if parallel else 1)
    final = wires[-1]
    assert "tools" not in final and "toolConfig" not in final
    assert len(final["contents"]) == 1 and final["contents"][0]["role"] == "user"
    assert set(final["contents"][0]["parts"][0]) == {"text"}
    packet = json.loads(final["contents"][0]["parts"][0]["text"])
    assert {item["evidence_id"] for item in packet["tool_execution_trace"]} == set(state.evidence)
    for entry in required:
        assert any(all(item[name] == getattr(entry, name) for name in
            ("evidence_id", "source_tool", "source_field", "source_event", "observed_value")) for item in packet["catalog"])
    assert service.limits.request_timeout_seconds == 60
    assert generator.call_args_list[-1].kwargs["config"].http_options.timeout == final_timeout * 1000
    assert all(call.kwargs["config"].http_options.retry_options.attempts == 1 for call in generator.call_args_list)
    failed_storage.save_inspection.assert_not_called()
    failed_storage.save_logs.assert_not_called()


@pytest.mark.parametrize("pointer", ["/data/defect_detection_status", "/data/metrics/mean", "/data/1/event_code"])
def test_early_stop_does_not_bypass_final_required_fact_coverage(failed_storage, pointer):
    def incomplete(**kwargs):
        response = final_report(**kwargs)
        packet = json.loads(kwargs["contents"][0].parts[0].text)
        omitted = next(entry["token"] for entry in packet["catalog"] if entry["source_field"] == pointer)
        payload = json.loads(response.candidates[0].content.parts[0].text)
        payload["observed_fact_refs"].remove(omitted)
        payload["possible_causes"] = []
        payload["recommended_checks"] = ["MANUAL_REINSPECTION:" + next(
            entry["token"] for entry in packet["catalog"] if entry["source_field"] == "/data/final_result")]
        return text_response(json.dumps(payload))

    service, generator = service_for(failed_storage, [*responses_with_logs()[:-1], incomplete])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "EVIDENCE_MISMATCH" and result.analysis_status == "FAILED"
    assert generator.await_count == 3


def test_post_loop_error_guard_remains_even_if_readiness_is_wrong(failed_storage):
    service, generator = service_for(failed_storage, [responses_with_logs()[0]])
    service._investigation_ready = lambda state: True
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "INSUFFICIENT_EVIDENCE"
    assert generator.await_count == 1


@pytest.mark.parametrize("kind", ["generic", "inference"])
def test_other_workflow_failures_still_wait_for_model_stop(failed_storage, kind):
    failed_storage.get_logs.return_value = failed_storage.get_logs.return_value[-1:]
    if kind == "inference":
        failed_storage.get_inspection.return_value = failed_storage.get_inspection.return_value.model_copy(update={
            "defect_detection_status": "FAILED", "image_quality_status": "NORMAL"})
        failed_storage.get_logs.return_value.insert(0, make_log(event_code="INFERENCE_FAILED", stage="inference", level="ERROR", metrics={}))
    service, state = collect_state(failed_storage)
    assert not image_load_failure_evidence_ready(state)
    assert not service._investigation_ready(state)
    service, generator = service_for(failed_storage, responses_with_logs(continue_investigation=True))
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and generator.await_count == 4
