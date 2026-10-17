"""Stored brightness comparison, provenance and bounded warning investigation."""

import asyncio
import copy
import json
from unittest.mock import patch

from google.genai import types
import pytest

from backend.agent.errors import AgentFailure
from backend.agent.reporting import build_catalog, convert_simple_report
from backend.agent.schemas import AgentLimits
from backend.agent.service import RequestState, _report_contents
from backend.agent.tools import InspectionTools
from backend.storage import JsonlInspectionStorage, StorageError
from tests.test_agent_service import call_response, normal_responses, service_for, text_response
from tests.test_agent_tools import make_record
from tests.test_agent_warning_policy_experiment import calls, warning_report, warning_storage
from tests.agent_error_fixtures import error_logs, error_record, with_error_facts
from tests.test_agent_service import report_payload, report_response


@pytest.fixture(autouse=True)
def forbid_live_client():
    with patch("backend.agent.service.genai.Client", side_effect=AssertionError("NETWORK_FORBIDDEN")):
        yield


def historical(identifier=10, mean=120.0, **changes):
    record = make_record(inspection_id=f"INSP-{identifier:06d}", timestamp=f"2026-10-14T{identifier % 24:02d}:00:00Z")
    record.metrics["mean"] = mean
    for name, value in changes.items():
        setattr(record, name, value)
    return record


def comparison_storage(records=()):
    storage = warning_storage()
    storage.list_inspections.return_value = list(records)
    return storage


def compare(storage, limit=5):
    return InspectionTools(storage).get_inspection_history("PROD-001", limit, "INSP-000001")


def comparison_report(**kwargs):
    response = warning_report(**kwargs)
    payload = json.loads(response.candidates[0].content.parts[0].text)
    packet = json.loads(kwargs["contents"][0].parts[0].text)
    payload["observed_fact_refs"].extend(entry["token"] for entry in packet["catalog"]
        if entry["source_field"].startswith("/brightness_comparison/summary/"))
    return text_response(json.dumps(payload))


def comparison_state():
    service, generator = service_for(comparison_storage([historical()]), [])
    state = RequestState("INSP-000001")

    async def collect():
        for name in ("get_inspection_result", "analyze_image_quality"):
            await service._execute(types.FunctionCall(name=name, args={"inspection_id": state.inspection_id}), state, 1)
        await service._ensure_warning_history(state, 1)

    asyncio.run(collect())
    generator.assert_not_called()
    return service, state


def test_three_samples_are_computed_from_stored_means_with_legacy_data_unchanged():
    storage = comparison_storage([historical(10, 100.0), historical(11, 120.0), historical(12, 140.0)])
    legacy = InspectionTools(storage).get_inspection_history("PROD-001")
    response = compare(storage)
    assert response["data"] == legacy["data"] and isinstance(response["data"], list)
    assert "brightness_comparison" not in legacy
    comparison = response["brightness_comparison"]
    assert comparison["summary"] == {
        "scope": "STORED_VALUES_ONLY_UNVERIFIED_MEASUREMENT_CONTRACT",
        "status": "DESCRIPTIVE_SUMMARY", "current_mean": 80.0, "sample_count": 3,
        "historical_mean": 120.0, "historical_min": 100.0, "historical_max": 140.0,
        "absolute_mean_difference": 40.0,
    }
    assert [sample["inspection_id"] for sample in comparison["samples"]] == ["INSP-000012", "INSP-000011", "INSP-000010"]
    assert comparison["summary"]["scope"] == "STORED_VALUES_ONLY_UNVERIFIED_MEASUREMENT_CONTRACT"
    storage.save_inspection.assert_not_called()


@pytest.mark.parametrize("records,status,count", [
    ([], "NO_HISTORY", 0), ([historical()], "SINGLE_OBSERVATION", 1),
    ([historical(mean=None)], "NO_COMPARABLE_HISTORY", 0),
])
def test_sample_count_controls_unavailable_and_single_observation(records, status, count):
    response = compare(comparison_storage(records))
    summary = response["brightness_comparison"]["summary"]
    assert summary["status"] == status and summary["sample_count"] == count
    assert summary["current_mean"] == 80.0
    assert summary["historical_mean"] == (120.0 if count else None)
    assert summary["historical_min"] == summary["historical_max"] == (120.0 if count else None)
    assert response["error"] == ("DATA_UNAVAILABLE" if not records else None)


@pytest.mark.parametrize("mean", [None, "120", True, -1, 256, float("nan"), float("inf"), -float("inf")])
def test_invalid_brightness_is_excluded_without_zero_substitution(mean):
    response = compare(comparison_storage([historical(10, mean), historical(11, 100.0)]))
    summary = response["brightness_comparison"]["summary"]
    assert summary["sample_count"] == 1 and summary["historical_mean"] == 100.0
    assert response["brightness_comparison"]["samples"][0]["inspection_id"] == "INSP-000011"


