"""Production token-report flow with offline SDK responses, never live Gemini."""

import asyncio
from dataclasses import replace
import json
from unittest.mock import Mock, patch

from google.genai import _api_client
import pytest

from backend.agent.api import get_agent_service
from backend.agent.reporting import build_catalog, simple_output_schema
from backend.agent.schemas import AnalysisResponse, DiagnosisDraft
from backend.agent.service import CORE_FIELDS
from backend.main import app
from backend.storage import InspectionStorageBase
from tests.test_agent_api import file_hashes, harness, prohibit_real_sdk_client
from tests.test_agent_service import call_response, service_for, text_response
from tests.test_agent_tools import make_log, make_record
from tests.agent_error_fixtures import error_logs, error_record, error_tokens


@pytest.fixture(autouse=True)
def no_external_requests():
    with patch.object(_api_client.BaseApiClient, "request", side_effect=AssertionError("NETWORK_FORBIDDEN")) as sync_request, \
         patch.object(_api_client.BaseApiClient, "async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")) as async_request:
        yield
        sync_request.assert_not_called()
        async_request.assert_not_called()


def simple_payload(kwargs):
    packet = json.loads(kwargs["contents"][0].parts[0].text)
    entries = packet["catalog"]
    core = {name: next(entry for entry in entries if entry["source_tool"] == "get_inspection_result"
        and entry["source_field"] == f"/data/{name}") for name in CORE_FIELDS}
    verdict = core["final_result"]["observed_value"]
    summary = {"OK": "NORMAL_MODEL_RESULT", "NG": "PRODUCT_ANOMALY", "REINSPECT": "REINSPECTION_REQUIRED",
               "ERROR": "INSPECTION_FAILED"}.get(verdict, "INSUFFICIENT_DATA")
    check = "CONTINUE_MONITORING" if verdict == "OK" else "MANUAL_REINSPECTION"
    return {"overall_summary": summary, "observed_fact_refs": [entry["token"] for entry in core.values()]
            + (error_tokens(packet["catalog"]) if verdict == "ERROR" else []),
            "possible_causes": [], "recommended_checks": [check + ":" + core["final_result"]["token"]], "limitations": []}


def simple_response(**kwargs):
    return text_response(json.dumps(simple_payload(kwargs)))


