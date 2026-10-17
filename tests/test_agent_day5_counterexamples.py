"""Repeated offline counterexample checks for conditional Agent investigation."""

import asyncio
import json
from unittest.mock import patch

from google.genai import _api_client
import pytest

from backend.agent.service import CORE_FIELDS
from tests.test_agent_service import call_response, service_for, text_response
from tests.test_agent_tools import make_log, make_record
from tests.test_agent_warning_policy_experiment import warning_storage


@pytest.fixture(autouse=True)
def prohibit_live_gemini_and_http():
    with patch("backend.agent.service.genai.Client", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(_api_client.BaseApiClient, "request", side_effect=AssertionError("NETWORK_FORBIDDEN")) as sync_request, \
         patch.object(_api_client.BaseApiClient, "async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")) as async_request:
        yield
        sync_request.assert_not_called()
        async_request.assert_not_called()


def final_from_catalog(kwargs, *, cause=None, extra_fact=None):
    packet = json.loads(kwargs["contents"][0].parts[0].text)
    entries = packet["catalog"]

    def find(tool, field):
        return next(entry for entry in entries if entry["source_tool"] == tool and entry["source_field"] == field)

    selected = [find("get_inspection_result", f"/data/{field}") for field in CORE_FIELDS]
    verdict = find("get_inspection_result", "/data/final_result")
    check = "CONTINUE_MONITORING" if verdict["observed_value"] == "OK" else "MANUAL_REINSPECTION"
    causes = []
    if cause:
        causes = [f"{cause[0]}:{cause[1]}"]
    if extra_fact is not None:
        selected.append(extra_fact)
    payload = {
        "overall_summary": {
            "OK": "NORMAL_MODEL_RESULT",
            "NG": "PRODUCT_ANOMALY",
            "REINSPECT": "REINSPECTION_REQUIRED",
            "ERROR": "INSPECTION_FAILED",
        }[verdict["observed_value"]],
        "observed_fact_refs": list(dict.fromkeys(entry["token"] for entry in selected)),
        "possible_causes": causes,
        "recommended_checks": [f"{check}:{verdict['token']}"],
        "limitations": [],
    }
    return text_response(json.dumps(payload))


def warning_final(kwargs, *, include_history=False, fabricated_history=False):
    packet = json.loads(kwargs["contents"][0].parts[0].text)
    entries = packet["catalog"]
    selected = [entry for entry in entries if entry["source_tool"] == "get_inspection_result"
                and entry["source_field"] in {f"/data/{field}" for field in CORE_FIELDS}]
    quality = [entry for entry in entries if entry["source_tool"] == "analyze_image_quality"
               and entry["source_field"] in {
                   "/data/image_quality_status", "/data/threshold_status",
                   "/data/metrics/mean", "/data/metrics/std", "/data/metrics/min", "/data/metrics/max",
                   "/data/brightness_thresholds/low_threshold", "/data/brightness_thresholds/high_threshold",
               }]
    selected.extend(quality)
    if include_history:
        selected.extend(entry for entry in entries if entry["source_tool"] == "get_inspection_history"
                        and entry["source_field"] in {"/data/0/timestamp", "/data/0/metrics/mean"})
    refs = [entry["token"] for entry in selected]
    if fabricated_history:
        refs.append("K9999")
    quality_ref = next(entry["token"] for entry in quality if entry["source_field"] == "/data/image_quality_status")
    payload = {
        "overall_summary": "REINSPECTION_REQUIRED",
        "observed_fact_refs": refs,
        "possible_causes": [f"ILLUMINATION_CHANGE:{quality_ref}"],
        "recommended_checks": [f"LIGHTING_EXPOSURE_CHECK:{quality_ref}"],
        "limitations": [],
    }
    return text_response(json.dumps(payload))


def warning_turns(*, with_history):
    return [
        call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})),
        call_response(("analyze_image_quality", {"inspection_id": "INSP-000001"}),
                     ("get_inspection_history", {"product_id": "TARGET-PRODUCT", "limit": 5})),
        lambda **kwargs: warning_final(kwargs, include_history=with_history),
    ]


