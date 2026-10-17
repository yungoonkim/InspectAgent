"""Stored T06 evidence through offline SDK transport; no evaluation files are read."""

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from google import genai
from google.genai import _api_client, types
import httpx
import pytest

from backend.agent import service as agent_module
from backend.agent.errors import AgentFailure
from backend.agent.reporting import build_catalog, catalog_json
from backend.agent.schemas import AgentLimits, DiagnosisDraft
from backend.agent.service import AgentService, CORE_FIELDS, RequestState
from backend.agent.tools import InspectionTools
from backend.storage import JsonlInspectionStorage
from scripts.agent_validation_measurements import plan_attempt
from tests.test_agent_service import report_payload


ROOT = Path(__file__).resolve().parents[1]
TARGET = "INSP-001406"
FORBIDDEN = (
    "ground_truth", "evaluation_answers", "evaluation_private", "actual_label",
    "defect_class", "false_negative", "broken_large", "broken_small", "contamination",
    "OFFLINE_ONLY_CANARY", "bottle_image_mask_pairs",
)


@pytest.fixture(autouse=True)
def forbid_network():
    with patch.object(httpx.HTTPTransport, "handle_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("NETWORK_FORBIDDEN")), \
         patch.object(_api_client.BaseApiClient, "_use_aiohttp", return_value=False):
        yield


@pytest.fixture
def tools():
    return InspectionTools(JsonlInspectionStorage(ROOT / "data/inspections.jsonl", ROOT / "data/inspection_logs.jsonl"))


def assert_isolated(value):
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    for marker in FORBIDDEN:
        assert marker not in serialized


def test_stored_t06_all_four_tools_exclude_evaluation_fields(tools):
    record = tools._storage.get_inspection(TARGET)
    result = tools.get_inspection_result(TARGET)
    assert tuple(result["data"][name] for name in CORE_FIELDS) == (
        "COMPLETED", "OK", "NORMAL", "COMPLETED", "OK", "ALL_CHECKS_PASSED",
    )
    assert result["data"]["anomaly_score"] <= result["data"]["decision_threshold"]
    responses = [result, tools.analyze_image_quality(TARGET), tools.get_execution_logs(TARGET),
                 tools.get_inspection_history(record.product_id)]
    assert all(response["ok"] for response in responses)
    assert_isolated(responses)
    assert_isolated(agent_module._context_view(responses))


@pytest.mark.parametrize("mutation", [None, "NG", "REINSPECT", "truth_claim", "guarantee", "token", "extra_truth"])
@pytest.mark.parametrize("final_timeout", [15, 30])
def test_real_sdk_mock_transport_preserves_isolated_normal_path(tools, mutation, final_timeout):
    requests = []
    captured = {}
    original_ready = AgentService._investigation_ready
    original_convert = agent_module.convert_simple_report

    def ready(instance, state):
        captured["state"] = copy.deepcopy(state)
        return original_ready(instance, state)

    def convert(raw, state, catalog):
        captured["conversion_input"] = json.loads(raw)
        return original_convert(raw, state, catalog)

    def respond(request):
        body = json.loads(request.content)
        assert_isolated(body)
        assert "image_id" not in json.dumps(body)
        expected_timeout = 15 if not requests else final_timeout
        assert request.extensions["timeout"] == dict.fromkeys(("connect", "read", "write", "pool"), float(expected_timeout))
        assert request.headers["X-Server-Timeout"] == str(expected_timeout)
        requests.append(body)
        if len(requests) == 1:
            assert TARGET in body["contents"][0]["parts"][0]["text"]
            parts = [{"functionCall": {"name": "get_inspection_result", "args": {"inspection_id": TARGET}, "id": "result-call"}}]
        else:
            assert len(requests) == 2
            assert "tools" not in body and "toolConfig" not in body
            assert len(body["contents"]) == 1 and body["contents"][0]["role"] == "user"
            packet = json.loads(body["contents"][0]["parts"][0]["text"])
            entries = packet["catalog"]
            core = {name: next(entry["token"] for entry in entries if entry["source_field"] == f"/data/{name}") for name in CORE_FIELDS}
            payload = {"overall_summary": "NORMAL_MODEL_RESULT", "observed_fact_refs": list(core.values()),
                       "possible_causes": [], "recommended_checks": ["CONTINUE_MONITORING:" + core["final_result"]], "limitations": []}
            if mutation in {"NG", "REINSPECT"}:
                payload["overall_summary"] = {"NG": "PRODUCT_ANOMALY", "REINSPECT": "REINSPECTION_REQUIRED"}[mutation]
            elif mutation == "truth_claim":
                payload["overall_summary"] = "This product has an actual defect."
            elif mutation == "guarantee":
                payload["overall_summary"] = "This product is completely defect-free."
            elif mutation == "token":
                payload["observed_fact_refs"].append("K9999")
            elif mutation == "extra_truth":
                payload["actual_label"] = "OFFLINE_ONLY_CANARY"
            parts = [{"text": json.dumps(payload)}]
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}]})

    client = genai.Client(api_key="OFFLINE_FAKE_KEY", vertexai=False, http_options=types.HttpOptions(
        api_version="v1beta", timeout=15000, retry_options=types.HttpRetryOptions(attempts=1),
        async_client_args={"transport": httpx.MockTransport(respond)}))
    service = AgentService(tools, settings=SimpleNamespace(GEMINI_MODEL="gemini-3.8-flash"), client=client,
                           limits=AgentLimits(final_model_timeout_seconds=final_timeout))

    async def run():
        try:
            return await service.analyze(TARGET)
        finally:
            await client.aio.aclose()

    try:
        with patch.object(AgentService, "_investigation_ready", ready), patch.object(agent_module, "convert_simple_report", convert):
            result = asyncio.run(run())
    finally:
        client.close()
    assert len(requests) == 2
    state = captured["state"]
    assert original_ready(service, state)
    assert not agent_module.error_report_scope(state)
    assert not agent_module.warning_report_scope(state)
    assert_isolated(state.evidence)
    assert_isolated(json.loads(catalog_json(build_catalog(state))))
    assert state.evidence["E0001"][1]["data"]["product_id"] == "TARGET-PRODUCT"
    assert len(state.trace) == 1 and state.trace[0].success
    assert state.trace[0].arguments == {"inspection_id": TARGET}
    assert state.trace[0].evidence_id == "E0001"
    if mutation is None:
        assert result.analysis_status == "COMPLETED"
        assert result.inspection_snapshot["result"] == result.inspection_snapshot["final_result"] == "OK"
        assert result.inspection_snapshot["final_reason_code"] == "ALL_CHECKS_PASSED"
        assert len(result.observed_facts) == 6
        assert "무결점 제품을 보증하지 않습니다" in result.overall_summary
        assert result.possible_causes == []
        assert_isolated(captured["conversion_input"])
        assert_isolated(result.model_dump())
    else:
        assert result.analysis_status == "FAILED"
        assert result.error_code in {"EVIDENCE_MISMATCH", "RESPONSE_SCHEMA_INVALID"}
        assert result.observed_facts == []