@pytest.mark.parametrize("scenario", ["normal", "warning", "failed", "stored_ok"])
def test_production_simple_report_flow_keeps_tools_evidence_and_verdicts(scenario):
    changes = {}
    additional = None
    if scenario == "warning":
        changes = {"image_quality_status": "WARNING_LOW_BRIGHTNESS", "final_result": "REINSPECT",
                   "final_reason_code": "IMAGE_QUALITY_WARNING"}
        additional = "analyze_image_quality"
    elif scenario == "failed":
        changes = {"status": "FAILED", "result": "UNKNOWN", "image_quality_status": "ERROR",
                   "defect_detection_status": "SKIPPED", "final_result": "ERROR", "final_reason_code": "INSPECTION_FAILED"}
        additional = "get_execution_logs"
    storage = Mock(spec=InspectionStorageBase)
    storage.get_inspection.return_value = make_record(**changes)
    if scenario == "failed":
        storage.get_inspection.return_value = error_record()
    storage.get_logs.return_value = [make_log(event_code="IMAGE_LOAD_FAILED")]
    if scenario == "failed":
        storage.get_logs.return_value = error_logs()
    original = storage.get_inspection.return_value.model_dump()

    def final(**kwargs):
        payload = simple_payload(kwargs)
        if additional:
            packet = json.loads(kwargs["contents"][0].parts[0].text)
            entry = next(entry for entry in packet["catalog"] if entry["source_tool"] == additional
                and entry["source_field"] == ("/data/image_quality_status" if scenario == "warning" else "/data/0/event_code"))
            if entry["token"] not in payload["observed_fact_refs"]:
                payload["observed_fact_refs"].append(entry["token"])
            if scenario == "warning":
                payload["observed_fact_refs"].extend(item["token"] for item in packet["catalog"]
                    if item["source_tool"] == additional and item["token"] not in payload["observed_fact_refs"])
            cause, check = ("ILLUMINATION_CHANGE", "LIGHTING_EXPOSURE_CHECK") if scenario == "warning" else (
                "IMAGE_ACQUISITION", "IMAGE_REGISTRATION_ACCESS_CHECK")
            payload["possible_causes"] = [cause + ":" + entry["token"]]
            payload["recommended_checks"] = [check + ":" + entry["token"]]
        return text_response(json.dumps(payload))

    responses = [call_response(("get_inspection_result", {"inspection_id": "INSP-000001"}))]
    if additional:
        responses.append(call_response((additional, {"inspection_id": "INSP-000001"})))
    responses.append(final)
    service, generator = service_for(storage, responses)
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "COMPLETED"
    assert generator.await_count == (3 if additional else 2)
    assert result.tools_used == ["get_inspection_result", *([additional] if additional else [])]
    assert all(entry.executed and entry.success for entry in result.tool_execution_trace)
    assert storage.get_inspection.return_value.model_dump() == original
    assert all(result.inspection_snapshot[name] == original[name] for name in CORE_FIELDS)
    packet = json.loads(generator.call_args_list[-1].kwargs["contents"][0].parts[0].text)
    assert set(packet) == {"inspection_id", "catalog", "tool_execution_trace"}
    assert all(entry["evidence_id"] in {trace.evidence_id for trace in result.tool_execution_trace}
               for entry in packet["catalog"])
    draft = DiagnosisDraft(inspection_id=result.inspection_id,
        overall_summary=simple_payload(generator.call_args_list[-1].kwargs)["overall_summary"],
        observed_facts=result.observed_facts, possible_causes=[entry.model_dump(include={"cause_code", "evidence_refs"})
        for entry in result.possible_causes], recommended_checks=[entry.model_dump(include={"check_code", "evidence_refs"})
        for entry in result.recommended_checks], limitations=[])
    assert DiagnosisDraft.model_validate(draft.model_dump()) == draft
    config = generator.call_args_list[-1].kwargs["config"]
    assert config.response_json_schema == simple_output_schema()
    assert config.tools is None and config.tool_config is None and config.response_schema is None
    assert config.http_options.retry_options.attempts == 1 and config.http_options.timeout == 15000
    storage.save_inspection.assert_not_called()
    storage.save_logs.assert_not_called()


def invalid_payload(kwargs, mutation):
    payload = simple_payload(kwargs)
    if mutation == "missing":
        del payload["limitations"]
    elif mutation == "type":
        payload["observed_fact_refs"] = [False]
    elif mutation in {"unknown_token", "evidence_id", "pointer"}:
        payload["observed_fact_refs"][0] = {"unknown_token": "K9999", "evidence_id": "E9999", "pointer": "/data/missing"}[mutation]
    elif mutation == "missing_core":
        payload["observed_fact_refs"].pop()
    elif mutation == "duplicate":
        payload["observed_fact_refs"].append(payload["observed_fact_refs"][0])
    elif mutation == "unselected":
        packet = json.loads(kwargs["contents"][0].parts[0].text)
        token = next(entry["token"] for entry in packet["catalog"] if entry["token"] not in payload["observed_fact_refs"])
        payload["recommended_checks"] = ["CONTINUE_MONITORING:" + token]
    elif mutation in {"cause", "check"}:
        field, code = ("possible_causes", "ILLUMINATION_CHANGE") if mutation == "cause" else ("recommended_checks", "MODEL_SERVICE_CHECK")
        payload[field] = [code + ":" + payload["observed_fact_refs"][0]]
    elif mutation == "verdict":
        payload["overall_summary"] = "PRODUCT_ANOMALY"
    elif mutation in {"inspection_id", "product_id", "observed_value", "trace", "provenance"}:
        payload[{"trace": "tool_execution_trace", "provenance": "source_field"}.get(mutation, mutation)] = "UNTRUSTED"
    return text_response(json.dumps(payload))