@pytest.mark.parametrize("repeat", range(1, 4), ids=lambda value: f"repeat-{value}")
def test_day5_t03_history_available_is_scoped_and_reported_from_actual_values(repeat):
    storage = warning_storage()
    current = storage.get_inspection.return_value
    current.metrics.update(mean=80.0, applied_thresholds={"low_threshold": 100.0, "high_threshold": 160.0})
    historical = make_record(
        inspection_id="INSP-000009", product_id=current.product_id,
        timestamp="2026-10-14T01:00:00Z", image_quality_status="NORMAL",
        metrics={"mean": 142.5, "std": 25.0, "min": 90.0, "max": 190.0,
                 "width": 900, "height": 900, "channels": 3},
    )
    storage.list_inspections.return_value = [historical]
    service, generator = service_for(storage, warning_turns(with_history=True))

    result = asyncio.run(service.analyze("INSP-000001"))

    assert result.analysis_status == "COMPLETED"
    assert result.inspection_snapshot["final_result"] == "REINSPECT"
    assert result.tools_used == ["get_inspection_result", "analyze_image_quality", "get_inspection_history"]
    history_trace = result.tool_execution_trace[-1]
    assert history_trace.arguments == {"product_id": "TARGET-PRODUCT", "limit": 5}
    assert history_trace.executed and history_trace.success and history_trace.evidence_id == "E0003"
    storage.list_inspections.assert_called_once_with(limit=1000, product_id=current.product_id)
    historical_facts = [fact for fact in result.observed_facts if fact.source_tool == "get_inspection_history"]
    assert {(fact.source_field, fact.observed_value) for fact in historical_facts} == {
        ("/data/0/timestamp", "2026-10-14T01:00:00+00:00"), ("/data/0/metrics/mean", 142.5),
    }
    assert all(fact.evidence_id == "E0003" for fact in historical_facts)
    assert not any(fact.observed_value == 111.25 for fact in result.observed_facts)
    final_packet = json.loads(generator.call_args_list[-1].kwargs["contents"][0].parts[0].text)
    assert any(entry["source_tool"] == "get_inspection_history" and entry["observed_value"] == 142.5
               for entry in final_packet["catalog"])
    assert generator.await_count == 3


@pytest.mark.parametrize("repeat", range(1, 4), ids=lambda value: f"repeat-{value}")
def test_day5_t03_empty_history_is_unavailable_and_never_fabricated(repeat):
    storage = warning_storage()
    storage.get_inspection.return_value.metrics.update(
        mean=80.0, applied_thresholds={"low_threshold": 100.0, "high_threshold": 160.0},
    )
    storage.list_inspections.return_value = []
    service, generator = service_for(storage, [
        *warning_turns(with_history=False)[:2],
        lambda **kwargs: warning_final(kwargs, include_history=False),
    ])

    result = asyncio.run(service.analyze("INSP-000001"))

    assert result.analysis_status == "COMPLETED"
    assert result.inspection_snapshot["final_result"] == "REINSPECT"
    history_trace = result.tool_execution_trace[-1]
    assert history_trace.executed and not history_trace.success
    assert history_trace.error_code == "DATA_UNAVAILABLE" and history_trace.evidence_id is None
    assert "get_inspection_history" not in result.tools_used
    assert not any(fact.source_tool == "get_inspection_history" for fact in result.observed_facts)
    assert any("일부 판정" in limitation for limitation in result.limitations)
    assert generator.await_count == 3


@pytest.mark.parametrize("repeat", range(1, 4), ids=lambda value: f"repeat-{value}")
def test_day5_t03_empty_history_rejects_fabricated_history_fact(repeat):
    storage = warning_storage()
    storage.get_inspection.return_value.metrics.update(
        mean=80.0, applied_thresholds={"low_threshold": 100.0, "high_threshold": 160.0},
    )
    storage.list_inspections.return_value = []
    responses = warning_turns(with_history=False)[:2]
    responses.append(lambda **kwargs: warning_final(kwargs, fabricated_history=True))
    service, generator = service_for(storage, responses)

    result = asyncio.run(service.analyze("INSP-000001"))

    assert result.analysis_status == "FAILED" and result.error_code == "EVIDENCE_MISMATCH"
    assert storage.get_inspection.return_value.final_result == "REINSPECT"
    assert generator.await_count == 3


def normal_with_warn_storage(*, foreign=False):
    storage = warning_storage()
    storage.get_inspection.return_value = make_record()
    event = make_log(
        inspection_id="INSP-000002" if foreign else "INSP-000001",
        stage="decision", event_code="BRIGHTNESS_LOW_WARNING", level="WARN", metrics={},
    )
    storage.get_logs.return_value = [event]
    return storage


