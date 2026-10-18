"""Unit and safety tests for scripts/day7_gemini_single_call.py.

Verifies with 0 live API calls:
1. Default DRY RUN makes 0 network calls
2. CLI without --execute-once makes 0 network calls
3. Mismatched confirmation phrase aborts with 0 network calls
4. Authorized live single call executes exactly 1 request with no retries
5. Multiple invocations on the same executor are strictly blocked
6. Provider errors (400, 401, 403, 404, 429) log diagnostic details without retries
7. Timeout errors are captured safely
8. API keys and bearer tokens are thoroughly redacted
"""

import argparse
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from google.genai import errors, types
import pytest

from scripts.day7_gemini_single_call import (
    REQUIRED_CONFIRMATION,
    SingleCallExecutor,
    _extract_provider_error_code,
    _extract_status_code,
    _sanitize_error_message,
    async_main,
)


def mock_response(text="OK", finish_reason=types.FinishReason.STOP):
    candidate = types.Candidate(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=text)],
        ),
        finish_reason=finish_reason,
    )
    return types.GenerateContentResponse(candidates=[candidate])


@pytest.fixture
def mock_client():
    generator = AsyncMock()
    client = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(generate_content=generator),
            aclose=AsyncMock(),
        ),
        close=Mock(),
    )
    return client, generator


@pytest.fixture
def test_settings():
    return SimpleNamespace(
        GEMINI_MODEL="gemini-3.8-flash",
        GEMINI_API_KEY="test-mock-api-key-for-unit-tests",
        AGENT_MODEL_TIMEOUT_SECONDS=15.0,
    )


def test_dry_run_executes_zero_network_calls(mock_client, test_settings):
    client, generator = mock_client
    executor = SingleCallExecutor(client=client, settings=test_settings)

    result = pytest.run_async(executor.execute_dry_run()) if hasattr(pytest, "run_async") else None
    # Use asyncio.run for standard test
    import asyncio
    result = asyncio.run(executor.execute_dry_run())

    assert result.status == "DRY_RUN"
    assert result.network_calls_attempted == 0
    assert result.model_name == "gemini-3.8-flash"
    generator.assert_not_called()


def test_cli_without_execute_once_flag_is_dry_run(monkeypatch):
    args = argparse.Namespace(execute_once=False, confirm_phrase=None)
    import asyncio
    with patch("scripts.day7_gemini_single_call.SingleCallExecutor.execute_dry_run") as mock_dry:
        mock_dry.return_value = SimpleNamespace(status="DRY_RUN", network_calls_attempted=0)
        exit_code = asyncio.run(async_main(args))

    assert exit_code == 0
    mock_dry.assert_called_once()


@pytest.mark.parametrize("bad_phrase", ["", "run one gemini request", "RUN ONE", "YES", "CONFIRM"])
def test_cli_with_mismatched_confirmation_aborts_with_zero_calls(bad_phrase):
    args = argparse.Namespace(execute_once=True, confirm_phrase=bad_phrase)
    import asyncio
    with patch("scripts.day7_gemini_single_call.SingleCallExecutor.execute_live_single_call") as mock_live:
        exit_code = asyncio.run(async_main(args))

    assert exit_code == 1
    mock_live.assert_not_called()


def test_single_call_success_executes_exactly_once(mock_client, test_settings):
    client, generator = mock_client
    generator.return_value = mock_response(text="OK")
    executor = SingleCallExecutor(client=client, settings=test_settings)

    import asyncio
    result = asyncio.run(executor.execute_live_single_call())

    assert result.status == "SUCCESS"
    assert result.network_calls_attempted == 1
    assert result.response_text == "OK"
    assert result.finish_reason == "STOP"
    assert result.model_name == "gemini-3.8-flash"
    assert result.elapsed_ms >= 0

    # Verify exactly 1 call
    assert generator.await_count == 1
    call_kwargs = generator.call_args.kwargs
    assert call_kwargs["model"] == "gemini-3.8-flash"
    assert call_kwargs["contents"] == "Reply exactly OK"
    config = call_kwargs["config"]
    assert config.temperature == 0
    assert config.max_output_tokens == 16
    assert config.automatic_function_calling.disable is True
    assert config.automatic_continuation is False
    assert config.http_options.retry_options.attempts == 1


def test_multiple_calls_strictly_blocked_by_guard(mock_client, test_settings):
    client, generator = mock_client
    generator.return_value = mock_response()
    executor = SingleCallExecutor(client=client, settings=test_settings)

    import asyncio
    # 1st call succeeds
    result1 = asyncio.run(executor.execute_live_single_call())
    assert result1.network_calls_attempted == 1

    # 2nd call must raise RuntimeError
    with pytest.raises(RuntimeError, match="Further calls forbidden"):
        asyncio.run(executor.execute_live_single_call())

    # Call count remains strictly 1
    assert generator.await_count == 1


@pytest.mark.parametrize(
    "status_code,status_str",
    [
        (400, "INVALID_ARGUMENT"),
        (401, "UNAUTHENTICATED"),
        (403, "PERMISSION_DENIED"),
        (404, "NOT_FOUND"),
        (429, "RESOURCE_EXHAUSTED"),
    ],
)
def test_provider_errors_captured_without_retries(mock_client, test_settings, status_code, status_str):
    client, generator = mock_client
    failure = errors.ClientError(
        status_code,
        {"error": {"code": status_code, "status": status_str, "message": "Test provider error"}},
    )
    generator.side_effect = failure
    executor = SingleCallExecutor(client=client, settings=test_settings)

    import asyncio
    result = asyncio.run(executor.execute_live_single_call())

    assert result.status == "FAILED"
    assert result.network_calls_attempted == 1
    assert result.http_status == status_code
    assert result.provider_code == status_str
    assert result.exception_class == "ClientError"
    # Verify no retries: exactly 1 call was attempted
    assert generator.await_count == 1


def test_timeout_error_captured_without_retries(mock_client, test_settings):
    client, generator = mock_client
    generator.side_effect = TimeoutError()
    executor = SingleCallExecutor(client=client, settings=test_settings)

    import asyncio
    result = asyncio.run(executor.execute_live_single_call())

    assert result.status == "FAILED"
    assert result.network_calls_attempted == 1
    assert result.http_status == 504
    assert result.provider_code == "TIMEOUT"
    assert result.exception_class == "TimeoutError"
    assert generator.await_count == 1


def test_credentials_masked_in_failure_output(mock_client, test_settings):
    client, generator = mock_client
    secret_key = "AIzaSySecretApiKey12345678901234567890"
    bearer_token = "Bearer confidential-token-98765"
    failure = RuntimeError(f"Connection failed: key={secret_key} and {bearer_token}")
    generator.side_effect = failure
    executor = SingleCallExecutor(client=client, settings=test_settings)

    import asyncio
    result = asyncio.run(executor.execute_live_single_call())

    assert result.status == "FAILED"
    assert "[REDACTED]" in result.safe_message
    assert secret_key not in result.safe_message
    assert "confidential-token" not in result.safe_message
