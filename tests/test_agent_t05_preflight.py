"""Offline T05 readiness, current ERROR coverage gaps, and manual preparation."""

import asyncio
from dataclasses import replace
import importlib.util
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import warnings

from google.genai import _api_client, errors, types
import httpx
import pytest

from backend.agent.api import get_agent_service
from backend.agent.reporting import build_catalog, convert_simple_report
from backend.agent.schemas import DiagnosisDraft
from backend.agent.service import AgentFailure, AgentService, CORE_FIELDS, RequestState, _normal_evidence_ready
from backend.agent.tools import InspectionTools
from backend.agent.investigation import warning_evidence_ready
from backend.main import app
from backend.storage import InspectionStorageBase
from scripts.agent_validation_measurements import attempt_paths, prepare_attempt, validate_ready_attempt
from tests.test_agent_api import harness
from tests.test_agent_service import call_response, service_for, text_response
from tests.test_agent_tools import make_log, make_record
from tests.agent_error_fixtures import error_logs, error_tokens


@pytest.fixture(autouse=True)
def prohibit_external_calls():
    with patch("google.genai.Client", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(_api_client.BaseApiClient, "request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(_api_client.BaseApiClient, "async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(httpx.HTTPTransport, "handle_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")):
        yield


@pytest.fixture
def failed_storage():
    storage = Mock(spec=InspectionStorageBase)
    storage.get_inspection.return_value = make_record(status="FAILED", result="UNKNOWN",
        image_quality_status="ERROR", defect_detection_status="SKIPPED", final_result="ERROR",
        final_reason_code="INSPECTION_FAILED", anomaly_score=None, decision_threshold=None,
        inference_time_ms=None, metrics={})
    storage.get_logs.return_value = [
        make_log("2026-10-14T11:07:13.616990Z", event_code="INSPECTION_STARTED", stage="init", metrics={}),
        make_log("2026-10-14T11:07:13.618533Z", event_code="IMAGE_LOAD_FAILED", stage="load", level="ERROR",
            message="PRIVATE_ERROR_MESSAGE", metrics={}),
        make_log("2026-10-14T11:07:13.618533Z", event_code="INSPECTION_FAILED", stage="complete", level="ERROR", metrics={}),
    ]
    return storage


def report_for_catalog(entries, include_logs=True):
    selected = [entry for entry in entries if entry["source_tool"] == "get_inspection_result"
        and entry["source_field"] in {f"/data/{name}" for name in CORE_FIELDS}]
    if include_logs:
        selected.extend(entry for entry in entries if entry["source_event"] in {"IMAGE_LOAD_FAILED", "INSPECTION_FAILED", "INFERENCE_FAILED"}
            and entry["source_field"].rsplit("/", 1)[-1] in {"event_code", "stage", "timestamp"})
    known = {entry["token"] for entry in selected}
    selected.extend(entry for entry in entries if entry["token"] in error_tokens(entries)
        and entry["source_tool"] == "get_inspection_result" and entry["token"] not in known)
    final = next(entry["token"] for entry in selected if entry["source_field"] == "/data/final_result")
    return {"overall_summary": "INSPECTION_FAILED", "observed_fact_refs": [entry["token"] for entry in selected],
        "possible_causes": [], "recommended_checks": ["MANUAL_REINSPECTION:" + final], "limitations": []}


def final_report(**kwargs):
    packet = json.loads(kwargs["contents"][0].parts[0].text)
    payload = report_for_catalog(packet["catalog"])
    event = next((entry for entry in packet["catalog"] if entry["source_event"] == "IMAGE_LOAD_FAILED"
        and entry["source_field"].endswith("/event_code")), None)
    if event:
        payload["possible_causes"] = ["IMAGE_ACQUISITION:" + event["token"]]
        payload["recommended_checks"] = ["IMAGE_REGISTRATION_ACCESS_CHECK:" + event["token"]]
    return text_response(json.dumps(payload))


def responses_with_logs(*, continue_investigation=False):
    return [call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})),
        call_response(("get_execution_logs", {"inspection_id": "INSP-000001"})),
        *([text_response()] if continue_investigation else []), final_report]


def collect_state(storage, with_logs=True, with_quality=False):
    service, generator = service_for(storage, [])
    state = RequestState("INSP-000001")

    async def collect():
        names = ["get_inspection_result"]
        if with_logs:
            names.append("get_execution_logs")
        if with_quality:
            names.append("analyze_image_quality")
        for index, name in enumerate(names, 1):
            await service._execute(types.FunctionCall(name=name, args={"inspection_id": state.inspection_id}), state, index)

    asyncio.run(collect())
    generator.assert_not_awaited()
    return service, state