@pytest.mark.parametrize("foreign", [False, True], ids=["same-inspection-unrelated", "different-inspection-filtered"])
@pytest.mark.parametrize("repeat", range(1, 4), ids=lambda value: f"repeat-{value}")
def test_day5_normal_unrelated_warn_does_not_support_a_cause(foreign, repeat):
    storage = normal_with_warn_storage(foreign=foreign)
    service, generator = service_for(storage, [
        call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}),
                      ("get_execution_logs", {"inspection_id": "INSP-000001"})),
        lambda **kwargs: final_from_catalog(
            kwargs,
            cause=("ILLUMINATION_CHANGE", "K9999") if foreign else None,
            extra_fact=None,
        ) if foreign else _unsafe_warn_report(kwargs),
    ])

    result = asyncio.run(service.analyze("INSP-000001"))

    assert result.analysis_status == "FAILED" and result.error_code == "EVIDENCE_MISMATCH"
    assert storage.get_inspection.return_value.result == storage.get_inspection.return_value.final_result == "OK"
    assert generator.await_count == 2
    if foreign:
        assert result.tool_execution_trace[1].error_code == "DATA_UNAVAILABLE"
        assert result.tool_execution_trace[1].evidence_id is None
        assert "get_execution_logs" not in result.tools_used
    else:
        assert result.tool_execution_trace[1].success and result.tool_execution_trace[1].evidence_id == "E0002"
    assert storage.save_inspection.call_count == storage.save_logs.call_count == 0


def _unsafe_warn_report(kwargs):
    packet = json.loads(kwargs["contents"][0].parts[0].text)
    event = next(entry for entry in packet["catalog"] if entry["source_tool"] == "get_execution_logs"
                 and entry["source_field"] == "/data/0/event_code")
    result = next(entry for entry in packet["catalog"] if entry["source_tool"] == "get_inspection_result"
                  and entry["source_field"] == "/data/final_result")
    core = [entry for entry in packet["catalog"] if entry["source_tool"] == "get_inspection_result"
            and entry["source_field"] in {f"/data/{field}" for field in CORE_FIELDS}]
    payload = {
        "overall_summary": "NORMAL_MODEL_RESULT",
        "observed_fact_refs": [entry["token"] for entry in core] + [event["token"]],
        "possible_causes": [f"ILLUMINATION_CHANGE:{event['token']}"],
        "recommended_checks": [f"CONTINUE_MONITORING:{result['token']}"],
        "limitations": [],
    }
    return text_response(json.dumps(payload))


@pytest.mark.parametrize("foreign", [False, True], ids=["same-inspection-unrelated", "different-inspection-filtered"])
@pytest.mark.parametrize("repeat", range(1, 4), ids=lambda value: f"repeat-{value}")
def test_day5_normal_unrelated_warn_safe_report_preserves_verdict(foreign, repeat):
    storage = normal_with_warn_storage(foreign=foreign)
    service, generator = service_for(storage, [
        call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}),
                      ("get_execution_logs", {"inspection_id": "INSP-000001"})),
        lambda **kwargs: final_from_catalog(kwargs),
    ])

    result = asyncio.run(service.analyze("INSP-000001"))

    assert result.analysis_status == "COMPLETED"
    assert result.inspection_snapshot["result"] == result.inspection_snapshot["final_result"] == "OK"
    assert result.possible_causes == []
    assert result.recommended_checks[0].check_code == "CONTINUE_MONITORING"
    assert result.tool_execution_trace[0].success
    if foreign:
        assert result.tool_execution_trace[1].error_code == "DATA_UNAVAILABLE"
        assert "get_execution_logs" not in result.tools_used
    else:
        assert result.tool_execution_trace[1].success
    assert generator.await_count == 2


def anomaly_storage():
    record = make_record(
        result="NG", final_result="NG", final_reason_code="PRODUCT_ANOMALY_DETECTED",
        anomaly_score=40.0, decision_threshold=34.1442,
    )
    from unittest.mock import Mock
    from backend.storage import InspectionStorageBase

    storage = Mock(spec=InspectionStorageBase)
    storage.get_inspection.return_value = record
    storage.get_logs.return_value = [make_log(event_code="IMAGE_LOADED", stage="load", level="INFO")]
    storage.list_inspections.return_value = []
    return storage


