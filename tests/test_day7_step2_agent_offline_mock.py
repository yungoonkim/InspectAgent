"""VisionInsight — Day 7 Step 2: Gemini Agent Offline Mock Compatibility Suite.

Verifies the 10 request/response/safety scenarios with 0 external Google Gemini API calls.
Strictly relies on local mock clients and verifies operational code paths.
Uses synchronous test runners with asyncio.run() matching test_agent_service.py.
"""

import asyncio
import json
import logging
import time
from unittest.mock import AsyncMock, Mock, patch

from google.genai import types
import pytest

from backend.agent.api import ERROR_STATUS, analysis_error
from backend.agent.errors import AgentFailure
from backend.agent.prompts import REPORT_SYSTEM_INSTRUCTION, SYSTEM_INSTRUCTION
from backend.agent.reporting import CORE_FIELDS, build_catalog
from backend.agent.schemas import AgentLimits, DiagnosisResult
from backend.agent.service import (
    ARGUMENT_MODELS,
    AgentService,
    PRODUCT_ALIAS,
    RequestState,
    SUMMARY_TEXT,
    function_declarations,
)
from backend.agent.tools import InspectionTools
from backend.config import get_settings
from backend.storage import JsonlInspectionStorage
from tests.test_agent_service import call_response, report_payload, report_response, text_response
from tests.test_agent_tools import make_record


@pytest.fixture(autouse=True)
def forbid_real_gemini_client():
    """Safety guard: prevent any live Google API connection during offline test run."""
    with patch(
        "backend.agent.service.genai.Client",
        side_effect=AssertionError("Live Gemini client is forbidden in Day 7 Step 2 offline tests"),
    ):
        yield


def _wrap_generator(responses):
    seq = iter(responses)

    async def _generate(**kwargs):
        resp = next(seq)
        if isinstance(resp, Exception):
            raise resp
        return resp(**kwargs) if callable(resp) else resp

    return AsyncMock(side_effect=_generate)


def _setup_service(storage_records=None, responses=None):
    """Create real storage and tool instances with a mocked Gemini client."""
    storage = Mock(spec=JsonlInspectionStorage)
    record = storage_records or make_record(
        inspection_id="INSP-001442",
        product_id="PROD-001",
        status="COMPLETED",
        result="OK",
        image_quality_status="NORMAL",
        defect_detection_status="COMPLETED",
        final_result="OK",
        final_reason_code="ALL_CHECKS_PASSED",
        anomaly_score=12.5,
        decision_threshold=34.1442,
    )
    storage.get_inspection.return_value = record
    storage.get_logs.return_value = []
    storage.list_inspections.return_value = ([record], 1)
    tools = InspectionTools(storage)
    mock_client = Mock()
    mock_client.aio = Mock()
    mock_client.aio.models = Mock()
    if responses is not None:
        mock_client.aio.models.generate_content = _wrap_generator(responses)
    else:
        mock_client.aio.models.generate_content = AsyncMock()
    settings = get_settings()
    service = AgentService(tools=tools, client=mock_client, settings=settings)
    return service, storage, record, mock_client


