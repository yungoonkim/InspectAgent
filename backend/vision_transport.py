"""Opt-in, single-HTTP-attempt Gemini image transport, separate from the Agent."""

import json
import logging
import re
from types import SimpleNamespace

from google import genai
from google.genai import errors, types
import httpx


SUPPORTED_MODEL = "gemini-4-argon"
SUPPORTED_MODELS = frozenset({SUPPORTED_MODEL, "gemini-3.8-flash"})
logger = logging.getLogger(__name__)


def _safe_provider_error(error, api_key):
    status = error.status if isinstance(error.status, str) and error.status in {
        "PERMISSION_DENIED", "UNAUTHENTICATED", "INVALID_ARGUMENT", "FAILED_PRECONDITION",
        "NOT_FOUND", "RESOURCE_EXHAUSTED", "INTERNAL", "UNAVAILABLE", "UNKNOWN",
    } else "UNKNOWN"
    message = error.message if isinstance(error.message, str) else ""
    if len(message) > 4096 or re.search(r'[{}\[\]\x00-\x08\x0b\x0c\x0e-\x1f]', message):
        message = "[REDACTED_PROVIDER_MESSAGE]"
    else:
        if api_key:
            message = message.replace(api_key, "[REDACTED]")
        message = re.sub(r'AIza[A-Za-z0-9_-]{20,}', '[REDACTED]', message)
        message = re.sub(r'(?i)\b(?:authorization|x-goog-api-key|api[_ -]?key|(?:access|id|refresh)[_-]?token)\s*[:=]\s*[^\r\n;,]+',
                         '[REDACTED_AUTH]', message)
        message = re.sub(r'(?i)\bBearer\s+[^\s,;]+', '[REDACTED_AUTH]', message)
        message = re.sub(r'(?i)data:image/[^\s]+', '[REDACTED_IMAGE]', message)
        message = re.sub(r'https?://[^\s<>"\x27]+', '[REDACTED_URL]', message)
        message = re.sub(r'"[^"\r\n]*"|\x27[^\x27\r\n]*\x27', '[REDACTED_VALUE]', message)
        message = re.sub(r'[A-Za-z0-9_+/=-]{32,}', '[REDACTED_DATA]', message)
        message = ' '.join(message.split())[:500] or "PROVIDER_MESSAGE_UNAVAILABLE"
    return {"google_error_code": error.code if type(error.code) is int else None,
            "google_error_status": status, "google_error_message": message}


class VisionTransportError(Exception):
    def __init__(self, code, http_status=None, exception_class=None):
        self.code = code
        self.http_status = http_status
        self.exception_class = exception_class
        super().__init__(code)


class SingleAttemptTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner, *, model=SUPPORTED_MODEL):
        if not isinstance(model, str) or model not in SUPPORTED_MODELS:
            raise VisionTransportError("VISION_TRANSPORT_CONFIG_INVALID")
        self.inner = inner
        self.model = model
        self.attempts = 0
        self.http_status = None

    async def handle_async_request(self, request):
        expected_path = f"/v1beta/models/{self.model}:generateContent"
        if (request.method != "POST" or request.url.scheme != "https"
                or request.url.host != "generativelanguage.googleapis.com"
                or request.url.port not in (None, 443) or request.url.path != expected_path
                or request.url.query):
            raise VisionTransportError("VISION_DESTINATION_REJECTED")
        if self.attempts >= 1:
            raise VisionTransportError("VISION_HTTP_ATTEMPT_LIMIT")
        self.attempts += 1
        response = await self.inner.handle_async_request(request)
        self.http_status = response.status_code
        if 300 <= response.status_code < 400:
            await response.aclose()
            raise VisionTransportError("VISION_REDIRECT_REJECTED", response.status_code)
        return response

    async def aclose(self):
        await self.inner.aclose()


class GeminiVisionTransport:
    def __init__(self, api_key, timeout_seconds=15, *, test_transport=None):
        self.analysis_mode = "FAKE_TEST" if test_transport is not None else "LIVE"
        self.aio = SimpleNamespace(models=self)
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.test_transport = test_transport
        self.guard = None
        self.used = False

    @property
    def http_attempts(self):
        return self.guard.attempts if self.guard is not None else 0

    @property
    def provider_http_status(self):
        return self.guard.http_status if self.guard is not None else None

    async def generate_content(self, *, model, contents, config):
        if self.used:
            raise VisionTransportError("VISION_HTTP_ATTEMPT_LIMIT")
        if not isinstance(model, str) or model not in SUPPORTED_MODELS or not self.api_key:
            raise VisionTransportError("VISION_TRANSPORT_CONFIG_INVALID")
        self.used = True
        inner = self.test_transport if self.test_transport is not None else httpx.AsyncHTTPTransport(retries=0)
        self.guard = SingleAttemptTransport(inner, model=model)
        http_client = httpx.AsyncClient(transport=self.guard, trust_env=False, follow_redirects=False,
                                       timeout=self.timeout_seconds)
        client = None
        try:
            client = genai.Client(api_key=self.api_key, vertexai=False, http_options=types.HttpOptions(
                base_url="https://generativelanguage.googleapis.com", api_version="v1beta",
                timeout=int(self.timeout_seconds * 1000), retry_options=types.HttpRetryOptions(attempts=1),
                httpx_async_client=http_client, client_args={"trust_env": False}))
            response = await client.aio.models.generate_content(model=model,
                contents=[types.Content.model_validate(content) for content in contents],
                config=types.GenerateContentConfig(**config, max_output_tokens=4096,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
            candidates = response.candidates or []
            reason = candidates[0].finish_reason if candidates else None
            return SimpleNamespace(text=response.text, model_version=response.model_version,
                                   finish_reason=getattr(reason, "value", reason))
        except (TimeoutError, httpx.TimeoutException):
            raise VisionTransportError("VISION_TIMEOUT", self.provider_http_status) from None
        except VisionTransportError:
            raise
        except Exception as error:
            if self.provider_http_status == 403 and isinstance(error, errors.APIError):
                logger.warning("VISION_PROVIDER_REJECTED %s", json.dumps({
                    "http_status": self.provider_http_status, "model": model,
                    **_safe_provider_error(error, self.api_key),
                }, ensure_ascii=True))
            raise VisionTransportError("VISION_PROVIDER_FAILED", self.provider_http_status, type(error).__name__) from None
        finally:
            try:
                if client is not None:
                    await client.aio.aclose()
                    client.close()
            finally:
                await http_client.aclose()
