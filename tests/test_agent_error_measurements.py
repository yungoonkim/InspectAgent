"""Policy-backed manual measurements, distinct READY and executed-report outcomes."""

import asyncio
import copy
import importlib.util
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import warnings

import pytest

from backend.agent import error_policy
from backend.agent.reporting import build_catalog
from backend.agent.service import AgentFailure, AgentService
from scripts.agent_validation_measurements import (
    NOT_OBSERVABLE, NOT_TESTED, attempt_paths, error_policy_measurements, probe_error_policy,
)
from tests.test_agent_error_policy import draft_for
from tests.test_agent_t05_preflight import collect_state, failed_storage, prohibit_external_calls
from tests.test_agent_tools import make_record


def capabilities(service, state):
    return asyncio.run(probe_error_policy(service, state))


def test_ready_policy_metadata_uses_actual_guards_without_claiming_e2e_success(failed_storage):
    service, state = collect_state(failed_storage)
    before = copy.deepcopy((state.evidence, state.trace, state.snapshot))
    with patch.object(AgentService, "analyze", side_effect=AssertionError("ANALYSIS_FORBIDDEN")) as analyze:
        checks = capabilities(service, state)
        measured = error_policy_measurements(state, capabilities=checks)
    analyze.assert_not_called()
    assert checks == {"investigation_guard": True, "report_coverage_guard": True,
        "complete_probe_accepted": True, "skipped_model_claims_rejected": True, "policy_enabled": True,
        "unavailable_reason": None}
    assert measured["policy_enabled"] is True and measured["policy_applicable"] is True
    assert measured["required_tools"] == ["get_execution_logs", "get_inspection_result"]
    assert measured["required_event_codes"] == ["IMAGE_LOAD_FAILED", "INSPECTION_FAILED"]
    assert measured["required_fact_count"] == len(measured["required_facts"]) == 17
    assert measured["offline_required_evidence_valid"] is True
    assert measured["required_evidence_collected"] == measured["report_validation_passed"] == NOT_TESTED
    assert all(set(entry) == {"evidence_id", "source_tool", "source_field", "source_event"} for entry in measured["required_facts"])
    assert (state.evidence, state.trace, state.snapshot) == before


@pytest.mark.parametrize("scenario", ["T01", "T03", "T06"])
def test_error_measurements_do_not_reclassify_normal_or_warning_inspections(failed_storage, scenario):
    record = make_record()
    if scenario == "T03":
        record = record.model_copy(update={"image_quality_status": "WARNING_LOW_BRIGHTNESS",
            "final_result": "REINSPECT", "final_reason_code": "IMAGE_QUALITY_WARNING"})
    failed_storage.get_inspection.return_value = record
    service, state = collect_state(failed_storage, with_logs=False)
    measured = error_policy_measurements(state)
    assert measured["policy_applicable"] is False and measured["required_fact_count"] == 0
    assert measured["required_tools"] == measured["required_event_codes"] == []
    assert measured["required_evidence_collected"] == measured["report_validation_passed"] == NOT_TESTED
    assert capabilities(service, state)["policy_enabled"] == NOT_OBSERVABLE


@pytest.mark.parametrize("phase", ["READY", "INVESTIGATION", "REPORT"])
def test_missing_logs_are_never_reported_as_collected_or_validated(failed_storage, phase):
    service, state = collect_state(failed_storage, with_logs=False)
    measured = error_policy_measurements(state, phase=phase, validation_failed=phase == "REPORT")
    assert measured["policy_applicable"] is True and measured["offline_required_evidence_valid"] is False
    assert measured["required_evidence_collected"] == (NOT_TESTED if phase == "READY" else False)
    assert measured["report_validation_passed"] == (False if phase == "REPORT" else NOT_TESTED)
    assert measured["required_facts"] == NOT_OBSERVABLE
    assert capabilities(service, state)["policy_enabled"] == NOT_OBSERVABLE


def test_enabled_without_capability_observation_is_not_assumed(failed_storage):
    service, state = collect_state(failed_storage)
    assert error_policy_measurements(state)["policy_enabled"] == NOT_OBSERVABLE


def test_validated_result_is_distinct_from_ready_and_collection(failed_storage):
    service, state = collect_state(failed_storage)
    draft = draft_for(state)
    result = service._verify_report(draft, state, "gemini-mock")
    checks = capabilities(service, state)
    ready = error_policy_measurements(state, capabilities=checks, draft=draft, validation_result=result)
    assert ready["report_validation_passed"] == ready["required_evidence_collected"] == NOT_TESTED
    collected = error_policy_measurements(state, capabilities=checks, phase="INVESTIGATION")
    assert collected["required_evidence_collected"] is True and collected["report_validation_passed"] == NOT_TESTED
    reported = error_policy_measurements(state, capabilities=checks, phase="REPORT", draft=draft, validation_result=result)
    assert reported["report_validation_passed"] is True
    invalid = draft.model_copy(deep=True)
    invalid.observed_facts.pop()
    rejected = error_policy_measurements(state, capabilities=checks, phase="REPORT", draft=invalid, validation_result=result)
    assert rejected["report_validation_passed"] is False