@pytest.mark.parametrize("mutation", ["missing", "type", "unknown_token", "evidence_id", "pointer", "missing_core",
    "duplicate", "unselected", "cause", "check", "verdict", "inspection_id", "product_id", "observed_value", "trace", "provenance"])
def test_http_rejects_invalid_simple_reports_without_repair(harness, mutation):
    service, generator = service_for(harness.storage, [
        call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})),
        lambda **kwargs: invalid_payload(kwargs, mutation),
    ])
    app.dependency_overrides[get_agent_service] = lambda: service
    before = file_hashes(harness)
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 502
    expected = "RESPONSE_SCHEMA_INVALID" if mutation in {"missing", "type", "duplicate", "inspection_id",
        "product_id", "observed_value", "trace", "provenance"} else "EVIDENCE_MISMATCH"
    assert response.json()["detail"]["error_code"] == expected
    assert generator.await_count == 2
    assert file_hashes(harness) == before
    assert "UNTRUSTED" not in response.text


def test_http_accepts_raw_simple_report_with_unchanged_response_contract(harness):
    service, generator = service_for(harness.storage, [
        call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})), simple_response,
    ])
    app.dependency_overrides[get_agent_service] = lambda: service
    before = file_hashes(harness)
    response = harness.client.post("/analyze/INSP-000001")
    assert response.status_code == 200
    result = AnalysisResponse.model_validate(response.json())
    assert result.analysis_status == "COMPLETED"
    assert result.inspection_result == result.final_result == "OK"
    assert {fact.evidence_id for fact in result.observed_facts} == {"E0001"}
    assert len(result.tool_execution_trace) == 1 and result.tool_execution_trace[0].success
    assert generator.await_count == 2 and file_hashes(harness) == before


@pytest.mark.parametrize("mutation", ["owner", "pointer", "evidence_id", "value"])
def test_request_catalog_cannot_override_the_server_evidence(mutation):
    storage = Mock(spec=InspectionStorageBase)
    storage.get_inspection.return_value = make_record()
    service, generator = service_for(storage, [
        call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})), simple_response,
    ])

    def forged(state, **kwargs):
        catalog = build_catalog(state, **kwargs)
        if mutation == "owner":
            return replace(catalog, inspection_id="INSP-000002")
        entry = catalog.entries[0]
        entry = replace(entry, **{
            {"pointer": "source_field", "evidence_id": "evidence_id", "value": "observed_value"}[mutation]:
            {"pointer": "/data/unrecorded", "evidence_id": "E9999", "value": "FAKE"}[mutation],
        })
        return replace(catalog, entries=(entry, *catalog.entries[1:]))

    with patch("backend.agent.service.build_catalog", side_effect=forged):
        result = asyncio.run(service.analyze("INSP-000001"))
    assert result.analysis_status == "FAILED" and result.error_code == "EVIDENCE_MISMATCH"
    assert generator.await_count == 2


@pytest.mark.parametrize("text,error", [("not JSON", "FINAL_JSON_INVALID"), ('{"x":NaN}', "FINAL_JSON_INVALID"),
    ('{"x":1,"x":2}', "FINAL_JSON_INVALID"), ('{}', "RESPONSE_SCHEMA_INVALID")])
def test_raw_invalid_json_fails_in_production_without_second_attempt(text, error):
    storage = Mock(spec=InspectionStorageBase)
    storage.get_inspection.return_value = make_record()
    service, generator = service_for(storage, [
        call_response(("get_inspection_result", {"inspection_id": "INSP-000001"})), text_response(text),
    ])
    result = asyncio.run(service.analyze("INSP-000001"))
    assert result.error_code == error and generator.await_count == 2


def test_experimental_imports_share_the_operational_converter_without_duplication():
    from scripts import agent_simple_report_prototype as experimental
    from backend.agent import reporting
    assert experimental.convert_simple_report is reporting.convert_simple_report
    assert experimental.build_catalog is reporting.build_catalog
    assert experimental.SimpleReport is reporting.SimpleReport