@pytest.mark.parametrize("mutation", ["evidence", "pointer", "invented_fact"])
def test_stored_t06_draft_rejects_unsupported_evidence(tools, mutation):
    state = RequestState(TARGET)
    service = AgentService(tools, settings=SimpleNamespace(GEMINI_MODEL="gemini-3.8-flash"), client=SimpleNamespace(), limits=AgentLimits())
    asyncio.run(service._execute(types.FunctionCall(name="get_inspection_result", args={"inspection_id": TARGET}), state, 1))
    payload = report_payload(tools._storage.get_inspection(TARGET))
    payload["inspection_id"] = TARGET
    fact = payload["observed_facts"][0]
    if mutation == "evidence":
        fact["evidence_id"] = "E9999"
    elif mutation == "pointer":
        fact["source_field"] = "/data/missing"
    else:
        fact["observed_value"] = "Actual defect exists"
    with pytest.raises(AgentFailure, match="EVIDENCE_MISMATCH"):
        service._verify_report(DiagnosisDraft.model_validate(payload), state, "gemini-3.8-flash")


def test_preparation_plan_supports_fixed_t06_without_creating_ready(tmp_path):
    manifest = plan_attempt(tmp_path, "t06_operational_groundtruth_isolated_1", TARGET, scenario="T06", final_timeout=15)
    assert manifest["scenario"] == "T06" and manifest["inspection_id"] == TARGET
    assert manifest["timeouts_seconds"]["final_ceiling"] == 15
    assert list(tmp_path.iterdir()) == []
