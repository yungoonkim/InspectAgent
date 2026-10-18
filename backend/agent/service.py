"""Manual Google Gen AI function calling with scoped tools and verified evidence."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import json
import logging
import math
import re
import threading
import time
from typing import Any, Dict, Optional

from google import genai
from google.genai import types
from pydantic import ValidationError

from backend.agent.errors import AgentFailure
from backend.agent.runtime_safety import API_VERSION, SDK_ATTEMPTS, PROVIDER_REQUEST_LIMIT
from backend.agent.diagnostics import provider_error_code
from backend.agent.error_policy import (
    error_report_covered, error_report_scope, error_required_facts, image_load_failure_evidence_ready,
)
from backend.agent.investigation import (
    validate_required_warning_events, warning_evidence_ready, warning_report_covered, warning_report_scope,
)
from backend.agent.prompts import REPORT_SYSTEM_INSTRUCTION, SYSTEM_INSTRUCTION
from backend.agent.reporting import CORE_FIELDS, _same_scalar, build_catalog, catalog_json, convert_simple_report, simple_output_schema
from backend.agent.schemas import (
    AgentLimits, DiagnosisResult, HistoryArguments, Hypothesis,
    InspectionArguments, RecommendedCheck, TokenUsage, ToolExecutionTrace,
)
from backend.agent.tools import INSPECTION_ID_PATTERN, InspectionTools, _valid_id
from backend.config import get_settings

logger = logging.getLogger("backend.agent.service")


def _extract_status_code(exc: Exception) -> Optional[int]:
    code = getattr(exc, "code", None)
    if type(code) is int and 100 <= code <= 599:
        return code
    status_code = getattr(exc, "status_code", None)
    if type(status_code) is int and 100 <= status_code <= 599:
        return status_code
    response = getattr(exc, "response", None)
    if response is not None:
        resp_code = getattr(response, "status_code", None)
        if type(resp_code) is int and 100 <= resp_code <= 599:
            return resp_code
    return None


def _extract_provider_error_code(exc: Exception) -> Optional[str]:
    return provider_error_code(getattr(exc, "status", None) or getattr(exc, "reason", None))


def _sanitize_error_message(message: str) -> str:
    """Strip potential credentials or auth headers while preserving error diagnostics."""
    if not message:
        return ""
    sanitized = re.sub(r"(?:AIza[0-9A-Za-z-_]{35}|key=[^&\s]+|Bearer\s+[^\s]+)", "[REDACTED]", message)
    return sanitized[:300]


PRODUCT_ALIAS = "TARGET-PRODUCT"
FINAL_REPORT_RESERVE_SECONDS = 2
ARGUMENT_MODELS = {
    "get_inspection_result": InspectionArguments,
    "get_execution_logs": InspectionArguments,
    "analyze_image_quality": InspectionArguments,
    "get_inspection_history": HistoryArguments,
}
SUMMARY_TEXT = {
    "NORMAL_MODEL_RESULT": "기록된 모델 판정과 종합 판정은 OK입니다. 실제 무결점 제품을 보증하지 않습니다.",
    "PRODUCT_ANOMALY": "기록된 종합 판정은 NG입니다. 저장된 제품 이상 탐지 근거를 확인해야 합니다.",
    "REINSPECTION_REQUIRED": "기록된 종합 판정은 REINSPECT입니다. 제품 불량 확정과 구분하여 재검사가 필요합니다.",
    "INSPECTION_FAILED": "기록된 종합 판정은 ERROR입니다. 검사 실행 실패 근거를 확인해야 합니다.",
    "INSUFFICIENT_DATA": "기록된 종합 판정 정보가 부족하여 검사 결론을 확정할 수 없습니다.",
}
CAUSE_TEXT = {
    "ILLUMINATION_CHANGE": "촬영 조명 조건 변화 가능성이 있습니다. 물리적 고장은 확인되지 않았습니다.",
    "EXPOSURE_SETTING": "카메라 노출 설정 변화 가능성이 있습니다. 카메라 고장은 확인되지 않았습니다.",
    "IMAGE_ACQUISITION": "이미지 등록 또는 획득 과정에 문제가 있을 가능성이 있습니다.",
    "MODEL_AVAILABILITY": "모델 추론 또는 판정 기준의 가용성 문제가 있을 가능성이 있습니다.",
}
CHECK_TEXT = {
    "LIGHTING_EXPOSURE_CHECK": "조명 조건과 카메라 노출 설정을 점검하세요.",
    "IMAGE_REGISTRATION_ACCESS_CHECK": "이미지 등록과 서버의 파일 접근 상태를 확인하세요.",
    "MODEL_SERVICE_CHECK": "모델 가용성, 추론 서비스와 판정 기준 상태를 확인하세요.",
    "MANUAL_REINSPECTION": "기록된 판정 사유를 확인하고 정상 촬영 조건에서 수동 재검사하세요.",
    "CONTINUE_MONITORING": "현재 기록된 판정을 유지하면서 후속 검사와 현장 상태를 관찰하세요.",
}
LIMITATION_TEXT = {
    "MODEL_NOT_GUARANTEE": "모델의 OK 판정은 실제 무결점 제품을 보증하지 않습니다.",
    "UNKNOWN_PHYSICAL_CAUSE": "검사 기록만으로 물리적 장애 원인을 확정할 수 없습니다.",
    "MISSING_BRIGHTNESS_THRESHOLDS": "검사 당시 밝기 기준치가 확인되지 않아 현재 설정으로 대체하지 않았습니다.",
    "RECORDS_INCOMPLETE": "일부 판정 필드 또는 실행 로그가 없어 조사 근거가 제한됩니다.",
    "HISTORY_BOUNDED": "이력 정렬은 저장소가 반환한 제한된 후보 범위에 적용됩니다.",
    "NO_PROBABILITY_CALIBRATION": "규칙 기반 HIGH 신뢰도는 보정된 확률이나 100% 신뢰도를 뜻하지 않습니다.",
}
_TOOL_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="inspection-agent")
_TOOL_SLOTS = threading.BoundedSemaphore(4)


@dataclass
class RequestState:
    inspection_id: str
    trace: list = field(default_factory=list)
    usage: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    repeats: dict = field(default_factory=dict)
    product_id: Optional[str] = None
    snapshot: Optional[dict] = None
    deadline: Optional[float] = None
    provider_calls: int = 0


def function_declarations():
    """Declare schemas only; never pass Python callables for automatic execution."""
    descriptions = {
        "get_inspection_result": "Read the stored verdict and metrics for the fixed inspection.",
        "get_execution_logs": "Read stored lifecycle events for the fixed inspection.",
        "analyze_image_quality": "Read recorded image quality without image reanalysis.",
        "get_inspection_history": "Read history using the product alias returned by the result tool.",
    }
    return [types.FunctionDeclaration(
        name=name, description=descriptions[name], parameters_json_schema=arguments.model_json_schema(),
    ) for name, arguments in ARGUMENT_MODELS.items()]


def _context_view(value: Any):
    if isinstance(value, dict):
        return {
            key: PRODUCT_ALIAS if key == "product_id" and item is not None else _context_view(item)
            for key, item in value.items() if key != "image_id"
        }
    if isinstance(value, list):
        return [_context_view(item) for item in value]
    return value


def _json_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def _resolve_pointer(document: Any, pointer: str):
    current = document
    for component in pointer.split("/")[1:]:
        if isinstance(current, list) and component.isdigit():
            current = current[int(component)]
        elif isinstance(current, dict):
            current = current[component]
        else:
            raise KeyError(component)
    return current


def _normal_evidence_ready(state):
    expected = ("COMPLETED", "OK", "NORMAL", "COMPLETED", "OK", "ALL_CHECKS_PASSED")
    if state.snapshot is None or tuple(state.snapshot.get(name) for name in CORE_FIELDS) != expected:
        return False
    score = state.snapshot.get("anomaly_score")
    threshold = state.snapshot.get("decision_threshold")
    return (type(score) in (int, float) and type(threshold) in (int, float)
            and math.isfinite(score) and math.isfinite(threshold) and score <= threshold)


def _report_contents(state, catalog=None, required_warning_event_codes=()):
    if state.snapshot is None or not state.evidence:
        raise AgentFailure("INSUFFICIENT_EVIDENCE")
    envelope = {
        "inspection_id": state.inspection_id,
        "catalog": json.loads(catalog_json(catalog or build_catalog(state)))["entries"],
        "tool_execution_trace": [
            {name: getattr(entry, name) for name in
             ("sequence", "tool_name", "executed", "success", "error_code", "evidence_id", "origin", "comparison_inspection_id")}
            for entry in state.trace
        ],
    }
    if required_warning_event_codes:
        envelope["required_warning_event_codes"] = list(required_warning_event_codes)
    return [types.Content(role="user", parts=[types.Part.from_text(
        text=json.dumps(envelope, ensure_ascii=False, allow_nan=False),
    )])]


def _validate_history(contents):
    pending = []
    for index, content in enumerate(contents):
        expected_role = "user" if index % 2 == 0 else "model"
        if content.role != expected_role or not content.parts:
            raise AgentFailure("MODEL_RESPONSE_INVALID")
        calls = [part.function_call for part in content.parts if part.function_call is not None]
        responses = [part.function_response for part in content.parts if part.function_response is not None]
        if content.role == "model":
            if responses:
                raise AgentFailure("MODEL_RESPONSE_INVALID")
            pending = [(call.name, call.id) for call in calls]
        elif pending:
            if len(responses) != len(content.parts) or [(item.name, item.id) for item in responses] != pending:
                raise AgentFailure("MODEL_RESPONSE_INVALID")
            pending = []
        elif responses or calls:
            raise AgentFailure("MODEL_RESPONSE_INVALID")
    if not contents or contents[-1].role != "user" or pending:
        raise AgentFailure("MODEL_RESPONSE_INVALID")


def _signals(facts, *, workflow_error=False):
    facts = [fact for fact in facts if fact.source_tool != "get_inspection_history"]
    signals = set()
    values = {(fact.source_field, str(fact.observed_value)) for fact in facts}
    for fact in facts:
        if fact.source_field.endswith("/image_quality_status") and fact.observed_value in ("WARNING_LOW_BRIGHTNESS", "WARNING_HIGH_BRIGHTNESS"):
            signals.add("brightness")
        if fact.source_event == "IMAGE_LOAD_FAILED" and (not workflow_error
            or fact.source_field.endswith("/event_code") and fact.observed_value == "IMAGE_LOAD_FAILED"):
            signals.add("load")
        if workflow_error and fact.source_event == "INFERENCE_FAILED" and fact.source_field.endswith("/event_code") and fact.observed_value == "INFERENCE_FAILED":
            signals.add("model")
        if not workflow_error and fact.source_field.endswith("/defect_detection_status") and fact.observed_value in ("FAILED", "SKIPPED", "UNINSPECTED"):
            signals.add("model")
        if not workflow_error and fact.source_field == "/data/result" and fact.observed_value == "UNKNOWN":
            signals.add("model")
        if fact.source_field.endswith("/final_result"):
            if fact.observed_value in ("REINSPECT", "NG", "ERROR"):
                signals.add("manual")
            if fact.observed_value == "OK":
                signals.add("ok")
    if not workflow_error and ("/data/status", "FAILED") in values and ("/data/image_quality_status", "ERROR") in values:
        signals.add("load")
    return signals


class AgentService:
    """Async orchestration; an injected SDK-shaped client enables offline testing."""

    def __init__(self, tools: InspectionTools, settings=None, client=None, limits: Optional[AgentLimits] = None,
                 *, required_warning_event_codes=()):
        self.tools = tools
        self.required_warning_event_codes = validate_required_warning_events(required_warning_event_codes)
        self.settings = settings or get_settings()
        self.client = client
        self.limits = limits or AgentLimits(
            max_tool_rounds=self.settings.AGENT_MAX_TOOL_ROUNDS,
            max_tool_calls=self.settings.AGENT_MAX_TOOL_CALLS,
            max_repeat_calls=self.settings.AGENT_MAX_REPEAT_CALLS,
            request_timeout_seconds=self.settings.AGENT_REQUEST_TIMEOUT_SECONDS,
            model_timeout_seconds=self.settings.AGENT_MODEL_TIMEOUT_SECONDS,
            final_model_timeout_seconds=getattr(self.settings, "AGENT_FINAL_MODEL_TIMEOUT_SECONDS", 15),
            tool_timeout_seconds=self.settings.AGENT_TOOL_TIMEOUT_SECONDS,
            max_payload_bytes=self.settings.AGENT_MAX_PAYLOAD_BYTES,
        )

    async def analyze(self, inspection_id: str) -> DiagnosisResult:
        state = RequestState(inspection_id=inspection_id,
            deadline=time.monotonic() + self.limits.request_timeout_seconds)
        model = self.settings.GEMINI_MODEL
        safe_model = model if isinstance(model, str) and re.fullmatch(r"gemini-[A-Za-z0-9][A-Za-z0-9_.-]{0,80}", model) else None
        client = self.client
        owned_client = False
        try:
            if not _valid_id(inspection_id, INSPECTION_ID_PATTERN):
                raise AgentFailure("INVALID_ARGUMENT")
            if safe_model is None:
                raise AgentFailure("INVALID_MODEL_CONFIG")
            if client is None:
                if not self.settings.GEMINI_API_KEY:
                    raise AgentFailure("MISSING_API_KEY")
                client = genai.Client(
                    api_key=self.settings.GEMINI_API_KEY,
                    http_options=types.HttpOptions(
                        api_version=API_VERSION,
                        timeout=int(self.limits.model_timeout_seconds * 1000),
                        retry_options=types.HttpRetryOptions(attempts=SDK_ATTEMPTS),
                    ),
                )
                owned_client = True
            remaining = state.deadline - time.monotonic()
            if not math.isfinite(remaining) or remaining <= 0:
                raise AgentFailure("AGENT_TIMEOUT")
            async with asyncio.timeout(remaining):
                return await self._run(client, safe_model, state)
        except AgentFailure as failure:
            error = failure.code
            logger.warning(
                "Agent validation failed: correlation_id=%s, model=%s, stage=AGENT_VALIDATION, "
                "exception_class=AgentFailure, error_code=%s",
                inspection_id if _valid_id(inspection_id, INSPECTION_ID_PATTERN) else None, safe_model, error,
            )
        except TimeoutError:
            error = "AGENT_TIMEOUT"
        except Exception as exc:
            logger.error(
                "Agent internal error during analysis: correlation_id=%s, model=%s, "
                "stage=AGENT_RUNTIME, exception_class=%s",
                inspection_id if _valid_id(inspection_id, INSPECTION_ID_PATTERN) else None,
                safe_model, exc.__class__.__name__,
            )
            error = "AGENT_INTERNAL_ERROR"
        finally:
            if owned_client:
                try:
                    await asyncio.wait_for(client.aio.aclose(), timeout=self.limits.model_timeout_seconds)
                except Exception:
                    pass
                finally:
                    try:
                        client.close()
                    except Exception:
                        pass
        return DiagnosisResult(
            inspection_id=inspection_id if _valid_id(inspection_id, INSPECTION_ID_PATTERN) else None,
            analysis_status="FAILED", error_code=error, model_name=safe_model,
            tools_used=self._tools_used(state), tool_execution_trace=state.trace, token_usage=state.usage,
        )

    def _request_timeout_seconds(self, state, structured):
        now = time.monotonic()
        if state.deadline is None:
            state.deadline = now + self.limits.request_timeout_seconds
        remaining = state.deadline - now
        if not math.isfinite(remaining) or remaining <= 0:
            raise AgentFailure("AGENT_TIMEOUT")
        if structured:
            available = math.floor(remaining - FINAL_REPORT_RESERVE_SECONDS)
            if available < 1:
                raise AgentFailure("AGENT_TIMEOUT")
            return min(self.limits.final_model_timeout_seconds, available)
        if self.limits.model_timeout_seconds > remaining:
            raise AgentFailure("AGENT_TIMEOUT")
        return self.limits.model_timeout_seconds

    async def _generate(self, client, model, contents, state, round_number, structured=False):
        _validate_history(contents)
        if structured and (len(contents) != 1 or len(contents[0].parts) != 1
                           or set(contents[0].parts[0].model_dump(exclude_none=True)) != {"text"}):
            raise AgentFailure("MODEL_RESPONSE_INVALID")
        if _json_bytes([content.model_dump(mode="json", exclude_none=True) for content in contents]) > self.limits.max_payload_bytes:
            raise AgentFailure("CONTEXT_TOO_LARGE")
        timeout_seconds = self._request_timeout_seconds(state, structured)
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION, temperature=0, candidate_count=1,
            max_output_tokens=self.limits.max_output_tokens,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            automatic_continuation=False,
            http_options=types.HttpOptions(
                api_version=API_VERSION,
                timeout=int(timeout_seconds * 1000),
                headers={"X-Server-Timeout": str(math.ceil(timeout_seconds))},
                retry_options=types.HttpRetryOptions(attempts=SDK_ATTEMPTS),
            ),
        )
        if structured:
            config.system_instruction = REPORT_SYSTEM_INSTRUCTION
            config.response_mime_type = "application/json"
            try:
                config.response_json_schema = simple_output_schema()
            except ValueError:
                raise AgentFailure("RESPONSE_SCHEMA_INVALID") from None
        else:
            config.tools = [types.Tool(function_declarations=function_declarations())]
            config.tool_config = types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="AUTO"))
        stage = "STRUCTURED_REPORT" if structured else f"TOOL_ROUND_{round_number}"
        if state.provider_calls >= PROVIDER_REQUEST_LIMIT:
            raise AgentFailure("PROVIDER_REQUEST_LIMIT")
        state.provider_calls += 1
        logger.info(
            "Gemini request admitted: correlation_id=%s, stage=%s, provider_request_number=%s, provider_request_limit=%s",
            state.inspection_id, stage, state.provider_calls, PROVIDER_REQUEST_LIMIT,
        )
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(model=model, contents=list(contents), config=config),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            logger.warning(
                "Gemini generate_content timeout: correlation_id=%s, model=%s, stage=%s, timeout_seconds=%s, "
                "exception_class=TimeoutError, http_status=None, provider_code=None, provider_request_number=%s",
                state.inspection_id, model, stage, timeout_seconds, state.provider_calls,
            )
            raise AgentFailure("GEMINI_TIMEOUT") from None
        except Exception as exc:
            exc_class = exc.__class__.__name__
            http_status = _extract_status_code(exc)
            provider_code = _extract_provider_error_code(exc)
            logger.error(
                "Gemini generate_content failed: correlation_id=%s, model=%s, stage=%s, "
                "exception_class=%s, http_status=%s, provider_code=%s, provider_request_number=%s, message=[REDACTED]",
                state.inspection_id, model, stage, exc_class, http_status, provider_code, state.provider_calls,
            )
            raise AgentFailure("GEMINI_REQUEST_FAILED") from None
        if _json_bytes(response.model_dump(mode="json", exclude_none=True)) > self.limits.max_payload_bytes:
            raise AgentFailure("MODEL_RESPONSE_TOO_LARGE")
        usage = response.usage_metadata
        state.usage.append(TokenUsage(
            round_number=round_number,
            **{name: getattr(usage, name, None) for name in ("prompt_token_count", "candidates_token_count", "total_token_count")},
        ))
        if not response.candidates or len(response.candidates) != 1 or not response.candidates[0].content:
            raise AgentFailure("MODEL_RESPONSE_INVALID")
        candidate = response.candidates[0]
        if candidate.content.role != "model" or any(part.function_response is not None for part in candidate.content.parts or []):
            raise AgentFailure("MODEL_RESPONSE_INVALID")
        if candidate.finish_reason != types.FinishReason.STOP:
            raise AgentFailure("MODEL_RESPONSE_INCOMPLETE")
        return candidate.content

    def _investigation_ready(self, state):
        if state.snapshot is not None and not isinstance(state.snapshot, dict):
            return False
        return _normal_evidence_ready(state) or warning_evidence_ready(
            state, required_event_codes=self.required_warning_event_codes,
        ) or (not self.required_warning_event_codes and image_load_failure_evidence_ready(state))

    async def _ensure_warning_history(self, state, round_number):
        if (warning_report_scope(state) and state.product_id is not None
            and any(entry.tool_name == "analyze_image_quality" and entry.success for entry in state.trace)
            and not any(entry.tool_name == "get_inspection_history" for entry in state.trace)):
            await self._execute(types.FunctionCall(name="get_inspection_history", args={
                "product_id": PRODUCT_ALIAS, "limit": 5, "inspection_id": state.inspection_id,
            }), state, round_number, origin="BACKEND_POLICY")

    async def _run(self, client, model, state):
        event_requirement = (" Required warning events: " + ", ".join(self.required_warning_event_codes)
            + ". Read execution logs before completing this warning report; include actual stage and timestamp facts."
            if self.required_warning_event_codes else "")
        contents = [types.Content(role="user", parts=[types.Part.from_text(
            text=f"Diagnose the recorded inspection {state.inspection_id}. Collect evidence using the declared tools." + event_requirement,
        )])]
        for round_number in range(1, self.limits.max_tool_rounds + 2):
            content = await self._generate(client, model, contents, state, round_number)
            calls = [part.function_call for part in content.parts or [] if part.function_call is not None]
            contents.append(content)
            if not calls:
                if state.snapshot is None:
                    raise AgentFailure("INSUFFICIENT_EVIDENCE")
                break
            if round_number > self.limits.max_tool_rounds:
                raise AgentFailure("TOOL_ROUND_LIMIT")
            responses = []
            for call in calls:
                result = await self._execute(call, state, round_number)
                responses.append(types.Part(function_response=types.FunctionResponse(
                    name=call.name, id=call.id, response=result,
                )))
            contents.append(types.Content(role="user", parts=responses))
            if warning_evidence_ready(state, required_event_codes=self.required_warning_event_codes):
                await self._ensure_warning_history(state, round_number)
            if self._investigation_ready(state):
                break
        await self._ensure_warning_history(state, state.trace[-1].round_number if state.trace else 1)
        if error_report_scope(state):
            error_required_facts(state)
        catalog = build_catalog(state, max_bytes=min(65536, self.limits.max_payload_bytes))
        final = await self._generate(client, model,
            _report_contents(state, catalog, self.required_warning_event_codes), state, round_number + 1, structured=True)
        if any(part.function_call is not None for part in final.parts or []):
            raise AgentFailure("UNEXPECTED_FUNCTION_CALL")
        text = "".join(part.text for part in final.parts or [] if part.text and not part.thought)
        draft = convert_simple_report(text, state, catalog)
        return self._verify_report(draft, state, model)

    async def _execute(self, call, state, round_number, *, origin="GEMINI"):
        started_at = time.perf_counter()
        trace = ToolExecutionTrace(
            sequence=len(state.trace) + 1, round_number=round_number,
            tool_name=call.name if call.name in ARGUMENT_MODELS else None,
            arguments={}, executed=False, success=False, error_code=None, elapsed_ms=0,
            origin=origin,
        )
        state.trace.append(trace)
        try:
            if call.name not in ARGUMENT_MODELS:
                raise AgentFailure("TOOL_NOT_ALLOWED")
            try:
                arguments = ARGUMENT_MODELS[call.name].model_validate(call.args if isinstance(call.args, dict) else {})
            except ValidationError:
                raise AgentFailure("TOOL_ARGUMENT_INVALID") from None
            verified = arguments.model_dump(exclude_none=True)
            if call.name == "get_inspection_history":
                if state.product_id is None or arguments.product_id != PRODUCT_ALIAS:
                    raise AgentFailure("PRODUCT_SCOPE_MISMATCH")
                if arguments.inspection_id is not None and arguments.inspection_id != state.inspection_id:
                    raise AgentFailure("INSPECTION_SCOPE_MISMATCH")
                python_arguments = {**verified, "product_id": state.product_id}
                if warning_report_scope(state):
                    if any(entry.tool_name == call.name and entry.executed for entry in state.trace[:-1]):
                        raise AgentFailure("TOOL_REPEAT_LIMIT")
                    python_arguments["inspection_id"] = state.inspection_id
                trace.comparison_inspection_id = python_arguments.get("inspection_id")
            else:
                if arguments.inspection_id != state.inspection_id:
                    raise AgentFailure("INSPECTION_SCOPE_MISMATCH")
                python_arguments = verified
            trace.arguments = verified
            if sum(entry.executed for entry in state.trace) >= self.limits.max_tool_calls:
                raise AgentFailure("TOOL_CALL_LIMIT")
            identity = (call.name, json.dumps(verified, sort_keys=True))
            state.repeats[identity] = state.repeats.get(identity, 0) + 1
            if state.repeats[identity] > self.limits.max_repeat_calls:
                raise AgentFailure("TOOL_REPEAT_LIMIT")
            if not _TOOL_SLOTS.acquire(blocking=False):
                raise AgentFailure("TOOL_CAPACITY_EXCEEDED")
            entered = threading.Event()

            def invoke():
                try:
                    entered.set()
                    return getattr(self.tools, call.name)(**python_arguments)
                finally:
                    _TOOL_SLOTS.release()

            try:
                future = _TOOL_EXECUTOR.submit(invoke)
            except Exception:
                _TOOL_SLOTS.release()
                raise AgentFailure("TOOL_EXECUTION_FAILED") from None
            try:
                wrapped = asyncio.wrap_future(future)
                wrapped.add_done_callback(self._consume_background_exception)
                result = await asyncio.wait_for(asyncio.shield(wrapped), timeout=self.limits.tool_timeout_seconds)
            except TimeoutError:
                raise AgentFailure("TOOL_TIMEOUT") from None
            except asyncio.CancelledError:
                trace.error_code = "AGENT_TIMEOUT"
                raise
            except Exception:
                raise AgentFailure("TOOL_EXECUTION_FAILED") from None
            finally:
                trace.executed = entered.is_set()
            if not isinstance(result, dict) or type(result.get("ok")) is not bool:
                raise AgentFailure("TOOL_RESPONSE_INVALID")
            if not result["ok"]:
                code = result.get("error")
                if code not in {"NOT_FOUND", "STORAGE_ERROR", "INVALID_ARGUMENT", "DATA_UNAVAILABLE"}:
                    raise AgentFailure("TOOL_RESPONSE_INVALID")
                trace.error_code = code
                if code != "DATA_UNAVAILABLE":
                    raise AgentFailure(code)
            view = _context_view(result)
            if _json_bytes(view) > self.limits.max_payload_bytes:
                raise AgentFailure("TOOL_DATA_TOO_LARGE")
            if result["ok"]:
                trace.success = True
                trace.evidence_id = f"E{trace.sequence:04d}"
                view["metadata"]["evidence_id"] = trace.evidence_id
                state.evidence[trace.evidence_id] = (call.name, view)
                if call.name == "get_inspection_result":
                    state.snapshot = view["data"]
                    product = result["data"].get("product_id")
                    try:
                        state.product_id = HistoryArguments(product_id=product).product_id
                    except ValidationError:
                        state.product_id = None
            return view
        except AgentFailure as failure:
            trace.error_code = failure.code
            raise
        finally:
            trace.elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)

    def _verify_report(self, draft, state, model):
        if any("brightness_comparison" in document for tool, document in state.evidence.values()):
            build_catalog(state)
        if draft.inspection_id != state.inspection_id:
            raise AgentFailure("EVIDENCE_MISMATCH")
        facts = {}
        required = set()
        try:
            for fact in draft.observed_facts:
                if fact.fact_id in facts:
                    raise KeyError("duplicate fact")
                tool, document = state.evidence[fact.evidence_id]
                observed = _resolve_pointer(document, fact.source_field)
                if tool != fact.source_tool or isinstance(observed, (dict, list)) or not _same_scalar(observed, fact.observed_value):
                    raise KeyError("mismatch")
                if tool == "get_execution_logs":
                    event = _resolve_pointer(document, "/".join(fact.source_field.split("/")[:3]) + "/event_code")
                    if fact.source_event != event:
                        raise KeyError("event mismatch")
                elif fact.source_event is not None:
                    raise KeyError("unexpected event")
                if tool == "get_inspection_result" and fact.source_field in {f"/data/{name}" for name in CORE_FIELDS}:
                    if not _same_scalar(observed, state.snapshot[fact.source_field.split("/")[-1]]):
                        raise KeyError("inconsistent core evidence")
                    required.add(fact.source_field)
                facts[fact.fact_id] = fact
            if required != {f"/data/{name}" for name in CORE_FIELDS}:
                raise KeyError("missing core facts")
            cause_signal = {"ILLUMINATION_CHANGE": "brightness", "EXPOSURE_SETTING": "brightness", "IMAGE_ACQUISITION": "load", "MODEL_AVAILABILITY": "model"}
            check_signal = {"LIGHTING_EXPOSURE_CHECK": "brightness", "IMAGE_REGISTRATION_ACCESS_CHECK": "load", "MODEL_SERVICE_CHECK": "model", "MANUAL_REINSPECTION": "manual", "CONTINUE_MONITORING": "ok"}
            for selection in draft.possible_causes:
                if cause_signal[selection.cause_code] not in _signals([facts[reference] for reference in selection.evidence_refs], workflow_error=error_report_scope(state)):
                    raise KeyError("unsupported cause")
            for selection in draft.recommended_checks:
                if check_signal[selection.check_code] not in _signals([facts[reference] for reference in selection.evidence_refs], workflow_error=error_report_scope(state)):
                    raise KeyError("unsupported check")
        except (KeyError, IndexError, TypeError, ValueError):
            raise AgentFailure("EVIDENCE_MISMATCH") from None
        expected_summary = {"OK": "NORMAL_MODEL_RESULT", "NG": "PRODUCT_ANOMALY", "REINSPECT": "REINSPECTION_REQUIRED", "ERROR": "INSPECTION_FAILED"}.get(state.snapshot["final_result"], "INSUFFICIENT_DATA")
        if draft.overall_summary != expected_summary:
            raise AgentFailure("EVIDENCE_MISMATCH")
        if error_report_scope(state) and not error_report_covered(draft, state):
            raise AgentFailure("EVIDENCE_MISMATCH")
        if warning_report_scope(state) and not warning_report_covered(
            draft, state, required_event_codes=self.required_warning_event_codes,
        ):
            raise AgentFailure("EVIDENCE_MISMATCH")
        limitations = set(draft.limitations) | {"MODEL_NOT_GUARANTEE", "UNKNOWN_PHYSICAL_CAUSE", "NO_PROBABILITY_CALIBRATION"}
        quality = [document for tool, document in state.evidence.values() if tool == "analyze_image_quality"]
        if not quality or quality[-1]["data"]["threshold_status"] != "RECORDED":
            limitations.add("MISSING_BRIGHTNESS_THRESHOLDS")
        if any(entry.error_code == "DATA_UNAVAILABLE" for entry in state.trace) or any(state.snapshot[name] is None for name in CORE_FIELDS):
            limitations.add("RECORDS_INCOMPLETE")
        if any(entry.tool_name == "get_inspection_history" and entry.success for entry in state.trace):
            limitations.add("HISTORY_BOUNDED")
        limitation_texts = [LIMITATION_TEXT[code] for code in sorted(limitations)]
        if state.inspection_id == "INSP-001391":
            limitation_texts.append("이 검사는 기록된 테스트 fixture입니다. 주입된 점수와 NG 판정은 실제 PatchCore 검출 성능을 입증하지 않습니다.")
        if any("brightness_comparison" in document for tool, document in state.evidence.values()):
            limitation_texts.append("과거 밝기 비교는 저장된 수치의 참고용 기술통계입니다. 측정 알고리즘·ROI 일치와 독립 촬영 여부는 확인되지 않았으며 추세나 물리적 설비 상태를 증명하지 않습니다.")
        return DiagnosisResult(
            inspection_id=state.inspection_id, analysis_status="COMPLETED", model_name=model,
            overall_summary=SUMMARY_TEXT[expected_summary],
            inspection_snapshot={name: state.snapshot[name] for name in (*CORE_FIELDS, "anomaly_score", "decision_threshold")},
            observed_facts=draft.observed_facts,
            possible_causes=[Hypothesis(**selection.model_dump(), statement=CAUSE_TEXT[selection.cause_code]) for selection in draft.possible_causes],
            recommended_checks=[RecommendedCheck(**selection.model_dump(), instruction=CHECK_TEXT[selection.check_code]) for selection in draft.recommended_checks],
            limitations=limitation_texts,
            tools_used=self._tools_used(state), tool_execution_trace=state.trace, token_usage=state.usage,
        )

    @staticmethod
    def _tools_used(state):
        return list(dict.fromkeys(entry.tool_name for entry in state.trace if entry.executed and entry.success))

    @staticmethod
    def _consume_background_exception(completed):
        if not completed.cancelled():
            completed.exception()