def test_scope_time_status_dimensions_and_duplicates_are_filtered_before_limit():
    storage = comparison_storage()
    current = storage.get_inspection.return_value
    invalid_size = historical(16)
    invalid_size.metrics["width"] = 100
    missing = historical(17)
    missing.metrics.pop("mean")
    storage.list_inspections.return_value = [
        current, historical(13, timestamp="2026-10-16T01:00:00Z"), historical(14, product_id="PROD-OTHER"),
        historical(15, timestamp="invalid"), invalid_size, missing,
        historical(18, final_result="ERROR", image_quality_status="ERROR"), historical(19, status="FAILED"),
        historical(20), historical(20, mean=121.0), historical(21, timestamp=current.timestamp),
        historical(10, 100.0), historical(11, 120.0, image_quality_status="WARNING_LOW_BRIGHTNESS"),
        historical(12, 140.0),
    ]
    response = compare(storage, limit=2)
    comparison = response["brightness_comparison"]
    assert comparison["summary"]["sample_count"] == len(comparison["samples"]) == 2
    assert [record["inspection_id"] for record in comparison["samples"]] == ["INSP-000012", "INSP-000011"]
    assert comparison["summary"]["historical_mean"] == 130.0
    assert response["metadata"]["scan_limit"] == 1000
    storage.list_inspections.assert_called_once_with(limit=1000, product_id="PROD-001")


def test_storage_scan_cap_is_not_reported_as_all_history():
    storage = comparison_storage([historical(identifier=100 + index) for index in range(1001)])
    response = compare(storage, limit=3)
    assert response["metadata"]["scan_limit_reached"] is True
    assert response["metadata"]["candidate_count"] == 1000
    assert response["metadata"]["global_latest_guaranteed"] is False
    assert response["brightness_comparison"]["summary"]["sample_count"] == 3


@pytest.mark.parametrize("field,value", [("mean", None), ("width", None), ("width", True)])
def test_current_missing_measurement_does_not_generate_statistics(field, value):
    storage = comparison_storage([historical()])
    storage.get_inspection.return_value.metrics[field] = value
    summary = compare(storage)["brightness_comparison"]["summary"]
    assert summary["status"] == "CURRENT_UNAVAILABLE"
    assert summary["sample_count"] == 0 and summary["historical_mean"] is None


def test_comparison_target_must_match_product_before_history_lookup():
    storage = comparison_storage([historical()])
    response = InspectionTools(storage).get_inspection_history("PROD-OTHER", inspection_id="INSP-000001")
    assert response["error"] == "INVALID_ARGUMENT"
    storage.list_inspections.assert_not_called()


@pytest.mark.parametrize("field,value", [("historical_mean", 999.0), ("historical_min", 0.0),
    ("historical_max", 255.0), ("sample_count", 2), ("absolute_mean_difference", 1.0), ("current_mean", 99.0)])
def test_tampered_derived_statistics_are_rejected_by_catalog_and_final_validation(field, value):
    service, state = comparison_state()
    catalog = build_catalog(state)
    response = comparison_report(contents=_report_contents(state, catalog))
    draft = convert_simple_report(response.candidates[0].content.parts[0].text, state, catalog)
    state.evidence["E0003"][1]["brightness_comparison"]["summary"][field] = value
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        build_catalog(state)
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        service._verify_report(draft, state, "gemini-mock")


@pytest.mark.parametrize("mutation", ["future", "foreign", "self", "duplicate", "current", "bad_limit", "sample_mean"])
def test_comparison_samples_and_current_binding_are_independently_validated(mutation):
    service, state = comparison_state()
    comparison = state.evidence["E0003"][1]["brightness_comparison"]
    sample = comparison["samples"][0]
    if mutation == "future":
        sample["timestamp"] = "2026-10-16T00:00:00+00:00"
    elif mutation == "foreign":
        sample["product_id"] = "PROD-OTHER"
    elif mutation == "self":
        sample["inspection_id"] = state.inspection_id
    elif mutation == "duplicate":
        comparison["samples"].append(copy.deepcopy(sample))
    elif mutation == "current":
        comparison["current"]["metrics"]["mean"] = 90.0
    elif mutation == "bad_limit":
        comparison["limit"] = True
    else:
        sample["metrics"]["mean"] = 99.0
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        build_catalog(state)