def test_failed_workflow_is_a_successful_read_without_fabricated_statistics(failed_storage):
    failed_storage.get_inspection.return_value.metrics["error"] = "PRIVATE_ERROR_MESSAGE"
    tools = InspectionTools(failed_storage)
    result = tools.get_inspection_result("INSP-000001")
    quality = tools.analyze_image_quality("INSP-000001")
    assert result["ok"] and result["data"]["status"] == "FAILED"
    assert result["data"]["result"] == "UNKNOWN" and result["data"]["final_result"] == "ERROR"
    assert all(result["data"][name] is None for name in ("anomaly_score", "decision_threshold", "inference_time_ms"))
    assert quality["ok"] and quality["data"]["image_quality_status"] == "ERROR"
    assert set(quality["data"]["metrics"].values()) == {None}
    assert quality["data"]["brightness_thresholds"] is None and quality["data"]["threshold_status"] == "NOT_RECORDED"
    assert "PRIVATE_ERROR_MESSAGE" not in json.dumps({"result": result, "quality": quality})
    failed_storage.save_inspection.assert_not_called()
    failed_storage.save_logs.assert_not_called()


def test_error_logs_keep_event_order_but_not_raw_messages(failed_storage):
    response = InspectionTools(failed_storage).get_execution_logs("INSP-000001")
    assert response["ok"] and response["metadata"]["messages_included"] is False
    assert [entry["event_code"] for entry in response["data"]] == [
        "INSPECTION_STARTED", "IMAGE_LOAD_FAILED", "INSPECTION_FAILED"]
    assert [entry["stage"] for entry in response["data"]] == ["init", "load", "complete"]
    assert "PRIVATE_ERROR_MESSAGE" not in json.dumps(response)


@pytest.mark.parametrize("with_logs,with_quality,required", [(False, False, ()), (False, True, ()),
    (True, False, ()), (True, True, ("INSPECTION_COMPLETED",))])
def test_error_never_uses_normal_or_warning_early_exit(failed_storage, with_logs, with_quality, required):
    service, state = collect_state(failed_storage, with_logs, with_quality)
    service.required_warning_event_codes = required
    assert not _normal_evidence_ready(state)
    assert not warning_evidence_ready(state, required_event_codes=required)
    assert service._investigation_ready(state) is (with_logs and not with_quality and not required)
    assert state.snapshot["result"] == "UNKNOWN" and state.snapshot["final_result"] == "ERROR"


def test_error_mock_flow_stops_after_required_tools_and_links_actual_log_facts(failed_storage):
    before = failed_storage.get_inspection.return_value.model_dump()
    service, generator = service_for(failed_storage, responses_with_logs())
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and generator.await_count == 3
    assert result.tools_used == ["get_inspection_result", "get_execution_logs"]
    assert [(entry.round_number, entry.evidence_id, entry.executed, entry.success)
        for entry in result.tool_execution_trace] == [(1, "E0001", True, True), (2, "E0002", True, True)]
    assert {fact.source_field for fact in result.observed_facts if fact.source_event == "IMAGE_LOAD_FAILED"} == {
        "/data/1/event_code", "/data/1/stage", "/data/1/timestamp"}
    assert result.possible_causes[0].is_hypothesis is True
    assert result.recommended_checks[0].check_code == "IMAGE_REGISTRATION_ACCESS_CHECK"
    assert result.inspection_snapshot["anomaly_score"] is None
    assert failed_storage.get_inspection.return_value.model_dump() == before
    final = generator.call_args_list[-1].kwargs
    assert final["config"].http_options.timeout == 15000 and final["config"].http_options.retry_options.attempts == 1
    assert final["config"].tools is None and final["config"].tool_config is None
    assert len(final["contents"]) == 1 and final["contents"][0].role == "user"
    failed_storage.list_inspections.assert_not_called()
    failed_storage.save_inspection.assert_not_called()
    failed_storage.save_logs.assert_not_called()


@pytest.mark.parametrize("log_availability", ["not_requested", "empty", "fetched_but_omitted"])
def test_error_event_is_mandatory_for_a_completed_report(failed_storage, log_availability):
    responses = responses_with_logs(continue_investigation=log_availability != "fetched_but_omitted")
    if log_availability == "not_requested":
        responses.pop(1)
    elif log_availability == "empty":
        failed_storage.get_logs.return_value = []

    def core_only(**kwargs):
        packet = json.loads(kwargs["contents"][0].parts[0].text)
        payload = report_for_catalog(packet["catalog"], include_logs=False)
        return text_response(json.dumps(payload))

    responses[-1] = core_only
    service, generator = service_for(failed_storage, responses)
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "FAILED"
    assert not any(fact.source_event == "IMAGE_LOAD_FAILED" for fact in result.observed_facts)
    assert generator.await_count == (2 if log_availability == "not_requested" else 3)
    assert result.error_code == ("EVIDENCE_MISMATCH" if log_availability == "fetched_but_omitted" else "INSUFFICIENT_EVIDENCE")
    if log_availability == "empty":
        assert result.tool_execution_trace[1].executed and not result.tool_execution_trace[1].success
        assert result.tool_execution_trace[1].error_code == "DATA_UNAVAILABLE"
        assert result.tools_used == ["get_inspection_result"]