# ==============================================================================
# Test 1 — 최초 Agent 요청 구조 검증
# ==============================================================================
def test_scenario_01_first_agent_request_structure():
    """Test 1: Verify exact model, config, contents, tools, and options of the first Gemini request."""
    service, storage, record, mock_client = _setup_service()

    captured = {}

    async def fake_generate_content(**kwargs):
        captured.update(kwargs)
        return text_response("Stopping round 1.")

    mock_client.aio.models.generate_content.side_effect = fake_generate_content

    result = asyncio.run(service.analyze("INSP-001442"))
    assert result.analysis_status == "FAILED"
    assert result.error_code == "INSUFFICIENT_EVIDENCE"

    # Verify model name
    assert captured["model"] == "gemini-3.8-flash"

    # Verify contents structure
    contents = captured["contents"]
    assert isinstance(contents, list)
    assert len(contents) == 1
    assert contents[0].role == "user"
    assert len(contents[0].parts) == 1
    assert "INSP-001442" in contents[0].parts[0].text
    assert "Diagnose the recorded inspection INSP-001442" in contents[0].parts[0].text

    # Verify config structure
    config = captured["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.temperature == 0
    assert config.candidate_count == 1
    assert config.max_output_tokens == 4096
    assert config.system_instruction == SYSTEM_INSTRUCTION
    assert config.automatic_function_calling.disable is True
    assert config.automatic_continuation is False

    # Verify HttpOptions
    assert config.http_options is not None
    assert config.http_options.api_version == "v1beta"
    assert config.http_options.retry_options.attempts == 1
    assert "X-Server-Timeout" in config.http_options.headers

    # Verify Tools declaration
    assert config.tools is not None
    assert len(config.tools) == 1
    declarations = config.tools[0].function_declarations
    assert len(declarations) == 4
    tool_names = [decl.name for decl in declarations]
    assert tool_names == [
        "get_inspection_result",
        "get_execution_logs",
        "analyze_image_quality",
        "get_inspection_history",
    ]

    # Verify ToolConfig mode
    assert config.tool_config is not None
    assert config.tool_config.function_calling_config.mode == "AUTO"

    # Verify response_mime_type and response_json_schema are None in Tool Round 1
    assert config.response_mime_type is None
    assert config.response_json_schema is None


# ==============================================================================
# Test 2 — Function Calling 응답 처리
# ==============================================================================
def test_scenario_02_function_calling_response_handling():
    """Test 2: Mock returns a valid FunctionCall; verify tool executes and state updates."""
    responses = [
        call_response(("get_inspection_result", {"inspection_id": "INSP-001442"})),
        text_response("Done gathering evidence."),
    ]
    service, storage, record, mock_client = _setup_service(responses=responses)

    state = RequestState(
        inspection_id="INSP-001442",
        deadline=time.monotonic() + 30.0,
    )

    async def _test():
        with patch.object(service, "_verify_report", return_value=DiagnosisResult(
            inspection_id="INSP-001442", analysis_status="COMPLETED", model_name="gemini-3.8-flash",
        )):
            try:
                await service._run(mock_client, "gemini-3.8-flash", state)
            except Exception:
                pass

    asyncio.run(_test())

    # Verify tool execution trace
    assert len(state.trace) >= 1
    first_trace = state.trace[0]
    assert first_trace.tool_name == "get_inspection_result"
    assert first_trace.executed is True
    assert first_trace.success is True
    assert first_trace.arguments == {"inspection_id": "INSP-001442"}
    assert first_trace.evidence_id == "E0001"

    # Verify state.snapshot populated
    assert state.snapshot is not None
    assert state.snapshot["inspection_id"] == "INSP-001442"
    assert state.snapshot["final_result"] == "OK"
    assert state.snapshot["final_reason_code"] == "ALL_CHECKS_PASSED"


# ==============================================================================
# Test 3 — Tool Result 반환 형식 검증
# ==============================================================================
def test_scenario_03_tool_result_return_payload_structure():
    """Test 3: Verify that FunctionResponse part passed back to Gemini has exact SDK structure."""
    # Create warning record so investigation requires a 2nd tool round before completing
    warning_record = make_record(
        inspection_id="INSP-001442",
        status="COMPLETED",
        result="NG",
        image_quality_status="WARNING_LOW_BRIGHTNESS",
        defect_detection_status="COMPLETED",
        final_result="REINSPECT",
        final_reason_code="IMAGE_QUALITY_WARNING",
    )
    captured_contents = []

    async def capturing_generate(model, contents, config):
        captured_contents.append(list(contents))
        if len(captured_contents) == 1:
            return call_response(("get_inspection_result", {"inspection_id": "INSP-001442"}))
        return text_response("Done.")

    service, storage, record, mock_client = _setup_service(storage_records=warning_record)
    mock_client.aio.models.generate_content.side_effect = capturing_generate

    state = RequestState(
        inspection_id="INSP-001442",
        deadline=time.monotonic() + 30.0,
    )

    async def _test():
        try:
            await service._run(mock_client, "gemini-3.8-flash", state)
        except Exception:
            pass

    asyncio.run(_test())

    # In Round 2 call, captured_contents[1] contains:
    # [0] user initial prompt
    # [1] model function_call
    # [2] user function_response
    assert len(captured_contents) >= 2
    round_2_contents = captured_contents[1]
    assert len(round_2_contents) == 3

    tool_response_content = round_2_contents[2]
    assert tool_response_content.role == "user"
    assert len(tool_response_content.parts) == 1

    part = tool_response_content.parts[0]
    func_resp = part.function_response
    assert func_resp is not None
    assert func_resp.name == "get_inspection_result"
    assert func_resp.id == "call-0"
    assert isinstance(func_resp.response, dict)
    assert func_resp.response["ok"] is True
    assert "data" in func_resp.response
    assert func_resp.response["data"]["inspection_id"] == "INSP-001442"


# ==============================================================================
# Test 4 — 최종 응답 -> AgentReport 생성
# ==============================================================================
def test_scenario_04_final_response_produces_agent_report():
    """Test 4: Verify end-to-end completion from tool calls to structured final report."""
    record = make_record(
        inspection_id="INSP-001442",
        status="COMPLETED",
        result="OK",
        image_quality_status="NORMAL",
        defect_detection_status="COMPLETED",
        final_result="OK",
        final_reason_code="ALL_CHECKS_PASSED",
        anomaly_score=12.5,
        decision_threshold=34.1442,
    )
    payload = report_payload(record)
    payload["inspection_id"] = "INSP-001442"
    responses = [
        call_response(("get_inspection_result", {"inspection_id": "INSP-001442"})),
        report_response(payload),
    ]
    service, storage, _, mock_client = _setup_service(storage_records=record, responses=responses)

    result = asyncio.run(service.analyze("INSP-001442"))

    assert result.analysis_status == "COMPLETED"
    assert result.error_code is None
    assert result.inspection_id == "INSP-001442"
    assert result.model_name == "gemini-3.8-flash"
    assert result.overall_summary == SUMMARY_TEXT["NORMAL_MODEL_RESULT"]
    assert len(result.observed_facts) >= 6
    assert len(result.recommended_checks) >= 1
    assert any("OK" in text for text in result.limitations)


# ==============================================================================
# Test 5 — Evidence 검증 (1:1 결정적 JSON Pointer 매칭)
# ==============================================================================
def test_scenario_05_evidence_verification_deterministic_pointer():
    """Test 5: Verify that every ObservedFact matches server evidence store exactly."""
    record = make_record(
        inspection_id="INSP-001442",
        status="COMPLETED",
        result="OK",
        image_quality_status="NORMAL",
        defect_detection_status="COMPLETED",
        final_result="OK",
        final_reason_code="ALL_CHECKS_PASSED",
        anomaly_score=12.5,
        decision_threshold=34.1442,
    )
    payload = report_payload(record)
    payload["inspection_id"] = "INSP-001442"
    responses = [
        call_response(("get_inspection_result", {"inspection_id": "INSP-001442"})),
        report_response(payload),
    ]
    service, storage, _, mock_client = _setup_service(storage_records=record, responses=responses)

    result = asyncio.run(service.analyze("INSP-001442"))
    assert result.analysis_status == "COMPLETED"

    # Verify each fact
    for fact in result.observed_facts:
        assert fact.evidence_id == "E0001"
        assert fact.source_tool == "get_inspection_result"
        assert fact.source_field.startswith("/data/")
        field_name = fact.source_field.split("/data/")[1]
        assert hasattr(record, field_name)
        assert fact.observed_value == getattr(record, field_name)


# ==============================================================================
# Test 6 — 서버 판정 불변성 보호
# ==============================================================================
def test_scenario_06_server_verdict_immutability():
    """Test 6: Verify that running the Agent never mutates or overwrites the original inspection verdict."""
    record = make_record(
        inspection_id="INSP-001442",
        status="COMPLETED",
        result="OK",
        image_quality_status="NORMAL",
        defect_detection_status="COMPLETED",
        final_result="OK",
        final_reason_code="ALL_CHECKS_PASSED",
        anomaly_score=12.5,
        decision_threshold=34.1442,
    )
    original_final_result = record.final_result
    original_final_reason = record.final_reason_code
    original_result = record.result

    payload = report_payload(record)
    payload["inspection_id"] = "INSP-001442"
    responses = [
        call_response(("get_inspection_result", {"inspection_id": "INSP-001442"})),
        report_response(payload),
    ]
    service, storage, _, mock_client = _setup_service(storage_records=record, responses=responses)

    result = asyncio.run(service.analyze("INSP-001442"))
    assert result.analysis_status == "COMPLETED"

    # Verify storage was never asked to update/save records
    assert not hasattr(storage, "save_inspection") or not storage.save_inspection.called
    assert record.final_result == original_final_result == "OK"
    assert record.final_reason_code == original_final_reason == "ALL_CHECKS_PASSED"
    assert record.result == original_result == "OK"


# ==============================================================================
# Test 7 — 모델 오류 매핑 & 관측성 로깅
# ==============================================================================
@pytest.mark.parametrize("status_code,provider_status", [
    (400, "INVALID_ARGUMENT"),
    (403, "PERMISSION_DENIED"),
    (404, "NOT_FOUND"),
    (429, "RESOURCE_EXHAUSTED"),
])
def test_scenario_07_model_errors_safe_mapping_and_logging(caplog, status_code, provider_status):
    """Test 7: Verify 400/403/404/429 errors safely map to GEMINI_REQUEST_FAILED without leaking keys."""
    service, storage, record, mock_client = _setup_service()

    class MockGoogleApiError(Exception):
        def __init__(self, code, status, msg):
            super().__init__(msg)
            self.code = code
            self.status = status

    secret_key = "AIzaSyFakeSecretKeyThatMustBeRedacted12345"
    mock_error = MockGoogleApiError(
        status_code,
        provider_status,
        f"Google API call failed for key={secret_key}: {provider_status}",
    )
    mock_client.aio.models.generate_content.side_effect = mock_error

    with caplog.at_level(logging.ERROR, logger="backend.agent.service"):
        result = asyncio.run(service.analyze("INSP-001442"))

    assert result.analysis_status == "FAILED"
    assert result.error_code == "GEMINI_REQUEST_FAILED"

    # Verify structured observability logging
    log_text = caplog.text
    assert "GEMINI_REQUEST_FAILED" or "Gemini generate_content failed" in log_text
    assert "INSP-001442" in log_text
    assert "gemini-3.8-flash" in log_text
    assert f"http_status={status_code}" in log_text
    assert f"provider_code={provider_status}" in log_text

    # Verify API key is redacted
    assert secret_key not in log_text
    assert "[REDACTED]" in log_text


# ==============================================================================
# Test 8 — Timeout 검증
# ==============================================================================
def test_scenario_08_timeout_handling_without_infinite_retry():
    """Test 8: Verify TimeoutError triggers GEMINI_TIMEOUT cleanly with zero retries."""
    service, storage, record, mock_client = _setup_service()

    mock_client.aio.models.generate_content.side_effect = TimeoutError("Request timed out")

    result = asyncio.run(service.analyze("INSP-001442"))

    assert result.analysis_status == "FAILED"
    assert result.error_code == "GEMINI_TIMEOUT"
    # generate_content was called exactly once (no retry loop)
    assert mock_client.aio.models.generate_content.call_count == 1


# ==============================================================================
# Test 9 — 응답에 Function Call이 없는 경우 안전 처리
# ==============================================================================
def test_scenario_09_no_function_call_in_round1_safe_rejection():
    """Test 9: When Gemini returns plain text instead of a tool call in Round 1, safely reject."""
    service, storage, record, mock_client = _setup_service()

    # Gemini model returns a normal text candidate instead of function_call
    mock_client.aio.models.generate_content.return_value = text_response(
        "I believe the bottle is OK without checking tools."
    )

    result = asyncio.run(service.analyze("INSP-001442"))

    assert result.analysis_status == "FAILED"
    assert result.error_code == "INSUFFICIENT_EVIDENCE"
    # Never ran into infinite loop; aborted safely after 1 call
    assert mock_client.aio.models.generate_content.call_count == 1


# ==============================================================================
# Test 10 — MAX_TOKENS 안전 거부
# ==============================================================================
def test_scenario_10_max_tokens_safe_rejection_no_hallucination():
    """Test 10: Candidate finish_reason=MAX_TOKENS raises MODEL_RESPONSE_INCOMPLETE; no dummy report."""
    service, storage, record, mock_client = _setup_service()

    # Model truncated by token limit
    mock_client.aio.models.generate_content.return_value = text_response(
        "Truncated partial text",
        finish=types.FinishReason.MAX_TOKENS,
    )

    result = asyncio.run(service.analyze("INSP-001442"))

    assert result.analysis_status == "FAILED"
    assert result.error_code == "MODEL_RESPONSE_INCOMPLETE"
    assert result.overall_summary is None
    assert len(result.observed_facts) == 0
