"""Offline comparison of current warning investigation and a non-operating stop policy."""

import asyncio
import copy
from contextlib import contextmanager, nullcontext
import json
from unittest.mock import Mock, patch

from google.genai import _api_client, errors, types
import pytest

from backend.agent.api import get_agent_service
from backend.agent.schemas import AgentLimits
from backend.agent.service import AgentFailure, AgentService, CORE_FIELDS, LIMITATION_TEXT, RequestState, _normal_evidence_ready
from backend.main import app
from backend.storage import InspectionStorageBase
from scripts.agent_warning_policy_experiment import warning_evidence_ready, warning_report_covered
from tests.test_agent_api import file_hashes, harness, prohibit_real_sdk_client
from tests.test_agent_reporting_integration import simple_payload
from tests.test_agent_service import call_response, normal_responses, service_for, text_response
from tests.test_agent_tools import make_log, make_record
from tests.agent_error_fixtures import error_logs, error_record


REQUIRED_EVENTS = ("ANALYSIS_COMPLETED", "INSPECTION_COMPLETED")


@pytest.fixture(autouse=True)
def offline_only():
    with patch("google.genai.Client", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(_api_client.BaseApiClient, "request", side_effect=AssertionError("NETWORK_FORBIDDEN")) as sync_request, \
         patch.object(_api_client.BaseApiClient, "async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")) as async_request:
        yield
        sync_request.assert_not_called()
        async_request.assert_not_called()


def warning_storage(**changes):
    metrics = {"mean": 80.0, "std": 50.0, "min": 10.0, "max": 150.0,
               "width": 900, "height": 900, "channels": 3}
    record = make_record(image_quality_status="WARNING_LOW_BRIGHTNESS", final_result="REINSPECT",
        final_reason_code="IMAGE_QUALITY_WARNING", metrics=metrics)
    record = record.model_copy(update=changes)
    storage = Mock(spec=InspectionStorageBase)
    storage.get_inspection.return_value = record
    storage.get_logs.return_value = [
        make_log(event_code="ANALYSIS_COMPLETED", stage="analyze", level="WARN", metrics=metrics),
        make_log(event_code="INSPECTION_COMPLETED", stage="complete", level="WARN", metrics={
            "image_quality_status": record.image_quality_status, "final_result": record.final_result,
            "final_reason_code": record.final_reason_code}),
    ]
    return storage


def collect_state(storage=None, names=("get_inspection_result", "analyze_image_quality")):
    storage = storage or warning_storage()
    service, generator = service_for(storage, [])
    state = RequestState("INSP-000001")

    async def collect():
        for index, name in enumerate(names, 1):
            await service._execute(types.FunctionCall(name=name, args={"inspection_id": state.inspection_id}), state, index)

    asyncio.run(collect())
    generator.assert_not_called()
    return state, storage


class LegacyWarningAgent(AgentService):
    def _investigation_ready(self, state):
        return _normal_evidence_ready(state)


@contextmanager
def proposed_policy(required_event_codes=()):
    """The constructor now selects the real policy; retain old experiment call sites."""
    yield


def make_service(storage, responses, proposed=False, required_event_codes=(), limits=None):
    service, generator = service_for(storage, responses, limits)
    service_class = AgentService if proposed else LegacyWarningAgent
    service = service_class(service.tools, settings=service.settings, client=service.client, limits=service.limits,
        required_warning_event_codes=required_event_codes)
    return service, generator


def warning_report(**kwargs):
    packet = json.loads(kwargs["contents"][0].parts[0].text)
    payload = simple_payload(kwargs)
    selected = [entry for entry in packet["catalog"] if entry["source_tool"] == "analyze_image_quality"]
    payload["observed_fact_refs"].extend(entry["token"] for entry in selected)
    quality = next(entry["token"] for entry in selected if entry["source_field"] == "/data/image_quality_status")
    payload["possible_causes"] = ["ILLUMINATION_CHANGE:" + quality]
    payload["recommended_checks"] = ["LIGHTING_EXPOSURE_CHECK:" + quality]
    payload["observed_fact_refs"].extend(entry["token"] for entry in packet["catalog"]
        if entry["source_tool"] == "get_execution_logs" and entry["source_field"].endswith(("/stage", "/timestamp")))
    return text_response(json.dumps(payload))


def calls(include_logs=False):
    names = ["get_inspection_result", "analyze_image_quality", *(["get_execution_logs"] if include_logs else [])]
    return [call_response((name, {"inspection_id": "INSP-000001"}), signature=b"offline-signature") for name in names]


