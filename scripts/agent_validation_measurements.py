"""Safe measurement helpers shared by manual, explicitly approved experiments."""

from contextlib import contextmanager
from contextvars import ContextVar
import copy
import json
import math
from pathlib import Path
import re
import time


MODEL_REQUEST = ContextVar("manual_model_request", default=None)
WAIT_DEADLINE = ContextVar("manual_wait_deadline", default=None)
NOT_OBSERVABLE = "NOT OBSERVABLE"
NOT_TESTED = "NOT TESTED"


def error_policy_measurements(state, *, capabilities=None, phase="READY", draft=None,
                              validation_result=None, validation_failed=False):
    from backend.agent import error_policy
    from backend.agent.errors import AgentFailure
    from backend.agent.schemas import DiagnosisResult

    result = {"policy_enabled": (capabilities or {}).get("policy_enabled", NOT_OBSERVABLE),
        "policy_applicable": NOT_TESTED, "required_tools": NOT_OBSERVABLE,
        "required_event_codes": NOT_OBSERVABLE, "required_facts": NOT_OBSERVABLE,
        "required_fact_count": NOT_OBSERVABLE, "offline_required_evidence_valid": NOT_TESTED,
        "required_evidence_collected": NOT_TESTED, "report_validation_passed": NOT_TESTED,
        "unavailable_reason": None}
    if phase not in {"READY", "INVESTIGATION", "REPORT"}:
        result.update(policy_enabled=NOT_OBSERVABLE, unavailable_reason="INVALID_MEASUREMENT_PHASE")
        return result
    try:
        if state.snapshot is None:
            result["unavailable_reason"] = "NO_INSPECTION_SNAPSHOT"
            return result
        applicable = error_policy.error_report_scope(state)
        if type(applicable) is not bool:
            raise ValueError("UNOBSERVABLE_POLICY_SCOPE")
        result["policy_applicable"] = applicable
        if not applicable:
            result.update(required_tools=[], required_event_codes=[], required_facts=[], required_fact_count=0)
            return result
        try:
            required = error_policy.error_required_facts(state)
        except AgentFailure as failure:
            result["offline_required_evidence_valid"] = False
            result["unavailable_reason"] = failure.code if failure.code in {
                "INSUFFICIENT_EVIDENCE", "EVIDENCE_MISMATCH", "CONTEXT_TOO_LARGE"} else "POLICY_CHECK_FAILED"
            if phase != "READY":
                result["required_evidence_collected"] = False
            if phase == "REPORT" and validation_failed:
                result["report_validation_passed"] = False
            return result
        result.update(required_tools=sorted({entry.source_tool for entry in required}),
            required_event_codes=sorted({entry.source_event for entry in required if entry.source_event}),
            required_fact_count=len(required), offline_required_evidence_valid=True,
            required_facts=[{name: getattr(entry, name) for name in
                ("evidence_id", "source_tool", "source_field", "source_event")} for entry in required])
        if phase != "READY":
            result["required_evidence_collected"] = True
        if phase == "REPORT":
            if validation_failed:
                result["report_validation_passed"] = False
            elif isinstance(validation_result, DiagnosisResult) and draft is not None:
                result["report_validation_passed"] = (validation_result.analysis_status == "COMPLETED"
                    and error_policy.error_report_covered(draft, state))
        return result
    except Exception:
        result.update(policy_enabled=NOT_OBSERVABLE, policy_applicable=NOT_OBSERVABLE,
            required_evidence_collected=NOT_TESTED, report_validation_passed=NOT_TESTED,
            unavailable_reason="POLICY_NOT_OBSERVABLE")
        return result