def test_false_pointer_fact_and_history_causal_claim_are_rejected():
    service, state = comparison_state()
    catalog = build_catalog(state)
    response = comparison_report(contents=_report_contents(state, catalog))
    draft = convert_simple_report(response.candidates[0].content.parts[0].text, state, catalog)
    comparison_fact = next(fact for fact in draft.observed_facts if fact.source_field.endswith("/historical_mean"))
    malformed = draft.model_copy(deep=True)
    next(fact for fact in malformed.observed_facts if fact.fact_id == comparison_fact.fact_id).source_field = "/brightness_comparison/summary/nonexistent"
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        service._verify_report(malformed, state, "gemini-mock")
    draft.possible_causes[0].evidence_refs = [comparison_fact.fact_id]
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        service._verify_report(draft, state, "gemini-mock")


def test_warning_policy_executes_one_python_history_without_another_model_request():
    storage = comparison_storage([historical()])
    before = storage.get_inspection.return_value.model_dump()
    service, generator = service_for(storage, [*calls(), comparison_report])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and result.inspection_snapshot["final_result"] == "REINSPECT"
    assert generator.await_count == 3
    assert result.tools_used == ["get_inspection_result", "analyze_image_quality", "get_inspection_history"]
    trace = result.tool_execution_trace[-1]
    assert trace.origin == "BACKEND_POLICY" and trace.executed and trace.success
    assert trace.evidence_id == "E0003" and trace.comparison_inspection_id == "INSP-000001"
    assert [entry.origin for entry in result.tool_execution_trace[:2]] == ["GEMINI", "GEMINI"]
    storage.list_inspections.assert_called_once_with(limit=1000, product_id="PROD-001")
    assert any(fact.source_field == "/brightness_comparison/summary/historical_mean" and fact.observed_value == 120.0
               and fact.evidence_id == "E0003" for fact in result.observed_facts)
    packet = json.loads(generator.call_args_list[-1].kwargs["contents"][0].parts[0].text)
    assert any(entry["source_field"] == "/brightness_comparison/summary/scope"
        and entry["observed_value"] == "STORED_VALUES_ONLY_UNVERIFIED_MEASUREMENT_CONTRACT" for entry in packet["catalog"])
    assert any("参考" in text or "참고용" in text for text in result.limitations)
    assert storage.get_inspection.return_value.model_dump() == before
    storage.save_inspection.assert_not_called()


def test_model_proposed_history_is_executed_once_and_distinguished_from_policy():
    storage = comparison_storage([historical()])
    parallel = call_response(("analyze_image_quality", {"inspection_id": "INSP-000001"}),
        ("get_inspection_history", {"product_id": "TARGET-PRODUCT"}))
    service, generator = service_for(storage, [calls()[0], parallel, comparison_report])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and generator.await_count == 3
    assert result.tool_execution_trace[-1].origin == "GEMINI"
    assert result.tool_execution_trace[-1].arguments == {"product_id": "TARGET-PRODUCT", "limit": 5}
    storage.list_inspections.assert_called_once()


@pytest.mark.parametrize("records,error", [([], "DATA_UNAVAILABLE"), ([historical(mean=None)], None)])
def test_empty_and_incomparable_history_terminate_without_retry(records, error):
    storage = comparison_storage(records)
    service, generator = service_for(storage, [*calls(), comparison_report])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and generator.await_count == 3
    trace = result.tool_execution_trace[-1]
    assert trace.error_code == error and trace.executed
    assert trace.success == (error is None)
    assert (trace.evidence_id is None) == (error is not None)
    storage.list_inspections.assert_called_once()


def test_storage_error_is_fatal_preserved_and_sanitized_without_retry():
    storage = comparison_storage()
    storage.list_inspections.side_effect = StorageError("SECRET C:/internal/private")
    service, generator = service_for(storage, [*calls(), comparison_report])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "FAILED" and result.error_code == "STORAGE_ERROR"
    assert generator.await_count == 2
    trace = result.tool_execution_trace[-1]
    assert trace.origin == "BACKEND_POLICY" and trace.executed and not trace.success and trace.evidence_id is None
    assert "SECRET" not in result.model_dump_json() and "C:/internal" not in result.model_dump_json()
    assert storage.get_inspection.return_value.final_result == "REINSPECT"
    storage.list_inspections.assert_called_once()


def test_policy_respects_existing_call_budget():
    storage = comparison_storage([historical()])
    service, generator = service_for(storage, [*calls(), comparison_report], AgentLimits(max_tool_calls=2))
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "TOOL_CALL_LIMIT" and generator.await_count == 2
    assert not result.tool_execution_trace[-1].executed
    storage.list_inspections.assert_not_called()


def test_duplicate_model_history_in_one_batch_is_blocked_before_second_execution():
    storage = comparison_storage([historical()])
    parallel = call_response(("analyze_image_quality", {"inspection_id": "INSP-000001"}),
        ("get_inspection_history", {"product_id": "TARGET-PRODUCT"}),
        ("get_inspection_history", {"product_id": "TARGET-PRODUCT", "limit": 10}))
    service, generator = service_for(storage, [calls()[0], parallel])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "TOOL_REPEAT_LIMIT" and generator.await_count == 2
    assert not result.tool_execution_trace[-1].executed
    storage.list_inspections.assert_called_once()