@pytest.mark.parametrize("log_mode", ["normal", "empty"], ids=["normal-log-only", "no-log-data"])
@pytest.mark.parametrize("repeat", range(1, 4), ids=lambda value: f"repeat-{value}")
def test_day5_suspected_anomaly_with_normal_or_empty_logs_stays_grounded(log_mode, repeat):
    storage = anomaly_storage()
    if log_mode == "empty":
        storage.get_logs.return_value = []
    responses = [
        call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})),
        call_response(("get_execution_logs", {"inspection_id": "INSP-000001"})),
        text_response("No root-cause evidence is available."),
        lambda **kwargs: final_from_catalog(kwargs),
    ]
    service, generator = service_for(storage, responses)

    result = asyncio.run(service.analyze("INSP-000001"))

    assert result.analysis_status == "COMPLETED"
    assert result.inspection_snapshot["result"] == result.inspection_snapshot["final_result"] == "NG"
    assert result.possible_causes == []
    assert result.recommended_checks[0].check_code == "MANUAL_REINSPECTION"
    assert result.tool_execution_trace[1].executed
    if log_mode == "empty":
        assert result.tool_execution_trace[1].error_code == "DATA_UNAVAILABLE"
        assert not result.tool_execution_trace[1].success and result.tool_execution_trace[1].evidence_id is None
        assert "get_execution_logs" not in result.tools_used
        assert any("일부 판정" in limitation for limitation in result.limitations)
    else:
        assert result.tool_execution_trace[1].success and result.tool_execution_trace[1].evidence_id == "E0002"
        assert "get_execution_logs" in result.tools_used
    assert generator.await_count == 4


@pytest.mark.parametrize("log_mode", ["normal", "empty"], ids=["normal-log-only", "no-log-data"])
@pytest.mark.parametrize("repeat", range(1, 4), ids=lambda value: f"repeat-{value}")
def test_day5_suspected_anomaly_cannot_turn_absent_logs_into_load_failure(log_mode, repeat):
    storage = anomaly_storage()
    if log_mode == "empty":
        storage.get_logs.return_value = []
    responses = [
        call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})),
        call_response(("get_execution_logs", {"inspection_id": "INSP-000001"})),
        text_response(),
        lambda **kwargs: _unsupported_acquisition_report(kwargs),
    ]
    service, generator = service_for(storage, responses)

    result = asyncio.run(service.analyze("INSP-000001"))

    assert result.analysis_status == "FAILED" and result.error_code == "EVIDENCE_MISMATCH"
    assert storage.get_inspection.return_value.result == storage.get_inspection.return_value.final_result == "NG"
    assert generator.await_count == 4


def _unsupported_acquisition_report(kwargs):
    packet = json.loads(kwargs["contents"][0].parts[0].text)
    result = next(entry for entry in packet["catalog"] if entry["source_tool"] == "get_inspection_result"
                  and entry["source_field"] == "/data/final_result")
    payload = {
        "overall_summary": "PRODUCT_ANOMALY",
        "observed_fact_refs": [entry["token"] for entry in packet["catalog"]
                               if entry["source_tool"] == "get_inspection_result"
                               and entry["source_field"] in {f"/data/{field}" for field in CORE_FIELDS}],
        "possible_causes": ["IMAGE_ACQUISITION:" + result["token"]],
        "recommended_checks": ["IMAGE_REGISTRATION_ACCESS_CHECK:" + result["token"]],
        "limitations": [],
    }
    return text_response(json.dumps(payload))


@pytest.mark.parametrize("repeat", range(1, 4), ids=lambda value: f"repeat-{value}")
def test_day5_tool_error_has_failed_trace_no_evidence_and_no_retry(repeat):
    storage = anomaly_storage()
    storage.get_logs.side_effect = RuntimeError("SECRET /private/token evaluation label")
    service, generator = service_for(storage, [
        call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}),
                      ("get_execution_logs", {"inspection_id": "INSP-000001"})),
    ])

    result = asyncio.run(service.analyze("INSP-000001"))

    assert result.analysis_status == "FAILED" and result.error_code == "STORAGE_ERROR"
    assert len(result.tool_execution_trace) == 2
    assert result.tool_execution_trace[0].success and result.tool_execution_trace[0].evidence_id == "E0001"
    failed = result.tool_execution_trace[1]
    assert failed.executed and not failed.success and failed.error_code == "STORAGE_ERROR"
    assert failed.evidence_id is None
    assert result.tools_used == ["get_inspection_result"]
    assert generator.await_count == 1
    serialized = result.model_dump_json()
    assert "SECRET" not in serialized and "/private/token" not in serialized and "evaluation label" not in serialized
    assert storage.get_inspection.return_value.final_result == "NG"

