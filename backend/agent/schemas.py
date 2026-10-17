"""Strict Agent protocol, grounded report and server-owned trace schemas."""

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

ToolName = Literal[
    "get_inspection_result", "get_execution_logs", "analyze_image_quality", "get_inspection_history",
]
SummaryCode = Literal[
    "NORMAL_MODEL_RESULT", "PRODUCT_ANOMALY", "REINSPECTION_REQUIRED", "INSPECTION_FAILED", "INSUFFICIENT_DATA",
]
CauseCode = Literal["ILLUMINATION_CHANGE", "EXPOSURE_SETTING", "IMAGE_ACQUISITION", "MODEL_AVAILABILITY"]
CheckCode = Literal[
    "LIGHTING_EXPOSURE_CHECK", "IMAGE_REGISTRATION_ACCESS_CHECK", "MODEL_SERVICE_CHECK",
    "MANUAL_REINSPECTION", "CONTINUE_MONITORING",
]
LimitationCode = Literal[
    "MODEL_NOT_GUARANTEE", "UNKNOWN_PHYSICAL_CAUSE", "MISSING_BRIGHTNESS_THRESHOLDS",
    "RECORDS_INCOMPLETE", "HISTORY_BOUNDED", "NO_PROBABILITY_CALIBRATION",
]
Scalar = Union[StrictBool, StrictInt, Annotated[StrictFloat, Field(allow_inf_nan=False)], StrictStr, None]
FactId = Annotated[str, Field(pattern=r"^F[0-9]{4}$")]
EvidenceId = Annotated[str, Field(pattern=r"^E[0-9]{4}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InspectionArguments(StrictModel):
    inspection_id: Annotated[StrictStr, Field(pattern=r"^INSP-[0-9]{6,12}$", max_length=17)]


class HistoryArguments(StrictModel):
    product_id: Annotated[StrictStr, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", max_length=64)]
    limit: Annotated[StrictInt, Field(ge=1, le=20)] = 5
    inspection_id: Optional[Annotated[StrictStr, Field(pattern=r"^INSP-[0-9]{6,12}$", max_length=17)]] = None


class AgentLimits(StrictModel):
    max_tool_rounds: int = Field(default=4, ge=1, le=10)
    max_tool_calls: int = Field(default=8, ge=1, le=30)
    max_repeat_calls: int = Field(default=2, ge=1, le=3)
    request_timeout_seconds: float = Field(default=60, gt=0, le=180)
    model_timeout_seconds: float = Field(default=15, gt=0, le=60)
    final_model_timeout_seconds: Annotated[StrictInt, Field(ge=1, le=30)] = 15
    tool_timeout_seconds: float = Field(default=3, gt=0, le=10)
    max_payload_bytes: int = Field(default=65536, ge=1024, le=262144)
    max_output_tokens: int = Field(default=4096, ge=256, le=8192)


class ObservedFact(StrictModel):
    fact_id: FactId
    evidence_id: EvidenceId
    source_tool: ToolName
    source_field: Annotated[str, Field(pattern=r"^/(?:data(?:/[A-Za-z0-9_]+)+|brightness_comparison/summary/[a-z_]+)$", max_length=120)]
    source_event: Optional[Annotated[str, Field(max_length=64)]] = None
    observed_value: Scalar


class CauseSelection(StrictModel):
    cause_code: CauseCode
    evidence_refs: List[FactId] = Field(min_length=1, max_length=10)


class CheckSelection(StrictModel):
    check_code: CheckCode
    evidence_refs: List[FactId] = Field(min_length=1, max_length=10)


class DiagnosisDraft(StrictModel):
    inspection_id: Annotated[str, Field(pattern=r"^INSP-[0-9]{6,12}$")]
    overall_summary: SummaryCode
    observed_facts: List[ObservedFact] = Field(min_length=1, max_length=40)
    possible_causes: List[CauseSelection] = Field(max_length=4)
    recommended_checks: List[CheckSelection] = Field(min_length=1, max_length=8)
    limitations: List[LimitationCode] = Field(max_length=6)


_RESPONSE_JSON_SCHEMA_FIELDS = frozenset({
    "$defs", "$ref", "type", "title", "description", "enum", "items", "minItems", "maxItems",
    "minimum", "maximum", "anyOf", "properties", "additionalProperties", "required",
})
_SERVER_ONLY_SCHEMA_FIELDS = frozenset({"pattern", "maxLength", "default"})


def _project_response_json_schema(schema: dict) -> dict:
    if set(schema) - _RESPONSE_JSON_SCHEMA_FIELDS - _SERVER_ONLY_SCHEMA_FIELDS:
        raise ValueError("UNSUPPORTED_DIAGNOSIS_SCHEMA")
    projected = {}
    for name, value in schema.items():
        if name in _SERVER_ONLY_SCHEMA_FIELDS:
            continue
        if name in {"$defs", "properties"}:
            projected[name] = {key: _project_response_json_schema(child) for key, child in value.items()}
        elif name == "items":
            projected[name] = _project_response_json_schema(value)
        elif name == "anyOf":
            projected[name] = [_project_response_json_schema(child) for child in value]
        else:
            projected[name] = value
    return projected


def diagnosis_response_json_schema() -> dict:
    """Project the strict server model into the reviewed Gemini JSON Schema subset."""
    return _project_response_json_schema(DiagnosisDraft.model_json_schema())


class ToolExecutionTrace(StrictModel):
    sequence: int
    round_number: int
    tool_name: Optional[ToolName]
    arguments: Dict[str, Any]
    executed: bool
    success: bool
    error_code: Optional[str]
    elapsed_ms: float
    evidence_id: Optional[EvidenceId] = None
    origin: Literal["GEMINI", "BACKEND_POLICY"] = "GEMINI"
    comparison_inspection_id: Optional[str] = None


class Hypothesis(CauseSelection):
    statement: str
    is_hypothesis: Literal[True] = True


class RecommendedCheck(CheckSelection):
    instruction: str


class TokenUsage(StrictModel):
    round_number: int
    prompt_token_count: Optional[int] = None
    candidates_token_count: Optional[int] = None
    total_token_count: Optional[int] = None


class DiagnosisResult(StrictModel):
    inspection_id: Optional[str]
    analysis_status: Literal["COMPLETED", "FAILED"]
    error_code: Optional[str] = None
    overall_summary: Optional[str] = None
    inspection_snapshot: Optional[Dict[str, Scalar]] = None
    observed_facts: List[ObservedFact] = Field(default_factory=list)
    possible_causes: List[Hypothesis] = Field(default_factory=list)
    recommended_checks: List[RecommendedCheck] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    tools_used: List[ToolName] = Field(default_factory=list)
    tool_execution_trace: List[ToolExecutionTrace] = Field(default_factory=list)
    model_name: Optional[str]
    token_usage: List[TokenUsage] = Field(default_factory=list)
    model_availability: Literal["NOT_TESTED"] = "NOT_TESTED"


class AnalysisResponse(DiagnosisResult):
    analysis_id: str = Field(pattern=r"^ANALYSIS-[0-9a-f]{32}$")
    inspection_result: Optional[Literal["OK", "NG", "UNKNOWN"]] = None
    final_result: Optional[Literal["OK", "NG", "REINSPECT", "ERROR"]] = None
    final_reason_code: Optional[str] = None
    timestamp: str


class AnalysisError(StrictModel):
    analysis_status: Literal["FAILED"] = "FAILED"
    error_code: str


class AnalysisErrorResponse(StrictModel):
    detail: AnalysisError