async def probe_error_policy(service, state):
    """Exercise isolated server guards with local doubles, never analyze or an SDK client."""
    from backend.agent import error_policy
    from backend.agent.errors import AgentFailure
    from backend.agent.reporting import CORE_FIELDS
    from backend.agent.schemas import DiagnosisDraft, ObservedFact
    from google.genai import types

    checks = {"investigation_guard": NOT_OBSERVABLE, "report_coverage_guard": NOT_OBSERVABLE,
        "complete_probe_accepted": NOT_OBSERVABLE, "skipped_model_claims_rejected": NOT_TESTED,
        "policy_enabled": NOT_OBSERVABLE, "unavailable_reason": None}
    try:
        if not error_policy.error_report_scope(state):
            checks["unavailable_reason"] = "POLICY_NOT_APPLICABLE"
            return checks
        required = error_policy.error_required_facts(state)
        facts = [ObservedFact(fact_id=f"F{index:04d}", **{name: getattr(entry, name) for name in
            ("evidence_id", "source_tool", "source_field", "observed_value", "source_event")})
            for index, entry in enumerate(required, 1)]
        final = next(fact.fact_id for fact in facts if fact.source_tool == "get_inspection_result"
            and fact.source_field == "/data/final_result")
        draft = DiagnosisDraft(inspection_id=state.inspection_id, overall_summary="INSPECTION_FAILED",
            observed_facts=facts, possible_causes=[], recommended_checks=[{
                "check_code": "MANUAL_REINSPECTION", "evidence_refs": [final]}], limitations=[])
        model = service.settings.GEMINI_MODEL
        accepted = service._verify_report(draft, copy.deepcopy(state), model)
        checks["complete_probe_accepted"] = accepted.analysis_status == "COMPLETED"
        omitted = next(fact for fact in facts if fact.source_tool != "get_inspection_result"
            or fact.source_field not in {f"/data/{name}" for name in CORE_FIELDS})
        incomplete = draft.model_copy(deep=True)
        incomplete.observed_facts = [fact for fact in incomplete.observed_facts if fact.fact_id != omitted.fact_id]
        checks["report_coverage_guard"] = _probe_report_rejected(service, incomplete, state, model)
        missing = copy.deepcopy(state)
        missing.evidence = {identifier: value for identifier, value in missing.evidence.items() if value[0] != "get_execution_logs"}
        missing.trace = [entry for entry in missing.trace if entry.tool_name != "get_execution_logs"]
        isolated = copy.copy(service)
        final_requested = False

        async def local_generate(client, model, contents, state, round_number, structured=False):
            nonlocal final_requested
            if structured:
                final_requested = True
                raise RuntimeError("OFFLINE_FINAL_BLOCKED")
            return types.Content(role="model", parts=[types.Part.from_text(text="Offline guard probe")])

        isolated._generate = local_generate
        try:
            await isolated._run(None, model, missing)
        except AgentFailure as failure:
            checks["investigation_guard"] = not final_requested and failure.code in {"INSUFFICIENT_EVIDENCE", "EVIDENCE_MISMATCH"}
        except Exception:
            checks["investigation_guard"] = False if final_requested else NOT_OBSERVABLE
        skipped = next((fact.fact_id for fact in facts if fact.source_field == "/data/defect_detection_status"
            and fact.observed_value == "SKIPPED"), None)
        if skipped:
            rejections = []
            for field, selection in (("possible_causes", {"cause_code": "MODEL_AVAILABILITY", "evidence_refs": [skipped]}),
                ("recommended_checks", {"check_code": "MODEL_SERVICE_CHECK", "evidence_refs": [skipped]})):
                values = draft.model_dump()
                values[field] = [selection]
                rejections.append(_probe_report_rejected(service, DiagnosisDraft.model_validate(values), state, model))
            checks["skipped_model_claims_rejected"] = all(value is True for value in rejections)
        observed = [checks[name] for name in ("investigation_guard", "report_coverage_guard", "complete_probe_accepted")]
        if skipped:
            observed.append(checks["skipped_model_claims_rejected"])
        checks["policy_enabled"] = False if False in observed else True if all(value is True for value in observed) else NOT_OBSERVABLE
        if checks["policy_enabled"] is not True:
            checks["unavailable_reason"] = "SERVER_POLICY_GUARD_NOT_ENFORCED" if checks["policy_enabled"] is False else "POLICY_PROBE_UNAVAILABLE"
    except Exception:
        checks["policy_enabled"] = NOT_OBSERVABLE
        checks["unavailable_reason"] = "POLICY_PROBE_UNAVAILABLE"
    return checks