def test_signal_policy_rejects_model_service_check_for_skipped_inference(failed_storage):
    service, state = collect_state(failed_storage)
    catalog = build_catalog(state)
    entries = [entry.__dict__ for entry in catalog.entries]
    payload = report_for_catalog(entries)
    token = next(entry["token"] for entry in entries if entry["source_field"] == "/data/defect_detection_status")
    payload["possible_causes"] = ["MODEL_AVAILABILITY:" + token]
    payload["recommended_checks"] = ["MODEL_SERVICE_CHECK:" + token]
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        service._verify_report(convert_simple_report(json.dumps(payload), state, catalog), state, "gemini-mock")


@pytest.mark.parametrize("mutation", ["fake_token", "fake_evidence", "fake_pointer", "invented_score", "invented_mean",
    "wrong_id", "wrong_event", "missing_core", "wrong_summary", "ungrounded_cause", "ungrounded_check"])
def test_error_report_rejects_untrusted_claims_without_repair(failed_storage, mutation):
    service, state = collect_state(failed_storage)
    catalog = build_catalog(state)
    entries = [entry.__dict__ for entry in catalog.entries]
    payload = report_for_catalog(entries)
    if mutation == "fake_token":
        payload["observed_fact_refs"].append("K9999")
        with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
            convert_simple_report(json.dumps(payload), state, catalog)
        return
    draft = convert_simple_report(json.dumps(payload), state, catalog)
    if mutation == "fake_evidence":
        draft.observed_facts[0].evidence_id = "E9999"
    elif mutation == "fake_pointer":
        draft.observed_facts[0].source_field = "/data/absent"
    elif mutation in {"invented_score", "invented_mean"}:
        draft.observed_facts[0].source_field = "/data/anomaly_score" if mutation == "invented_score" else "/data/metrics/mean"
        draft.observed_facts[0].observed_value = 0
    elif mutation == "wrong_id":
        draft.inspection_id = "INSP-000002"
    elif mutation == "wrong_event":
        draft.observed_facts[-1].source_event = "INFERENCE_FAILED"
    elif mutation == "missing_core":
        draft.observed_facts.pop(0)
    elif mutation == "wrong_summary":
        draft.overall_summary = "NORMAL_MODEL_RESULT"
    else:
        field, selection = ("possible_causes", {"cause_code": "ILLUMINATION_CHANGE", "evidence_refs": ["F0001"]}) \
            if mutation == "ungrounded_cause" else ("recommended_checks", {"check_code": "CONTINUE_MONITORING", "evidence_refs": ["F0001"]})
        values = draft.model_dump()
        values[field] = [selection]
        draft = DiagnosisDraft.model_validate(values)
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        service._verify_report(draft, state, "gemini-mock")


@pytest.mark.parametrize("mutation", ["pointer", "value", "evidence_id"])
def test_error_conversion_rejects_catalog_tampering(failed_storage, mutation):
    service, state = collect_state(failed_storage)
    catalog = build_catalog(state)
    payload = report_for_catalog([entry.__dict__ for entry in catalog.entries])
    first = replace(catalog.entries[0], **{
        {"pointer": "source_field", "value": "observed_value", "evidence_id": "evidence_id"}[mutation]:
        {"pointer": "/data/missing", "value": 0, "evidence_id": "E9999"}[mutation]})
    forged = replace(catalog, entries=(first, *catalog.entries[1:]))
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        convert_simple_report(json.dumps(payload), state, forged)


def test_error_repeated_tool_calls_are_bounded(failed_storage):
    response = call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}))
    service, generator = service_for(failed_storage, [response, response, response])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "TOOL_REPEAT_LIMIT" and generator.await_count == 3
    assert [entry.executed for entry in result.tool_execution_trace] == [True, True, False]


def test_error_final_gemini_504_keeps_safe_http_502_and_original_verdict(harness):
    storage = harness.storage
    storage.save_inspection(make_record(status="FAILED", result="UNKNOWN", image_quality_status="ERROR",
        defect_detection_status="SKIPPED", final_result="ERROR", final_reason_code="INSPECTION_FAILED",
        anomaly_score=None, decision_threshold=None, metrics={}))
    storage.save_logs(error_logs())
    responses = responses_with_logs()
    responses[-1] = errors.ServerError(504, {"error": {"status": "DEADLINE_EXCEEDED", "message": "PRIVATE_ERROR_MESSAGE"}})
    service, generator = service_for(storage, responses)
    app.dependency_overrides[get_agent_service] = lambda: service
    before = (storage.get_inspection("INSP-000001").model_dump(), storage.get_logs("INSP-000001"))
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 502 and response.json()["detail"]["error_code"] == "GEMINI_REQUEST_FAILED"
    assert "PRIVATE_ERROR_MESSAGE" not in response.text and generator.await_count == 3
    assert before == (storage.get_inspection("INSP-000001").model_dump(), storage.get_logs("INSP-000001"))


