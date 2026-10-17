"""Read-only analysis HTTP boundary and lazy application-scoped SDK lifecycle."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from google import genai
from google.genai import types
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from backend.agent.schemas import AnalysisError, AnalysisErrorResponse, AnalysisResponse, DiagnosisResult
from backend.agent.service import AgentService, CORE_FIELDS, SUMMARY_TEXT
from backend.agent.tools import INSPECTION_ID_PATTERN, InspectionTools, _valid_id
from backend.config import Settings, get_settings
from backend.storage import InspectionStorageBase, get_inspection_storage


ERROR_STATUS = {
    "INVALID_ARGUMENT": 422,
    "NOT_FOUND": 404,
    "MISSING_API_KEY": 503,
    "INVALID_MODEL_CONFIG": 503,
    "AGENT_CONFIG_CHANGED": 503,
    "STORAGE_ERROR": 503,
    "DATA_UNAVAILABLE": 503,
    "TOOL_CAPACITY_EXCEEDED": 503,
    "GEMINI_REQUEST_FAILED": 502,
    "GEMINI_TIMEOUT": 504,
    "AGENT_TIMEOUT": 504,
    "TOOL_TIMEOUT": 504,
    "TOOL_NOT_ALLOWED": 502,
    "TOOL_ARGUMENT_INVALID": 502,
    "INSPECTION_SCOPE_MISMATCH": 502,
    "PRODUCT_SCOPE_MISMATCH": 502,
    "TOOL_CALL_LIMIT": 502,
    "TOOL_REPEAT_LIMIT": 502,
    "TOOL_ROUND_LIMIT": 502,
    "TOOL_EXECUTION_FAILED": 503,
    "TOOL_RESPONSE_INVALID": 502,
    "TOOL_DATA_TOO_LARGE": 502,
    "CONTEXT_TOO_LARGE": 502,
    "MODEL_RESPONSE_TOO_LARGE": 502,
    "INSUFFICIENT_EVIDENCE": 502,
    "MODEL_RESPONSE_INVALID": 502,
    "MODEL_RESPONSE_INCOMPLETE": 502,
    "UNEXPECTED_FUNCTION_CALL": 502,
    "FINAL_JSON_INVALID": 502,
    "RESPONSE_SCHEMA_INVALID": 502,
    "EVIDENCE_MISMATCH": 502,
    "AGENT_INTERNAL_ERROR": 500,
}


def analysis_error(code: str):
    safe_code = code if isinstance(code, str) and code in ERROR_STATUS else "AGENT_INTERNAL_ERROR"
    raise HTTPException(
        status_code=ERROR_STATUS[safe_code],
        detail=AnalysisError(error_code=safe_code).model_dump(),
    )


class AgentRuntime:
    """One lazy SDK client per application; analysis state remains request-local."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._client = None
        self._configuration = None
        self._close_timeout = 15

    async def service(self, tools: InspectionTools, settings: Settings) -> AgentService:
        if not settings.GEMINI_API_KEY:
            return AgentService(tools, settings=settings)
        configuration = (settings.GEMINI_API_KEY, settings.AGENT_MODEL_TIMEOUT_SECONDS)
        async with self._lock:
            if self._client is not None and self._configuration != configuration:
                analysis_error("AGENT_CONFIG_CHANGED")
            if self._client is None:
                try:
                    self._client = genai.Client(
                        api_key=settings.GEMINI_API_KEY,
                        http_options=types.HttpOptions(
                            timeout=int(settings.AGENT_MODEL_TIMEOUT_SECONDS * 1000),
                            retry_options=types.HttpRetryOptions(attempts=1),
                        ),
                    )
                except Exception:
                    analysis_error("INVALID_MODEL_CONFIG")
                self._configuration = configuration
                self._close_timeout = settings.AGENT_MODEL_TIMEOUT_SECONDS
        return AgentService(tools, settings=settings, client=self._client)

    async def aclose(self):
        client, self._client = self._client, None
        self._configuration = None
        if client is not None:
            try:
                await asyncio.wait_for(client.aio.aclose(), timeout=self._close_timeout)
            except Exception:
                pass
            finally:
                try:
                    client.close()
                except Exception:
                    pass


@dataclass
class AnalysisContext:
    inspection_id: str
    record: dict
    tools: InspectionTools


def get_validated_inspection_id(
    inspection_id: Annotated[str, Path(
        description="Existing server-managed inspection ID: INSP- followed by 6 to 12 digits.",
        examples=["INSP-000001"],
    )],
) -> str:
    if not _valid_id(inspection_id, INSPECTION_ID_PATTERN):
        analysis_error("INVALID_ARGUMENT")
    return inspection_id