def test_plain_success_boolean_cannot_claim_final_validation(failed_storage):
    service, state = collect_state(failed_storage)
    measured = error_policy_measurements(state, phase="REPORT", draft=draft_for(state), validation_result=True)
    assert measured["report_validation_passed"] == NOT_TESTED


def test_invalid_measurement_phase_cannot_claim_collection(failed_storage):
    service, state = collect_state(failed_storage)
    measured = error_policy_measurements(state, phase="UNRECOGNIZED")
    assert measured["required_evidence_collected"] == measured["report_validation_passed"] == NOT_TESTED
    assert measured["unavailable_reason"] == "INVALID_MEASUREMENT_PHASE"


def test_no_snapshot_is_explicitly_unobserved(failed_storage):
    service, state = collect_state(failed_storage)
    state.snapshot = None
    measured = error_policy_measurements(state)
    assert measured["policy_applicable"] == NOT_TESTED and measured["unavailable_reason"] == "NO_INSPECTION_SNAPSHOT"


def test_required_fact_list_tracks_operating_policy_changes(failed_storage, monkeypatch):
    service, state = collect_state(failed_storage)
    original = error_policy.error_required_facts
    additional = next(entry for entry in build_catalog(state).entries if entry.source_tool == "get_inspection_result"
        and entry.source_field == "/data/metrics/min")
    monkeypatch.setattr(error_policy, "error_required_facts", lambda current: (*original(current), additional))
    measured = error_policy_measurements(state)
    assert measured["required_fact_count"] == 18
    assert any(entry["source_field"] == "/data/metrics/min" for entry in measured["required_facts"])


@pytest.mark.parametrize("function", ["error_report_scope", "error_required_facts"])
def test_unavailable_policy_is_not_observable_and_never_successful(failed_storage, monkeypatch, function):
    service, state = collect_state(failed_storage)
    monkeypatch.setattr(error_policy, function, None)
    measured = error_policy_measurements(state)
    assert measured["policy_enabled"] == NOT_OBSERVABLE
    assert measured["required_evidence_collected"] == measured["report_validation_passed"] == NOT_TESTED
    assert capabilities(service, state)["policy_enabled"] == NOT_OBSERVABLE


def test_unwired_investigation_gate_is_detected_without_final_network_request(failed_storage, monkeypatch):
    service, state = collect_state(failed_storage)

    async def bypass(self, client, model, current):
        return await self._generate(None, model, [], current, 1, structured=True)

    monkeypatch.setattr(AgentService, "_run", bypass)
    measured = capabilities(service, state)
    assert measured["investigation_guard"] is False and measured["policy_enabled"] is False


def test_unwired_report_guard_is_detected(failed_storage, monkeypatch):
    service, state = collect_state(failed_storage)
    original = service._verify_report
    accepted = original(draft_for(state), state, "gemini-mock")
    monkeypatch.setattr(service, "_verify_report", lambda *arguments: accepted)
    measured = capabilities(service, state)
    assert measured["report_coverage_guard"] is False and measured["policy_enabled"] is False


@pytest.mark.parametrize("selection", ["possible_causes", "recommended_checks"])
def test_skipped_model_claim_guard_is_behaviorally_checked(failed_storage, monkeypatch, selection):
    service, state = collect_state(failed_storage)
    original = service._verify_report
    accepted = original(draft_for(state), state, "gemini-mock")

    def bypass(draft, current, model):
        entries = getattr(draft, selection)
        if any(getattr(entry, "cause_code", None) == "MODEL_AVAILABILITY"
            or getattr(entry, "check_code", None) == "MODEL_SERVICE_CHECK" for entry in entries):
            return accepted
        return original(draft, current, model)

    monkeypatch.setattr(service, "_verify_report", bypass)
    measured = capabilities(service, state)
    assert measured["skipped_model_claims_rejected"] is False and measured["policy_enabled"] is False


def test_private_values_and_exceptions_are_not_copied_into_policy_metadata(failed_storage, monkeypatch):
    service, state = collect_state(failed_storage)
    service.settings.GEMINI_API_KEY = "PRIVATE_KEY"
    measured = error_policy_measurements(state, capabilities=capabilities(service, state))
    assert "observed_value" not in json.dumps(measured) and "PRIVATE_" not in json.dumps(measured)

    def fail(current):
        raise RuntimeError("PRIVATE_ERROR_MESSAGE")

    monkeypatch.setattr(error_policy, "error_required_facts", fail)
    assert "PRIVATE_" not in json.dumps(error_policy_measurements(state))
    assert "PRIVATE_" not in json.dumps(capabilities(service, state))