@pytest.mark.parametrize("artifact", ["ready", "lock", "result"])
def test_t05_preparation_preserves_existing_rounds(tmp_path, artifact):
    old = attempt_paths(tmp_path, "old_t03")
    old[artifact].write_text("PRESERVE", encoding="utf-8")
    manifest = prepare_attempt(tmp_path, "new_t05", "INSP-001405", scenario="T05", final_timeout=15)
    validate_ready_attempt(tmp_path, "new_t05", "INSP-001405", scenario="T05", final_timeout=15)
    assert manifest["scenario"] == "T05" and manifest["timeouts_seconds"]["final_ceiling"] == 15
    assert manifest["analysis_attempts"] == manifest["gemini_http_requests"] == 0 and manifest["approval_required"]
    assert not attempt_paths(tmp_path, "new_t05")["lock"].exists()
    assert not attempt_paths(tmp_path, "new_t05")["result"].exists()
    assert old[artifact].read_text(encoding="utf-8") == "PRESERVE"
    with pytest.raises(ValueError, match="ATTEMPT_COLLISION"):
        prepare_attempt(tmp_path, "new_t05", "INSP-001405", scenario="T05", final_timeout=15)
    with pytest.raises(ValueError, match="INVALID_READY_MANIFEST"):
        validate_ready_attempt(tmp_path, "new_t05", "INSP-001405", scenario="T05", final_timeout=30)


@pytest.mark.parametrize("scenario,timeout", [("T06", 15), ("T05", True), ("T05", 0), ("T05", 20)])
def test_preparation_rejects_unsupported_scenario_or_timeout(tmp_path, scenario, timeout):
    with pytest.raises(ValueError, match="INVALID_ATTEMPT_SETTINGS"):
        prepare_attempt(tmp_path, "new_t05", "INSP-001405", scenario=scenario, final_timeout=timeout)
    assert not list(tmp_path.iterdir())


def test_t05_runner_preflight_does_not_start_an_analysis_or_network(failed_storage, tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "data/outputs/manual_validation/run_t05_simple_e2e_once.py"
    if not source.exists():
        pytest.skip("Local manual runner is not distributed with the repository")
    previous_logging = logging.root.manager.disable
    previous_warnings = list(warnings.filters)
    try:
        spec = importlib.util.spec_from_file_location("offline_t05_runner", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        runner = module.runner
        monkeypatch.setattr(runner, "OUTPUT", tmp_path)
        monkeypatch.setattr(runner, "ROOT", tmp_path)
        monkeypatch.setattr(runner, "PROTECTED", {source})
        settings = SimpleNamespace(**runner.EXPECTED_LIMITS, GEMINI_API_KEY="PRIVATE_KEY",
            GEMINI_MODEL=runner.MODEL, AGENT_FINAL_MODEL_TIMEOUT_SECONDS=15,
            AGENT_MAX_PAYLOAD_BYTES=65536,
            absolute_inspections_path=tmp_path / "data/inspections.jsonl",
            absolute_inspection_logs_path=tmp_path / "data/inspection_logs.jsonl")
        monkeypatch.setattr(runner, "SETTINGS", settings)
        record = failed_storage.get_inspection.return_value
        record.inspection_id = runner.TARGET
        for log in failed_storage.get_logs.return_value:
            log.inspection_id = runner.TARGET
        monkeypatch.setattr(runner, "get_inspection_storage", lambda: failed_storage)
        with patch.object(AgentService, "analyze", side_effect=AssertionError("ANALYSIS_FORBIDDEN")) as analyze:
            manifest = module.prepare()
            module.offline_preflight()
        analyze.assert_not_called()
        assert manifest["state"] == "READY" and runner.REPORT["analysis_attempts"] == 0
        assert runner.REPORT["sdk_requests"] == runner.REPORT["http_transmissions"] == []
        assert "PRIVATE_KEY" not in json.dumps(runner.REPORT)
        assert runner.REPORT["stored_verdict"] == {"result": "UNKNOWN", "final_result": "ERROR", "final_reason_code": "INSPECTION_FAILED"}
        assert not attempt_paths(tmp_path, runner.ATTEMPT)["lock"].exists()
    finally:
        logging.disable(previous_logging)
        warnings.filters[:] = previous_warnings