def test_two_evidence_records_are_sufficient_without_fabricating_thresholds():
    state, storage = collect_state()
    before = copy.deepcopy((state.snapshot, state.evidence, state.trace))
    assert warning_evidence_ready(state)
    assert not _normal_evidence_ready(state)
    assert state.evidence["E0002"][1]["data"]["threshold_status"] == "NOT_RECORDED"
    assert state.evidence["E0002"][1]["data"]["brightness_thresholds"] is None
    assert (state.snapshot, state.evidence, state.trace) == before
    storage.save_inspection.assert_not_called()
    storage.save_logs.assert_not_called()


@pytest.mark.parametrize("field,value", [("status", "FAILED"), ("result", "UNKNOWN"), ("result", "NG"),
    ("image_quality_status", None), ("image_quality_status", "NORMAL"), ("defect_detection_status", "FAILED"),
    ("final_result", "ERROR"), ("final_reason_code", None), ("final_reason_code", "UNKNOWN_STATE_COMBINATION"),
    ("anomaly_score", None), ("anomaly_score", 40.0), ("decision_threshold", None)])
def test_other_or_incomplete_states_do_not_use_warning_shortcut(field, value):
    state, storage = collect_state(warning_storage(**{field: value}))
    assert not warning_evidence_ready(state)


@pytest.mark.parametrize("mutation", ["mean_missing", "std_missing", "min_missing", "max_missing", "size_missing",
    "wrong_id", "metadata_id", "evidence_id", "trace_id", "trace_not_executed", "trace_failed", "trace_scope",
    "missing_result", "missing_quality", "inconsistent_metric", "inconsistent_status", "threshold_unspecified",
    "not_recorded_with_values", "snapshot_id", "snapshot_metric", "unknown_required_event"])
def test_insufficient_or_tampered_evidence_fails_closed(mutation):
    state, storage = collect_state()
    quality = state.evidence["E0002"][1]["data"]
    if mutation.endswith("_missing"):
        quality["metrics"].pop({"size_missing": "width"}.get(mutation, mutation.split("_")[0]))
    elif mutation == "wrong_id":
        quality["inspection_id"] = "INSP-000002"
    elif mutation == "metadata_id":
        state.evidence["E0002"][1]["metadata"]["evidence_id"] = "E9999"
    elif mutation == "evidence_id":
        state.evidence["E9999"] = state.evidence.pop("E0002")
    elif mutation == "trace_id":
        state.trace[1].evidence_id = "E9999"
    elif mutation == "trace_not_executed":
        state.trace[1].executed = False
    elif mutation == "trace_failed":
        state.trace[1].success = False
    elif mutation == "trace_scope":
        state.trace[1].arguments["inspection_id"] = "INSP-000002"
    elif mutation in {"missing_result", "missing_quality"}:
        state.evidence.pop("E0001" if mutation == "missing_result" else "E0002")
    elif mutation == "inconsistent_metric":
        quality["metrics"]["mean"] += 1
    elif mutation == "inconsistent_status":
        quality["image_quality_status"] = "NORMAL"
    elif mutation == "threshold_unspecified":
        quality["threshold_status"] = None
    elif mutation == "not_recorded_with_values":
        quality["brightness_thresholds"] = {"low_threshold": 100.0, "high_threshold": 160.0}
    elif mutation == "snapshot_id":
        state.snapshot["inspection_id"] = "INSP-000002"
    elif mutation == "snapshot_metric":
        state.snapshot["metrics"]["mean"] = None
    required = ("IMAGE_LOAD_FAILED",) if mutation == "unknown_required_event" else ()
    assert not warning_evidence_ready(state, required_event_codes=required)


@pytest.mark.parametrize("warning,mean,expected", [("WARNING_LOW_BRIGHTNESS", 80.0, True),
    ("WARNING_LOW_BRIGHTNESS", 130.0, False), ("WARNING_HIGH_BRIGHTNESS", 200.0, True),
    ("WARNING_HIGH_BRIGHTNESS", 130.0, False)])
def test_recorded_thresholds_must_support_the_warning(warning, mean, expected):
    storage = warning_storage()
    record = storage.get_inspection.return_value
    record.image_quality_status = warning
    record.metrics.update(mean=mean, max=240.0, applied_thresholds={"low_threshold": 100.0, "high_threshold": 160.0})
    state, storage = collect_state(storage)
    assert warning_evidence_ready(state) is expected


