"""VisionInsight — Day 7 Step 1-B: Gemini API Single Call Smoke Test.

Executes exactly ONE live Google Gemini API call when explicitly authorized.
Default execution is DRY RUN (0 network requests).

Safety guarantees:
1. Default mode is DRY RUN (0 API requests).
2. Live call requires explicit --execute-once flag AND exact user confirmation phrase:
   'RUN ONE GEMINI REQUEST'.
3. Max call count is strictly bounded to 1 (enforced by internal assertion and counter).
4. Automatic retries disabled: HttpRetryOptions(attempts=1).
5. Automatic function calling disabled: AutomaticFunctionCallingConfig(disable=True).
6. Automatic continuation disabled: automatic_continuation=False.
7. No auxiliary Google API calls (no models.list, no token count).
8. Uses neutral prompt 'Reply exactly OK', never inspection data or evidence.
9. Credentials, auth tokens, headers are never logged or echoed.
10. Execution terminates immediately after the single call.
"""

import argparse
import asyncio
from dataclasses import dataclass
import logging
import math
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, Optional

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google import genai
from google.genai import types

from backend.config import get_settings

REQUIRED_CONFIRMATION = "RUN ONE GEMINI REQUEST"
TEST_PROMPT = "Reply exactly OK"
MAX_TOKENS = 16


def _extract_status_code(exc: Exception) -> Optional[int]:
    """Extract integer HTTP status code from exception or response object."""
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    if response is not None:
        resp_code = getattr(response, "status_code", None)
        if isinstance(resp_code, int):
            return resp_code
    return None


def _extract_provider_error_code(exc: Exception) -> Optional[str]:
    """Extract safe provider status identifier (e.g. NOT_FOUND, PERMISSION_DENIED)."""
    raw_status = getattr(exc, "status", None) or getattr(exc, "reason", None)
    if isinstance(raw_status, str) and re.fullmatch(r"^[A-Za-z0-9_]{1,64}$", raw_status):
        return raw_status.upper()
    return None


def _sanitize_error_message(message: str) -> str:
    """Mask credentials, auth tokens, or query keys in error text."""
    if not message:
        return ""
    sanitized = re.sub(
        r"(?:AIza[0-9A-Za-z-_]{35}|key=[^&\s]+|Bearer\s+[^\s]+)",
        "[REDACTED]",
        message,
    )
    return sanitized[:300]


@dataclass
class SingleCallResult:
    status: str  # "SUCCESS", "FAILED", "DRY_RUN", "ABORTED"
    network_calls_attempted: int
    elapsed_ms: float
    model_name: str
    response_text: Optional[str] = None
    finish_reason: Optional[str] = None
    exception_class: Optional[str] = None
    http_status: Optional[int] = None
    provider_code: Optional[str] = None
    safe_message: Optional[str] = None
    stage: str = "INIT"


