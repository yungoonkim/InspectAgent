"""Local preflight policy and nonblocking, process-shared analysis admission."""

from contextlib import contextmanager
import errno
import hashlib
from importlib.metadata import version
import os
from pathlib import Path
import tempfile

from backend.agent.errors import AgentFailure


API_VERSION = "v1beta"
SDK_ATTEMPTS = 1
PROVIDER_REQUEST_LIMIT = 6
SAFETY_REVISION = "day7-step6b-v1"
EXPECTED = {
    "model": "gemini-3.8-flash", "sdk_version": "2.31.0", "api_version": "v1beta",
    "sdk_attempts": 1, "automatic_retries": 0,
    "tool_round_limit": 4, "tool_call_limit": 8, "repeat_call_limit": 2,
    "provider_request_limit": 6, "request_timeout_seconds": 60,
    "model_timeout_seconds": 15, "final_model_timeout_seconds": 15,
    "tool_timeout_seconds": 3, "max_payload_bytes": 65536, "max_output_tokens": 4096,
}


def effective_configuration(settings, limits):
    return {
        "model": settings.GEMINI_MODEL, "sdk_version": version("google-genai"),
        "api_version": API_VERSION, "sdk_attempts": SDK_ATTEMPTS,
        "automatic_retries": SDK_ATTEMPTS - 1,
        "tool_round_limit": limits.max_tool_rounds, "tool_call_limit": limits.max_tool_calls,
        "repeat_call_limit": limits.max_repeat_calls, "provider_request_limit": PROVIDER_REQUEST_LIMIT,
        "request_timeout_seconds": limits.request_timeout_seconds,
        "model_timeout_seconds": limits.model_timeout_seconds,
        "final_model_timeout_seconds": limits.final_model_timeout_seconds,
        "tool_timeout_seconds": limits.tool_timeout_seconds,
        "max_payload_bytes": limits.max_payload_bytes, "max_output_tokens": limits.max_output_tokens,
    }


def verify_configuration(settings, limits):
    configuration = effective_configuration(settings, limits)
    if configuration != EXPECTED:
        raise AgentFailure("AGENT_RUNTIME_CONFIG_MISMATCH")
    return configuration


class AnalysisAdmission:
    """One OS lock per checkout and local temp namespace, including other workers."""

    def __init__(self, path=None):
        checkout = str(Path(__file__).resolve().parents[2]).casefold()
        namespace = hashlib.sha256(checkout.encode()).hexdigest()[:24]
        self.path = Path(path) if path else Path(tempfile.gettempdir()) / f"visioninsight-agent-{namespace}.lock"

    @contextmanager
    def acquire(self):
        try:
            handle = self.path.open("a+b")
        except OSError:
            raise AgentFailure("AGENT_ADMISSION_UNAVAILABLE") from None
        acquired = False
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as failure:
                    code = "AGENT_BUSY" if failure.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK) else "AGENT_ADMISSION_UNAVAILABLE"
                    raise AgentFailure(code) from None
            else:
                import fcntl

                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as failure:
                    code = "AGENT_BUSY" if failure.errno in (errno.EACCES, errno.EAGAIN) else "AGENT_ADMISSION_UNAVAILABLE"
                    raise AgentFailure(code) from None
            acquired = True
            yield
        finally:
            try:
                if acquired:
                    if os.name == "nt":
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