def _probe_report_rejected(service, draft, state, model):
    from backend.agent.errors import AgentFailure

    try:
        service._verify_report(draft, copy.deepcopy(state), model)
    except AgentFailure as failure:
        return failure.code == "EVIDENCE_MISMATCH"
    except Exception:
        return NOT_OBSERVABLE
    return False


def _finite(value):
    return value if type(value) in (int, float) and math.isfinite(value) else NOT_OBSERVABLE


@contextmanager
def model_request_context(service, state):
    token = MODEL_REQUEST.set((service, state))
    try:
        yield
    finally:
        MODEL_REQUEST.reset(token)


@contextmanager
def wait_deadline_context(timeout):
    started = time.monotonic()
    seconds = _finite(timeout)
    token = WAIT_DEADLINE.set({
        "local_wait_timeout_seconds": seconds,
        "request_deadline_monotonic": started + seconds if seconds != NOT_OBSERVABLE else NOT_OBSERVABLE,
        "deadline_source": "DERIVED_FROM_PUBLIC_WAIT_FOR_ENTRY",
    })
    try:
        yield
    finally:
        WAIT_DEADLINE.reset(token)


def sdk_timeout_measurements(config):
    options = getattr(config, "http_options", None)
    retry = getattr(options, "retry_options", None)
    result = {"sdk_timeout_ms": _finite(getattr(options, "timeout", None)),
        "sdk_retry_attempts": _finite(getattr(retry, "attempts", None))}
    result.update(request_budget_measurements())
    return result


def request_budget_measurements():
    result = {}
    context = MODEL_REQUEST.get()
    if context is not None:
        service, state = context
        deadline = _finite(state.deadline)
        result.update(agent_limit_seconds=_finite(service.limits.request_timeout_seconds),
            agent_deadline_monotonic=deadline,
            remaining_agent_budget_seconds=max(0, deadline - time.monotonic()) if deadline != NOT_OBSERVABLE else NOT_OBSERVABLE)
    else:
        result.update(agent_limit_seconds=NOT_OBSERVABLE, agent_deadline_monotonic=NOT_OBSERVABLE,
            remaining_agent_budget_seconds=NOT_OBSERVABLE)
    result.update(WAIT_DEADLINE.get() or {"local_wait_timeout_seconds": NOT_OBSERVABLE,
        "request_deadline_monotonic": NOT_OBSERVABLE, "deadline_source": NOT_OBSERVABLE})
    result["transport_absolute_deadline"] = NOT_OBSERVABLE
    result["server_absolute_deadline"] = NOT_OBSERVABLE
    return result


def transport_timeout_measurements(request, sdk_timeout_ms):
    configured = request.extensions.get("timeout")
    phases = {name: _finite(configured[name]) if configured[name] is not None else None
        for name in ("connect", "read", "write", "pool") if name in configured} if isinstance(configured, dict) else {}
    raw = request.headers.get("X-Server-Timeout", "")
    server = _finite(float(raw)) if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw) and len(raw) <= 24 else NOT_OBSERVABLE
    if server != NOT_OBSERVABLE and not 0 <= server <= 3600:
        server = NOT_OBSERVABLE
    seconds = sdk_timeout_ms / 1000 if _finite(sdk_timeout_ms) != NOT_OBSERVABLE else None
    return {"transport_timeout_seconds": phases or NOT_OBSERVABLE,
        "transport_timeout_source": "HTTPX_REQUEST_EXTENSIONS" if phases else NOT_OBSERVABLE,
        "server_timeout_seconds": server,
        "server_timeout_conflict": server != math.ceil(seconds) if seconds is not None and server != NOT_OBSERVABLE else NOT_OBSERVABLE,
        "transport_timeout_conflict": any(value != seconds for value in phases.values()) if phases and seconds is not None else NOT_OBSERVABLE}


def attempt_paths(directory, attempt_id):
    if not isinstance(attempt_id, str) or not re.fullmatch(r"[a-z0-9_]{1,64}", attempt_id):
        raise ValueError("INVALID_ATTEMPT_ID")
    root = Path(directory)
    return {"ready": root / (attempt_id + "_ready.json"),
        "lock": root / (attempt_id + "_analysis_started.lock"),
        "result": root / (attempt_id + "_sanitized_result.json")}