class SingleCallExecutor:
    """Strict execution controller ensuring at most 1 API request ever runs."""

    def __init__(self, client: Optional[Any] = None, settings: Optional[Any] = None):
        self.settings = settings or get_settings()
        self.client = client
        self.call_count = 0
        self.model_name = self.settings.GEMINI_MODEL

    async def execute_dry_run(self) -> SingleCallResult:
        """Perform local configuration validation with 0 network calls."""
        key_present = bool(self.settings.GEMINI_API_KEY)
        key_len = len(self.settings.GEMINI_API_KEY) if self.settings.GEMINI_API_KEY else 0
        print("=" * 70)
        print("VisionInsight — Day 7 Step 1-B: Gemini API Single Call Smoke Test")
        print("Mode: DRY RUN (0 network requests)")
        print("=" * 70)
        print(f"[CONFIG] Model Name:          {self.model_name}")
        print(f"[CONFIG] API Version:         v1beta")
        print(f"[CONFIG] API Key Present:     {key_present} (length: {key_len})")
        print(f"[CONFIG] Max Output Tokens:   {MAX_TOKENS}")
        print(f"[CONFIG] HTTP Retries:        Disabled (attempts=1)")
        print(f"[CONFIG] Function Calling:    Disabled")
        print(f"[CONFIG] Continuation:        Disabled")
        print(f"[CONFIG] Neutral Prompt:      '{TEST_PROMPT}'")
        print(f"[CONFIG] Total Requests:      0 (DRY RUN)")
        print("=" * 70)
        print("[NOTICE] DRY RUN complete. Zero network requests were made.")
        print(f"To execute exactly ONE live request, re-run with:")
        print(f"  --execute-once")
        print(f"and confirm with '{REQUIRED_CONFIRMATION}'.")
        print("=" * 70)
        return SingleCallResult(
            status="DRY_RUN",
            network_calls_attempted=0,
            elapsed_ms=0.0,
            model_name=self.model_name,
            stage="DRY_RUN_VALIDATION",
        )

    async def execute_live_single_call(self) -> SingleCallResult:
        """Execute strictly ONE Google Gemini generate_content call."""
        if self.call_count >= 1:
            raise RuntimeError("CRITICAL: SingleCallExecutor already executed 1 call. Further calls forbidden.")

        if not self.settings.GEMINI_API_KEY:
            return SingleCallResult(
                status="FAILED",
                network_calls_attempted=0,
                elapsed_ms=0.0,
                model_name=self.model_name,
                exception_class="MissingApiKeyError",
                safe_message="GEMINI_API_KEY is not set in environment or .env",
                stage="PRE_FLIGHT_CHECK",
            )

        timeout_seconds = getattr(self.settings, "AGENT_MODEL_TIMEOUT_SECONDS", 15.0)
        owned_client = False
        client = self.client

        if client is None:
            client = genai.Client(
                api_key=self.settings.GEMINI_API_KEY,
                http_options=types.HttpOptions(
                    api_version="v1beta",
                    timeout=int(timeout_seconds * 1000),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            owned_client = True

        config = types.GenerateContentConfig(
            temperature=0,
            candidate_count=1,
            max_output_tokens=MAX_TOKENS,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            automatic_continuation=False,
            http_options=types.HttpOptions(
                api_version="v1beta",
                timeout=int(timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

        started_at = time.perf_counter()
        self.call_count += 1  # Strictly 1st and only call
        stage = "GENERATE_CONTENT"

        try:
            print(f"[EXECUTING] Sending single request to model='{self.model_name}'...")
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=self.model_name,
                    contents=TEST_PROMPT,
                    config=config,
                ),
                timeout=timeout_seconds,
            )
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            finish = None
            text = None
            if response.candidates:
                candidate = response.candidates[0]
                finish = getattr(candidate.finish_reason, "name", str(candidate.finish_reason))
                if candidate.content and candidate.content.parts:
                    text = "".join(part.text for part in candidate.content.parts if getattr(part, "text", None))

            return SingleCallResult(
                status="SUCCESS",
                network_calls_attempted=1,
                elapsed_ms=elapsed_ms,
                model_name=self.model_name,
                response_text=text,
                finish_reason=finish,
                stage=stage,
            )

        except TimeoutError:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            return SingleCallResult(
                status="FAILED",
                network_calls_attempted=1,
                elapsed_ms=elapsed_ms,
                model_name=self.model_name,
                exception_class="TimeoutError",
                http_status=504,
                provider_code="TIMEOUT",
                safe_message=f"Request timed out after {timeout_seconds}s",
                stage=stage,
            )

        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            return SingleCallResult(
                status="FAILED",
                network_calls_attempted=1,
                elapsed_ms=elapsed_ms,
                model_name=self.model_name,
                exception_class=exc.__class__.__name__,
                http_status=_extract_status_code(exc),
                provider_code=_extract_provider_error_code(exc),
                safe_message=_sanitize_error_message(str(exc)),
                stage=stage,
            )

        finally:
            if owned_client:
                try:
                    await asyncio.wait_for(client.aio.aclose(), timeout=5.0)
                except Exception:
                    pass
                try:
                    client.close()
                except Exception:
                    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VisionInsight Day 7: Gemini Single Live Request Smoke Test",
    )
    parser.add_argument(
        "--execute-once",
        action="store_true",
        default=False,
        help="Explicit flag allowing exactly ONE live Gemini API call. Without this, performs DRY RUN.",
    )
    parser.add_argument(
        "--confirm-phrase",
        type=str,
        default=None,
        help="Optional confirmation phrase matching 'RUN ONE GEMINI REQUEST' for automation/testing.",
    )
    return parser.parse_args()


def prompt_user_confirmation() -> bool:
    print("\n" + "#" * 70)
    print("! ATTENTION: YOU ARE ABOUT TO EXECUTE EXACTLY ONE LIVE GOOGLE GEMINI API CALL !")
    print(f"To confirm, type exactly: '{REQUIRED_CONFIRMATION}'")
    print("#" * 70)
    try:
        entered = input("Confirmation >> ").strip()
        return entered == REQUIRED_CONFIRMATION
    except (EOFError, KeyboardInterrupt):
        print("\n[ABORTED] Interrupted by user.")
        return False


async def async_main(args: argparse.Namespace) -> int:
    executor = SingleCallExecutor()

    # Case 1: DRY RUN (no --execute-once)
    if not args.execute_once:
        result = await executor.execute_dry_run()
        return 0

    # Case 2: User confirmation check
    if args.confirm_phrase is not None:
        confirmed = (args.confirm_phrase.strip() == REQUIRED_CONFIRMATION)
    else:
        confirmed = prompt_user_confirmation()

    if not confirmed:
        print("\n" + "=" * 70)
        print("[ABORTED] Confirmation phrase did not match. Network requests executed: 0.")
        print("=" * 70)
        return 1

    # Case 3: Live single call execution
    print("\n" + "=" * 70)
    print("Executing ONE live request under strict guardrails...")
    print("=" * 70)
    result = await executor.execute_live_single_call()

    print("\n" + "=" * 70)
    print(f"[STATUS]             {result.status}")
    print(f"[TOTAL_CALLS_MADE]   {result.network_calls_attempted}")
    print(f"[MODEL]              {result.model_name}")
    print(f"[STAGE]              {result.stage}")
    print(f"[ELAPSED_MS]         {result.elapsed_ms} ms")

    if result.status == "SUCCESS":
        print(f"[RESPONSE_TEXT]      {result.response_text}")
        print(f"[FINISH_REASON]      {result.finish_reason}")
        print("=" * 70)
        print("[RESULT] Live Gemini API connectivity verified successfully!")
        return 0
    else:
        print(f"[EXCEPTION_CLASS]    {result.exception_class}")
        print(f"[HTTP_STATUS]        {result.http_status}")
        print(f"[PROVIDER_CODE]      {result.provider_code}")
        print(f"[SAFE_MESSAGE]       {result.safe_message}")
        print("=" * 70)
        print("[RESULT] Gemini call failed. Use above diagnostics to fix credentials/quota/endpoint.")
        return 1


def main() -> None:
    args = parse_args()
    exit_code = asyncio.run(async_main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
