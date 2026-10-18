"""Allowlisted error metadata for explicitly approved manual SDK experiments."""

import re

from google.genai import errors

from backend.agent.schemas import DiagnosisDraft


_STATUS_CODES = frozenset({
    "OK", "CANCELLED", "UNKNOWN", "INVALID_ARGUMENT", "DEADLINE_EXCEEDED", "NOT_FOUND",
    "ALREADY_EXISTS", "PERMISSION_DENIED", "RESOURCE_EXHAUSTED", "FAILED_PRECONDITION",
    "ABORTED", "OUT_OF_RANGE", "UNIMPLEMENTED", "INTERNAL", "UNAVAILABLE", "DATA_LOSS", "UNAUTHENTICATED",
})
_REASONS = frozenset({
    "API_KEY_INVALID", "API_KEY_EXPIRED", "API_KEY_SERVICE_BLOCKED", "ACCESS_TOKEN_EXPIRED",
    "SERVICE_DISABLED", "CONSUMER_INVALID", "QUOTA_EXCEEDED", "RATE_LIMIT_EXCEEDED",
    "INVALID_ARGUMENT", "SCHEMA_VALIDATION_FAILED", "INVALID_SCHEMA", "UNSUPPORTED_SCHEMA",
    "UNSUPPORTED_FIELD", "FIELD_VALUE_INVALID", "INVALID_VALUE", "INVALID_TYPE",
    "UNSUPPORTED_VALUE", "INVALID_JSON_PAYLOAD",
})
_PATH_NAMES = frozenset({
    "generation_config", "generationConfig", "response_schema", "responseSchema",
    "response_json_schema", "responseJsonSchema", "response_mime_type", "responseMimeType",
    "responseFormat", "response_format", "system_instruction", "systemInstruction",
    "contents", "parts", "text", "role", "tools", "tool_config", "toolConfig",
    "function_calling_config", "functionCallingConfig", "mode", "model",
    "temperature", "candidate_count", "candidateCount", "max_output_tokens", "maxOutputTokens",
    "thinking_config", "thinkingConfig", "thinking_budget", "thinkingBudget", "thinking_level", "thinkingLevel",
    "$defs", "$ref", "anyOf", "oneOf", "properties", "items", "type", "enum", "required",
    "additionalProperties", "minItems", "maxItems", "minimum", "maximum", "title", "description",
    "key", "value", "summary", "status",
    *DiagnosisDraft.model_fields,
    *DiagnosisDraft.model_json_schema()["$defs"],
    *(name for definition in DiagnosisDraft.model_json_schema()["$defs"].values()
      for name in definition["properties"]),
})
_PATH_ROOTS = frozenset({
    "generation_config", "generationConfig", "system_instruction", "systemInstruction",
    "contents", "tools", "tool_config", "toolConfig", "model",
})
_PATH_SEGMENT = re.compile(r'([A-Za-z_$][A-Za-z0-9_$]*)(?:\[([0-9]{1,4}|"[A-Za-z_$][A-Za-z0-9_$]*")\])?')


def provider_error_code(value):
    return value if isinstance(value, str) and value in _STATUS_CODES else None


def _safe_field_path(value):
    if not isinstance(value, str) or len(value) > 240:
        return "UNKNOWN"
    segments = value.split(".")
    for index, segment in enumerate(segments):
        match = _PATH_SEGMENT.fullmatch(segment)
        if match is None or match[1] not in _PATH_NAMES or index == 0 and match[1] not in _PATH_ROOTS:
            return "UNKNOWN"
        if match[2] and match[2].startswith('"') and match[2][1:-1] not in _PATH_NAMES:
            return "UNKNOWN"
    return value


def safe_gemini_error(failure: Exception, stage: str) -> dict:
    """Exclude messages, descriptions, headers, payloads and arbitrary exception names."""
    result = {
        "http_status": None, "google_api_code": "UNKNOWN", "reason": "UNKNOWN",
        "field_violations": [],
        "request_stage": stage if stage in {"FUNCTION_CALLING", "STRUCTURED_OUTPUT"} else "UNKNOWN",
        "sdk_exception_type": "UNKNOWN",
    }
    if not isinstance(failure, errors.APIError):
        return result
    result["sdk_exception_type"] = next((name for exception, name in (
        (errors.ClientError, "ClientError"), (errors.ServerError, "ServerError"),
    ) if isinstance(failure, exception)), "APIError")
    if type(failure.code) is int and 100 <= failure.code <= 599:
        result["http_status"] = failure.code
    if isinstance(failure.status, str) and failure.status in _STATUS_CODES:
        result["google_api_code"] = failure.status
    payload = failure.details if isinstance(failure.details, dict) else {}
    error = payload.get("error", payload)
    details = error.get("details", []) if isinstance(error, dict) else []
    for detail in details[:16] if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        if detail.get("@type") == "type.googleapis.com/google.rpc.ErrorInfo":
            reason = detail.get("reason")
            if isinstance(reason, str) and reason in _REASONS and result["reason"] == "UNKNOWN":
                result["reason"] = reason
        elif detail.get("@type") == "type.googleapis.com/google.rpc.BadRequest":
            violations = detail.get("fieldViolations", [])
            for violation in violations[:10] if isinstance(violations, list) else []:
                if not isinstance(violation, dict) or len(result["field_violations"]) >= 10:
                    continue
                reason = violation.get("reason")
                safe_reason = reason if isinstance(reason, str) and reason in _REASONS else "UNKNOWN"
                result["field_violations"].append({"field": _safe_field_path(violation.get("field")), "reason": safe_reason})
    return result