def t06_final_timeout(attempt_id):
    if not isinstance(attempt_id, str) or re.fullmatch(
        r"t06_operational_[a-z0-9]+(?:_[a-z0-9]+)*_[1-9][0-9]*", attempt_id
    ) is None:
        raise ValueError("INVALID_ATTEMPT_SETTINGS")
    return 30 if attempt_id == "t06_operational_groundtruth_isolated_final30_1" else 15


_UNSET_FINAL_TIMEOUT = object()


def ready_manifest(directory, attempt_id, inspection_id, *, scenario="T03", final_timeout=_UNSET_FINAL_TIMEOUT):
    if final_timeout is _UNSET_FINAL_TIMEOUT:
        if scenario == "T06":
            raise ValueError("INVALID_ATTEMPT_SETTINGS")
        final_timeout = 30
    if not isinstance(inspection_id, str) or not re.fullmatch(r"INSP-[0-9]{6,12}", inspection_id):
        raise ValueError("INVALID_INSPECTION_ID")
    if scenario not in {"T03", "T05", "T06"} or type(final_timeout) is not int or final_timeout not in {15, 30}:
        raise ValueError("INVALID_ATTEMPT_SETTINGS")
    paths = attempt_paths(directory, attempt_id)
    if scenario == "T06":
        if inspection_id != "INSP-001406" or final_timeout != t06_final_timeout(attempt_id):
            raise ValueError("INVALID_ATTEMPT_SETTINGS")
    elif inspection_id == "INSP-001406" or attempt_id.startswith("t06_"):
        raise ValueError("INVALID_ATTEMPT_SETTINGS")
    return {"schema_version": 1, "attempt_id": attempt_id, "state": "READY", "scenario": scenario,
        "inspection_id": inspection_id, "analysis_attempts": 0, "gemini_http_requests": 0,
        "approval_required": True, "model": "gemini-3.8-flash", "sdk": "2.31.0", "api_version": "v1beta",
        "timeouts_seconds": {"investigation": 15, "final_ceiling": final_timeout, "overall": 60, "reserve": 2},
        "lock_file": paths["lock"].name, "result_file": paths["result"].name}


def plan_attempt(directory, attempt_id, inspection_id, **settings):
    if any(path.exists() for path in attempt_paths(directory, attempt_id).values()):
        raise ValueError("ATTEMPT_COLLISION")
    return ready_manifest(directory, attempt_id, inspection_id, **settings)


def prepare_attempt(directory, attempt_id, inspection_id, **settings):
    manifest = plan_attempt(directory, attempt_id, inspection_id, **settings)
    with attempt_paths(directory, attempt_id)["ready"].open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    return manifest


def validate_ready_attempt(directory, attempt_id, inspection_id, **settings):
    paths = attempt_paths(directory, attempt_id)
    if paths["lock"].exists() or paths["result"].exists():
        raise ValueError("ATTEMPT_ALREADY_USED")
    if json.loads(paths["ready"].read_text(encoding="utf-8")) != ready_manifest(directory, attempt_id, inspection_id, **settings):
        raise ValueError("INVALID_READY_MANIFEST")


def validate_process_timeout(configured_timeout, process_timeout=None):
    if type(configured_timeout) is not int or configured_timeout not in {15, 30}:
        raise ValueError("INVALID_ATTEMPT_TIMEOUT")
    if process_timeout is None:
        selected = 15
    elif type(process_timeout) is str and process_timeout in {"15", "30"}:
        selected = int(process_timeout)
    else:
        raise ValueError("INVALID_PROCESS_TIMEOUT")
    if selected != configured_timeout:
        raise ValueError("PROCESS_SETTINGS_TIMEOUT_MISMATCH")
    return selected