@pytest.mark.parametrize("mutation", ["missing", "event_missing", "stage", "time", "error", "metric", "final_conflict"])
def test_required_events_are_not_skipped_or_inferred(mutation):
    state, storage = collect_state(names=("get_inspection_result", "analyze_image_quality", "get_execution_logs"))
    events = state.evidence["E0003"][1]["data"]
    if mutation == "missing":
        state.evidence.pop("E0003")
    elif mutation == "event_missing":
        events.pop()
    elif mutation == "stage":
        events[0]["stage"] = "load"
    elif mutation == "time":
        events[0]["timestamp"] = None
    elif mutation == "error":
        events[0]["level"] = "ERROR"
    elif mutation == "metric":
        events[0]["metrics"]["mean"] = 90.0
    else:
        events[1]["metrics"]["final_result"] = "OK"
    assert not warning_evidence_ready(state, required_event_codes=REQUIRED_EVENTS)


def test_required_event_policy_continues_until_actual_logs_are_available():
    state, storage = collect_state()
    assert not warning_evidence_ready(state, required_event_codes=REQUIRED_EVENTS)
    state, storage = collect_state(storage, ("get_inspection_result", "analyze_image_quality", "get_execution_logs"))
    assert warning_evidence_ready(state, required_event_codes=REQUIRED_EVENTS)


@pytest.mark.parametrize("required_logs", [False, True])
def test_current_and_proposed_paths_keep_evidence_but_remove_one_readiness_round(required_logs):
    storage = warning_storage()
    required = REQUIRED_EVENTS if required_logs else ()
    original_record = storage.get_inspection.return_value.model_dump()
    current, current_generator = make_service(storage, [*calls(required_logs), text_response(), warning_report])
    current_result = asyncio.run(current.analyze("INSP-000001"))
    proposed, proposed_generator = make_service(storage, [*calls(required_logs), warning_report], True, required)
    with proposed_policy(required):
        proposed_result = asyncio.run(proposed.analyze("INSP-000001"))
    assert current_result.analysis_status == proposed_result.analysis_status == "COMPLETED"
    assert current_generator.await_count == (5 if required_logs else 4)
    assert proposed_generator.await_count == (4 if required_logs else 3)
    assert current_result.inspection_snapshot == proposed_result.inspection_snapshot
    assert current_result.observed_facts == proposed_result.observed_facts
    assert proposed_result.inspection_snapshot["result"] == "OK"
    assert proposed_result.inspection_snapshot["final_result"] == "REINSPECT"
    assert proposed_result.tools_used == ["get_inspection_result", "analyze_image_quality", *(["get_execution_logs"] if required_logs else [])]
    assert all(trace.executed and trace.success for trace in proposed_result.tool_execution_trace)
    assert LIMITATION_TEXT["MISSING_BRIGHTNESS_THRESHOLDS"] in proposed_result.limitations
    assert storage.get_inspection.return_value.model_dump() == original_record
    storage.save_inspection.assert_not_called()
    storage.save_logs.assert_not_called()


def test_proposed_final_report_keeps_actual_core_and_brightness_coverage():
    service, generator = make_service(warning_storage(), [*calls(), warning_report], True)
    with proposed_policy():
        result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    assert len(result.observed_facts) > len(CORE_FIELDS)
    packets = [call.kwargs for call in generator.call_args_list]
    assert [content.role for content in packets[1]["contents"]] == ["user", "model", "user"]
    assert packets[1]["contents"][1].parts[0].thought_signature == b"offline-signature"
    call = packets[1]["contents"][1].parts[0].function_call
    response = packets[1]["contents"][2].parts[0].function_response
    assert (response.name, response.id) == (call.name, call.id)
    final = packets[-1]
    assert [content.role for content in final["contents"]] == ["user"]
    assert final["config"].response_mime_type == "application/json"
    assert final["config"].tools is None and final["config"].tool_config is None
    assert final["config"].http_options.retry_options.attempts == 1
    assert service.limits.max_tool_rounds == 4 and service.limits.max_tool_calls == 8
    assert service.limits.model_timeout_seconds == 15 and service.limits.request_timeout_seconds == 60


@pytest.mark.parametrize("missing", ["mean", "threshold_status", "core", "quality_all", "required_logs", "log_stage"])
def test_proposed_stop_never_hides_incomplete_final_explanations(missing):
    def incomplete(**kwargs):
        payload = simple_payload(kwargs) if missing in {"core", "quality_all"} else json.loads(warning_report(**kwargs).candidates[0].content.parts[0].text)
        if missing in {"mean", "threshold_status", "log_stage"}:
            packet = json.loads(kwargs["contents"][0].parts[0].text)
            pointer = "/data/metrics/mean" if missing == "mean" else "/data/threshold_status"
            removed = {entry["token"] for entry in packet["catalog"] if (
                entry["source_tool"] == "get_execution_logs" and entry["source_field"].endswith("/stage")
                if missing == "log_stage" else entry["source_tool"] == "analyze_image_quality" and entry["source_field"] == pointer)}
            payload["observed_fact_refs"] = [token for token in payload["observed_fact_refs"] if token not in removed]
        if missing == "core":
            payload["observed_fact_refs"].pop()
        return text_response(json.dumps(payload))

    required = REQUIRED_EVENTS if missing in {"required_logs", "log_stage"} else ()
    responses = [*calls(missing == "log_stage"), *([text_response()] if missing == "required_logs" else []), incomplete]
    service, generator = make_service(warning_storage(), responses, True, required)
    with proposed_policy(required):
        result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "FAILED" and result.error_code == "EVIDENCE_MISMATCH"
    assert result.observed_facts == []