def test_wrong_comparison_inspection_is_blocked_before_python():
    storage = comparison_storage([historical()])
    service, generator = service_for(storage, [calls()[0], call_response(("get_inspection_history", {
        "product_id": "TARGET-PRODUCT", "inspection_id": "INSP-000002"}))])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == "INSPECTION_SCOPE_MISMATCH" and generator.await_count == 2
    storage.list_inspections.assert_not_called()


def test_history_before_quality_is_reused_without_policy_requery():
    storage = comparison_storage([historical()])
    service, generator = service_for(storage, [calls()[0], call_response(("get_inspection_history", {
        "product_id": "TARGET-PRODUCT", "inspection_id": "INSP-000001"})), calls()[1], comparison_report])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and generator.await_count == 4
    assert all(trace.origin == "GEMINI" for trace in result.tool_execution_trace)
    storage.list_inspections.assert_called_once()


def test_required_logs_leave_model_an_opportunity_to_choose_history_without_policy_conflict():
    storage = comparison_storage([historical()])
    service, generator = service_for(storage, [*calls(), call_response(("get_inspection_history", {
        "product_id": "TARGET-PRODUCT"})), calls(True)[2], comparison_report])
    service.required_warning_event_codes = ("ANALYSIS_COMPLETED", "INSPECTION_COMPLETED")
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and generator.await_count == 5
    assert all(trace.origin == "GEMINI" for trace in result.tool_execution_trace)
    storage.list_inspections.assert_called_once()


def test_batched_warning_and_policy_history_stay_within_one_tool_round():
    storage = comparison_storage([historical()])
    service, generator = service_for(storage, [call_response(
        ("get_inspection_result", {"inspection_id": "INSP-000001"}),
        ("analyze_image_quality", {"inspection_id": "INSP-000001"})), comparison_report],
        AgentLimits(max_tool_rounds=1))
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and generator.await_count == 2
    assert [trace.round_number for trace in result.tool_execution_trace] == [1, 1, 1]


@pytest.mark.parametrize("mutation", ["missing", "not_object", "sample_type", "metrics_type"])
def test_missing_or_malformed_comparison_fails_closed(mutation):
    service, state = comparison_state()
    document = state.evidence["E0003"][1]
    if mutation == "missing":
        document.pop("brightness_comparison")
    elif mutation == "not_object":
        document["brightness_comparison"] = []
    elif mutation == "sample_type":
        document["brightness_comparison"]["samples"] = ["invalid"]
    else:
        document["brightness_comparison"]["samples"][0]["metrics"] = []
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        build_catalog(state)


def test_invalid_current_timestamp_is_unavailable_without_guessing_history():
    storage = comparison_storage([historical()])
    storage.get_inspection.return_value.timestamp = "invalid"
    summary = compare(storage)["brightness_comparison"]["summary"]
    assert summary["status"] == "CURRENT_UNAVAILABLE" and summary["sample_count"] == 0
    assert summary["historical_mean"] is None and summary["absolute_mean_difference"] is None


def test_normal_and_image_load_failure_do_not_force_history():
    storage = comparison_storage([historical()])
    storage.get_inspection.return_value = make_record()
    service, generator = service_for(storage, normal_responses())
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and result.inspection_snapshot["final_result"] == "OK"
    storage.list_inspections.assert_not_called()
    record = error_record()
    storage.get_inspection.return_value = record
    storage.get_logs.return_value = error_logs()
    payload = with_error_facts(report_payload(record, "INSPECTION_FAILED"), record)
    payload["recommended_checks"] = [{"check_code": "MANUAL_REINSPECTION", "evidence_refs": ["F0005"]}]
    service, generator = service_for(storage, [calls()[0], call_response(("get_execution_logs", {
        "inspection_id": "INSP-000001"})), report_response(payload)])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED" and result.inspection_snapshot["final_result"] == "ERROR"
    assert result.inspection_snapshot["result"] == "UNKNOWN" and record.metrics.get("mean") is None
    assert result.inspection_snapshot["defect_detection_status"] == "SKIPPED"
    storage.list_inspections.assert_not_called()


def test_real_temporary_jsonl_is_unchanged_by_comparison(tmp_path):
    storage = JsonlInspectionStorage(tmp_path / "inspections.jsonl", tmp_path / "logs.jsonl")
    storage.save_inspection(warning_storage().get_inspection.return_value)
    storage.save_inspection(historical())
    before = (tmp_path / "inspections.jsonl").read_bytes()
    response = compare(storage)
    assert response["brightness_comparison"]["summary"]["sample_count"] == 1
    assert (tmp_path / "inspections.jsonl").read_bytes() == before