@pytest.fixture
def manual_runner(tmp_path, failed_storage, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "data/outputs/manual_validation/run_t05_simple_e2e_once.py"
    if not source.exists():
        pytest.skip("Local manual runner is not distributed with the repository")
    previous_logging = logging.root.manager.disable
    previous_warnings = list(warnings.filters)
    try:
        spec = importlib.util.spec_from_file_location("measured_t05_runner", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        runner = module.runner
        monkeypatch.setattr(runner, "OUTPUT", tmp_path)
        monkeypatch.setattr(runner, "ROOT", tmp_path)
        monkeypatch.setattr(runner, "TARGET", "INSP-000001")
        monkeypatch.setitem(runner.REPORT, "inspection_id", runner.TARGET)
        monkeypatch.setattr(runner, "PROTECTED", {source})
        monkeypatch.setattr(runner, "SETTINGS", SimpleNamespace(**runner.EXPECTED_LIMITS,
            GEMINI_MODEL=runner.MODEL, GEMINI_API_KEY="PRIVATE_KEY", AGENT_FINAL_MODEL_TIMEOUT_SECONDS=15,
            AGENT_MAX_PAYLOAD_BYTES=65536, absolute_inspections_path=tmp_path / "data/inspections.jsonl",
            absolute_inspection_logs_path=tmp_path / "data/inspection_logs.jsonl"))
        record = failed_storage.get_inspection.return_value
        record.inspection_id = runner.TARGET
        for log in failed_storage.get_logs.return_value:
            log.inspection_id = runner.TARGET
        monkeypatch.setattr(runner, "get_inspection_storage", lambda: failed_storage)
        module.prepare()
        yield module, failed_storage
    finally:
        logging.disable(previous_logging)
        warnings.filters[:] = previous_warnings


def test_t05_preflight_keeps_ready_unexecuted_and_unknown_e2e_fields(manual_runner):
    module, storage = manual_runner
    runner = module.runner
    paths = attempt_paths(runner.OUTPUT, runner.ATTEMPT)
    before = paths["ready"].read_bytes()
    with patch.object(AgentService, "analyze", side_effect=AssertionError("ANALYSIS_FORBIDDEN")) as analyze:
        module.offline_preflight()
    analyze.assert_not_called()
    assert paths["ready"].read_bytes() == before and not paths["lock"].exists() and not paths["result"].exists()
    assert runner.REPORT["error_policy"]["policy_enabled"] is True
    assert runner.REPORT["error_policy"]["required_fact_count"] == 17
    assert runner.REPORT["error_policy"]["required_evidence_collected"] == NOT_TESTED
    assert runner.REPORT["error_policy"]["report_validation_passed"] == NOT_TESTED
    assert "error_log_coverage_enforced_by_service" not in runner.REPORT
    assert runner.REPORT["sdk_requests"] == runner.REPORT["http_transmissions"] == []
    assert runner.REPORT["analysis_attempts"] == 0 and "PRIVATE_" not in json.dumps(runner.REPORT)


@pytest.mark.parametrize("enabled", [False, NOT_OBSERVABLE])
def test_t05_preflight_blocks_unconfirmed_server_policy(manual_runner, monkeypatch, enabled):
    module, storage = manual_runner

    async def unconfirmed(service, state):
        return {"policy_enabled": enabled}

    monkeypatch.setattr(module, "probe_error_policy", unconfirmed)
    with pytest.raises(RuntimeError, match="ERROR_POLICY_NOT_VERIFIED"):
        module.offline_preflight()
    assert module.runner.REPORT["offline_preflight"] == "BLOCKED"
    assert not attempt_paths(module.runner.OUTPUT, module.runner.ATTEMPT)["lock"].exists()


@pytest.mark.parametrize("missing", [False, True])
def test_live_observation_distinguishes_collection_and_report_coverage(manual_runner, missing):
    module, storage = manual_runner
    module.offline_preflight()
    service, state = collect_state(storage, with_logs=not missing)
    draft = draft_for(state)
    module.observed_ready(service, state)
    measured = module.runner.REPORT["error_policy"]
    assert measured["required_evidence_collected"] is (not missing)
    assert measured["report_validation_passed"] == NOT_TESTED
    if missing:
        with pytest.raises(AgentFailure):
            module.observed_verify(service, draft, state, "gemini-mock")
        assert module.runner.REPORT["error_policy"]["report_validation_passed"] is False
    else:
        result = module.observed_verify(service, draft, state, "gemini-mock")
        assert result.analysis_status == "COMPLETED"
        assert module.runner.REPORT["error_policy"]["report_validation_passed"] is True