@pytest.mark.parametrize("proposed", [False, True])
def test_third_server_504_keeps_safe_http_502_and_data(harness, proposed):
    storage = warning_storage()
    harness.storage.save_inspection(storage.get_inspection.return_value)
    failure = errors.ServerError(504, {"error": {"code": 504, "status": "DEADLINE_EXCEEDED", "message": "PRIVATE"}})
    service, generator = make_service(harness.storage, [*calls(), failure], proposed)
    app.dependency_overrides[get_agent_service] = lambda: service
    before = file_hashes(harness)
    with proposed_policy() if proposed else nullcontext():
        response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 502 and response.json()["detail"]["error_code"] == "GEMINI_REQUEST_FAILED"
    assert generator.await_count == 3 and "PRIVATE" not in response.text
    assert generator.call_args_list[2].kwargs["config"].response_mime_type == ("application/json" if proposed else None)
    assert [content.role for content in generator.call_args_list[2].kwargs["contents"]] == (
        ["user"] if proposed else ["user", "model", "user", "model", "user"])
    assert file_hashes(harness) == before


@pytest.mark.parametrize("proposed", [False, True])
def test_identical_tool_repeat_limit_still_fails_without_fake_success(proposed):
    first = call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}))
    service, generator = make_service(warning_storage(), [first, first, first], proposed)
    with proposed_policy() if proposed else nullcontext():
        result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "TOOL_REPEAT_LIMIT" and generator.await_count == 3
    assert [trace.executed for trace in result.tool_execution_trace] == [True, True, False]


@pytest.mark.parametrize("record_id", ["IMG-BOTTLE-0001", "IMG-BOTTLE-0002"])
def test_t01_and_stored_ok_keep_existing_normal_shortcut_not_warning_policy(record_id):
    storage = warning_storage()
    storage.get_inspection.return_value = make_record(image_id=record_id)
    state, storage = collect_state(storage, ("get_inspection_result",))
    assert _normal_evidence_ready(state) and not warning_evidence_ready(state)
    service, generator = make_service(storage, normal_responses(), True)
    with proposed_policy():
        result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and generator.await_count == 2
    assert result.tools_used == ["get_inspection_result"]


def test_proposed_policy_does_not_hide_timeout_in_the_final_request():
    service, generator = make_service(warning_storage(), [*calls(), TimeoutError()], True)
    with proposed_policy():
        result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "GEMINI_TIMEOUT" and generator.await_count == 3
    assert generator.call_args_list[-1].kwargs["config"].response_mime_type == "application/json"


def test_t05_workflow_failure_still_requires_its_own_investigation_path():
    storage = warning_storage(status="FAILED", result="UNKNOWN", image_quality_status="ERROR",
        defect_detection_status="SKIPPED", final_result="ERROR", final_reason_code="INSPECTION_FAILED", anomaly_score=None)
    storage.get_inspection.return_value = error_record()
    storage.get_logs.return_value = error_logs()
    state, storage = collect_state(storage, ("get_inspection_result", "get_execution_logs"))
    assert not warning_evidence_ready(state) and not _normal_evidence_ready(state)

    def final(**kwargs):
        return text_response(json.dumps(simple_payload(kwargs)))

    service, generator = make_service(storage, [
        call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})),
        call_response(("get_execution_logs", {"inspection_id": "INSP-000001"})), final,
    ], True)
    with proposed_policy():
        result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and generator.await_count == 3
    assert result.inspection_snapshot["result"] == "UNKNOWN" and result.inspection_snapshot["final_result"] == "ERROR"


@pytest.mark.parametrize("limits,error", [(AgentLimits(max_tool_rounds=1), "TOOL_ROUND_LIMIT"),
    (AgentLimits(max_tool_calls=1), "TOOL_CALL_LIMIT")])
def test_proposed_policy_preserves_explicit_round_and_tool_budgets(limits, error):
    service, generator = make_service(warning_storage(), calls(), True, limits=limits)
    with proposed_policy():
        result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == error and result.analysis_status == "FAILED"
    assert generator.await_count == 2 and result.tools_used == ["get_inspection_result"]