def validate_attempt_timeout(directory, attempt_id, inspection_id, *, configured_timeout, process_timeout=None,
                             scenario="T05"):
    selected = validate_process_timeout(configured_timeout, process_timeout)
    paths = attempt_paths(directory, attempt_id)
    if paths["lock"].exists() or paths["result"].exists():
        raise ValueError("ATTEMPT_ALREADY_USED")
    if not paths["ready"].is_file():
        raise ValueError("READY_CONFIGURATION_MISSING")
    try:
        manifest = json.loads(paths["ready"].read_text(encoding="utf-8"))
        prepared = manifest["timeouts_seconds"]["final_ceiling"]
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("INVALID_READY_MANIFEST") from None
    if type(prepared) is not int or prepared not in {15, 30}:
        raise ValueError("INVALID_ATTEMPT_TIMEOUT")
    approved = t06_final_timeout(attempt_id) if scenario == "T06" else prepared
    try:
        validate_ready_attempt(directory, attempt_id, inspection_id, scenario=scenario, final_timeout=approved)
    except OSError:
        raise ValueError("INVALID_READY_MANIFEST") from None
    if prepared != selected:
        raise ValueError("ATTEMPT_PROCESS_TIMEOUT_MISMATCH")
    return manifest


def record_investigation_stop(report, service, state, original, normal_ready):
    ready = original(service, state)
    policy = "CONTINUE"
    if ready is True:
        try:
            from backend.agent.error_policy import image_load_failure_evidence_ready
            from backend.agent.investigation import warning_evidence_ready

            if normal_ready(state):
                policy = "NORMAL"
            elif warning_evidence_ready(state, required_event_codes=service.required_warning_event_codes):
                policy = "WARNING"
            elif not service.required_warning_event_codes and image_load_failure_evidence_ready(state):
                policy = "IMAGE_LOAD_FAILURE"
            else:
                policy = "UNKNOWN"
        except Exception:
            policy = "UNKNOWN"
    report.setdefault("early_exit_checks", []).append({
        "ready": ready,
        "policy": policy,
        "trace_round": max((entry.round_number for entry in state.trace), default=0),
        "executed_tools": sum(entry.executed for entry in state.trace),
        "evidence_ids": [entry.evidence_id for entry in state.trace if entry.executed and entry.success],
        "required_event_codes": list(service.required_warning_event_codes),
    })
    return ready


def summarize_measurements(report):
    requests = report.get("sdk_requests", [])
    transmissions = report.get("http_transmissions", [])
    trace = report.get("tool_execution_trace", [])
    report["actual_http_requests"] = len(transmissions)
    report["sdk_request_count"] = len(requests)
    report["python_tool_invocations"] = len(report.get("python_tools", []))
    report["agent_tool_executions"] = sum(entry["executed"] for entry in trace)
    report["trace_rounds"] = sorted({entry["round_number"] for entry in trace})
    report["known_tokens"] = {}
    for name in ("prompt_token_count", "candidates_token_count", "thoughts_token_count", "total_token_count"):
        known = [entry["tokens"][name] for entry in requests if entry.get("tokens", {}).get(name) is not None]
        report["known_tokens"][name] = sum(known) if known else None
    report["usage_complete"] = bool(requests) and all(
        entry.get("tokens", {}).get("total_token_count") is not None for entry in requests)
    failed = next((entry for entry in requests if not entry["success"]), None)
    if failed:
        report["failure_stage"] = failed["stage"]
        report["failed_sdk_request"] = failed["sequence"]
    if "returned_verdict" in report:
        report["verdict_unchanged"] = report["returned_verdict"] == report.get("stored_verdict")
    else:
        report["verdict_unchanged"] = None
    report["stored_data_unchanged"] = report.get("protected_files_unchanged")
    propagated = []
    for entry in transmissions:
        if entry.get("server_timeout_conflict") is True or entry.get("transport_timeout_conflict") is True:
            propagated.append(False)
        elif entry.get("server_timeout_conflict") is False and entry.get("transport_timeout_conflict") is False:
            sdk = _finite(entry.get("sdk_timeout_ms"))
            local = _finite(entry.get("local_wait_timeout_seconds"))
            propagated.append(local == sdk / 1000 if sdk != NOT_OBSERVABLE and local != NOT_OBSERVABLE else None)
        else:
            propagated.append(None)
    report["timeout_propagation_valid"] = False if False in propagated else None if not propagated or None in propagated else True