def get_analysis_storage(inspection_id: str = Depends(get_validated_inspection_id)) -> InspectionStorageBase:
    try:
        return get_inspection_storage()
    except Exception:
        analysis_error("STORAGE_ERROR")


async def get_analysis_context(
    inspection_id: str = Depends(get_validated_inspection_id),
    storage: InspectionStorageBase = Depends(get_analysis_storage),
) -> AnalysisContext:
    tools = InspectionTools(storage)
    try:
        result = await run_in_threadpool(tools.get_inspection_result, inspection_id)
    except Exception:
        analysis_error("STORAGE_ERROR")
    if not result["ok"]:
        analysis_error(result["error"])
    return AnalysisContext(inspection_id=inspection_id, record=result["data"], tools=tools)


async def get_agent_service(
    request: Request,
    context: AnalysisContext = Depends(get_analysis_context),
    settings: Settings = Depends(get_settings),
) -> AgentService:
    runtime = getattr(request.app.state, "agent_runtime", None)
    if runtime is None:
        runtime = AgentRuntime()
        request.app.state.agent_runtime = runtime
    try:
        return await runtime.service(context.tools, settings)
    except HTTPException:
        raise
    except Exception:
        analysis_error("AGENT_INTERNAL_ERROR")


router = APIRouter(tags=["Agent analysis"])


@router.post(
    "/analyze/{inspection_id}", response_model=AnalysisResponse,
    summary="Analyze an existing inspection without changing its verdict",
    description=(
        "Read-only post-inspection diagnosis using stored results and logs. "
        "Requires an existing inspection, including FAILED inspections. Does not create an inspection, "
        "reload an image or run PatchCore. Gemini configuration is required only for analysis requests."
    ),
    responses={status: {"model": AnalysisErrorResponse, "description": description} for status, description in {
        404: "Inspection not found", 422: "Invalid inspection identifier",
        500: "Unexpected internal failure", 502: "Agent service or validated output failure",
        503: "Agent configuration, storage or tool unavailable", 504: "Analysis or dependency timeout",
    }.items()},
)
async def analyze_inspection(
    context: AnalysisContext = Depends(get_analysis_context),
    service: AgentService = Depends(get_agent_service),
) -> AnalysisResponse:
    try:
        raw = await service.analyze(context.inspection_id)
        result = DiagnosisResult.model_validate(raw.model_dump(mode="json") if isinstance(raw, DiagnosisResult) else raw)
    except ValidationError:
        analysis_error("RESPONSE_SCHEMA_INVALID")
    except TimeoutError:
        analysis_error("AGENT_TIMEOUT")
    except Exception:
        analysis_error("AGENT_INTERNAL_ERROR")
    if result.analysis_status != "COMPLETED":
        analysis_error(result.error_code)
    if result.error_code is not None or result.inspection_id != context.inspection_id:
        analysis_error("EVIDENCE_MISMATCH")
    snapshot_fields = (*CORE_FIELDS, "anomaly_score", "decision_threshold")
    if result.inspection_snapshot is None or any(
        result.inspection_snapshot.get(name) != context.record.get(name) for name in snapshot_fields
    ):
        analysis_error("EVIDENCE_MISMATCH")
    summary_code = {
        "OK": "NORMAL_MODEL_RESULT", "NG": "PRODUCT_ANOMALY", "REINSPECT": "REINSPECTION_REQUIRED", "ERROR": "INSPECTION_FAILED",
    }.get(context.record["final_result"], "INSUFFICIENT_DATA")
    if result.overall_summary != SUMMARY_TEXT[summary_code]:
        analysis_error("EVIDENCE_MISMATCH")
    response_data = result.model_dump()
    response_data["inspection_snapshot"] = {name: context.record.get(name) for name in snapshot_fields}
    analysis_resp = AnalysisResponse(
        **response_data, analysis_id=f"ANALYSIS-{uuid4().hex}",
        inspection_result=context.record["result"], final_result=context.record["final_result"],
        final_reason_code=context.record["final_reason_code"], timestamp=datetime.now(timezone.utc).isoformat(),
    )
    try:
        from pathlib import Path
        import json
        report_dir = Path("data/outputs/agent_reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        dumped = analysis_resp.model_dump()
        dumped["provenance"] = "LIVE_AGENT_ANALYSIS"
        with open(report_dir / f"{context.inspection_id}.json", "w", encoding="utf-8") as f:
            json.dump(dumped, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return analysis_resp
