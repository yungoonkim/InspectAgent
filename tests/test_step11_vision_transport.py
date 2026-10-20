"""Installed Gemini SDK serialization with MockTransport and blocked real sockets."""

import asyncio
import base64
import hashlib
import json
from pathlib import Path
import socket
import traceback
from uuid import uuid4

import cv2
from google.genai.client import Client as InstalledClient
import httpx
import numpy as np
import pytest

from backend.vision_review import VisionJudgeDraft, VisionPolicy, VisionReviewError, VisionReviewService
from backend.vision_transport import GeminiVisionTransport, SingleAttemptTransport, SUPPORTED_MODELS, VisionTransportError
from tests.test_grab_inspection import harness
from tests.test_reinspection_workflow import first_warning


@pytest.fixture(autouse=True)
def offline_sdk(monkeypatch):
    monkeypatch.setattr("backend.vision_transport.genai.Client", InstalledClient)
    original_connect = socket.socket.connect
    def forbidden(*arguments, **keywords):
        if any(frame.name in ("socketpair", "_fallback_socketpair") and Path(frame.filename).name == "socket.py"
               for frame in traceback.extract_stack()):
            return original_connect(*arguments, **keywords)
        raise AssertionError("External network forbidden")
    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.setattr("socket.socket.connect_ex", forbidden)


def sample():
    encoded, raw = cv2.imencode(".png", np.full((32, 48, 3), 128, dtype=np.uint8))
    assert encoded
    payload = raw.tobytes()
    draft = {"judge_verdict": "REINSPECT", "visible_observations": [], "defect_locations": [],
             "judge_rationale": "Synthetic fixture cannot establish product condition",
             "limitations": ["Synthetic test only"], "recommended_operator_action": "Human check required"}
    return payload, draft


def request_arguments(raw, model="gemini-4-argon"):
    return {"model": model, "contents": [{"role": "user", "parts": [
        {"text": "Independent exterior observation"}, {"inline_data": {"mime_type": "image/png", "data": raw}}]}],
        "config": {"response_mime_type": "application/json", "response_json_schema": VisionJudgeDraft.model_json_schema()}}


@pytest.mark.parametrize("status", [200, 400, 401, 403, 429, 500, 503, 307, "timeout", "connection"])
@pytest.mark.parametrize("model", sorted(SUPPORTED_MODELS))
def test_installed_sdk_has_one_http_attempt_and_no_retry(status, model):
    raw, draft = sample()
    requests = []
    structures = []
    async def handler(request):
        requests.append(request)
        body = json.loads(request.content)
        structures.append({"root": list(body), "parts": [list(part) for part in body.get("contents", [{}])[0].get("parts", [])],
                           "config": list(body.get("generationConfig", {})),
                           "inline": list(body["contents"][0]["parts"][1].get("inlineData", {}))})
        inline = body["contents"][0]["parts"][1]["inlineData"]
        assert inline["mime_type"] == "image/png" and base64.urlsafe_b64decode(inline["data"]) == raw
        assert request.url.path == f"/v1beta/models/{model}:generateContent"
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["generationConfig"]["maxOutputTokens"] == 4096
        assert not body.get("tools")
        if status == "timeout":
            raise httpx.ReadTimeout("synthetic", request=request)
        if status == "connection":
            raise httpx.ConnectError("synthetic", request=request)
        if status != 200:
            return httpx.Response(status, json={"error": {"code": status, "message": "Synthetic provider error", "status": "UNAVAILABLE"}})
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": json.dumps(draft)}]},
                                                      "finishReason": "STOP"}], "modelVersion": model})
    async def run():
        transport = GeminiVisionTransport("SYNTHETIC_NOT_A_CREDENTIAL", test_transport=httpx.MockTransport(handler))
        assert transport.analysis_mode == "FAKE_TEST"
        if status == 200:
            try:
                response = await transport.generate_content(**request_arguments(raw, model))
            except VisionTransportError as error:
                pytest.fail(f"SDK exception_class={error.exception_class}; attempts={transport.http_attempts}; structure={structures}")
            assert json.loads(response.text) == draft and response.finish_reason == "STOP"
            assert response.model_version == model
        else:
            with pytest.raises(VisionTransportError) as caught:
                await transport.generate_content(**request_arguments(raw, model))
            assert caught.value.code == ("VISION_TIMEOUT" if status == "timeout" else
                                         "VISION_REDIRECT_REJECTED" if status == 307 else "VISION_PROVIDER_FAILED")
        assert transport.http_attempts == 1 and len(requests) == 1
        with pytest.raises(VisionTransportError, match="VISION_HTTP_ATTEMPT_LIMIT"):
            await transport.generate_content(**request_arguments(raw, model))
        assert len(requests) == 1
    asyncio.run(run())


def test_transport_guard_rejects_second_http_request_and_other_destination():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={})
    async def run():
        guard = SingleAttemptTransport(httpx.MockTransport(handler))
        async with httpx.AsyncClient(transport=guard) as client:
            with pytest.raises(VisionTransportError, match="VISION_DESTINATION_REJECTED"):
                await client.post("https://unapproved.invalid/generate")
            assert guard.attempts == 0
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-4-argon:generateContent"
            assert (await client.post(url)).status_code == 200
            with pytest.raises(VisionTransportError, match="VISION_HTTP_ATTEMPT_LIMIT"):
                await client.post(url)
        assert guard.attempts == 1 and len(calls) == 1
    asyncio.run(run())


@pytest.mark.parametrize("message,expected", [
    ("Your API key was reported as leaked. Please use another API key.", "reported as leaked"),
    ("Your project has been denied access. Please contact support.", "denied access"),
    ("Request had insufficient authentication scopes.", "insufficient authentication scopes"),
])
@pytest.mark.parametrize("model", sorted(SUPPORTED_MODELS))
def test_provider_403_logs_google_code_and_safe_message_without_retry(caplog, message, expected, model):
    raw, _draft = sample()
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(403, json={"error": {"code": 403, "status": "PERMISSION_DENIED",
            "message": message, "details": [{"metadata": {"secret": "DO_NOT_LOG_DETAILS"}}]}})
    async def run():
        transport = GeminiVisionTransport("SYNTHETIC_NOT_A_CREDENTIAL", test_transport=httpx.MockTransport(handler))
        with pytest.raises(VisionTransportError, match="VISION_PROVIDER_FAILED"):
            await transport.generate_content(**request_arguments(raw, model))
        with pytest.raises(VisionTransportError, match="VISION_HTTP_ATTEMPT_LIMIT"):
            await transport.generate_content(**request_arguments(raw, model))
        assert transport.http_attempts == 1 and len(calls) == 1
    with caplog.at_level("WARNING", logger="backend.vision_transport"):
        asyncio.run(run())
    records = [record for record in caplog.records if record.name == "backend.vision_transport"]
    assert len(records) == 1
    details = json.loads(records[0].getMessage().split(" ", 1)[1])
    assert details["http_status"] == details["google_error_code"] == 403
    assert details["google_error_status"] == "PERMISSION_DENIED"
    assert details["model"] == model
    assert expected in details["google_error_message"]
    assert "DO_NOT_LOG_DETAILS" not in records[0].getMessage()
    assert "SYNTHETIC_NOT_A_CREDENTIAL" not in records[0].getMessage()


@pytest.mark.parametrize("message", [
    'Authorization: Bearer TOKEN_MUST_NOT_APPEAR\nx-goog-api-key=SYNTHETIC_NOT_A_CREDENTIAL',
    'Denied key=SYNTHETIC_NOT_A_CREDENTIAL\naccess_token=TOKEN_MUST_NOT_APPEAR',
    'Denied data:image/png;base64,IMAGE_MUST_NOT_APPEAR',
    '{"contents":[{"inlineData":{"data":"IMAGE_MUST_NOT_APPEAR"}}]}',
    'Denied "IMAGE_MUST_NOT_APPEAR"',
    "Denied " + "a" * 5000,
])
def test_provider_403_diagnostics_exclude_credentials_and_image_data(message):
    from google.genai.errors import ClientError
    from backend.vision_transport import _safe_provider_error

    error = ClientError(403, {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": message}})
    diagnostic = _safe_provider_error(error, "SYNTHETIC_NOT_A_CREDENTIAL")
    serialized = json.dumps(diagnostic)
    for sensitive in ("SYNTHETIC_NOT_A_CREDENTIAL", "TOKEN_MUST_NOT_APPEAR", "IMAGE_MUST_NOT_APPEAR", "a" * 501):
        assert sensitive not in serialized
    assert diagnostic["google_error_code"] == 403
    assert diagnostic["google_error_status"] == "PERMISSION_DENIED"
    assert len(diagnostic["google_error_message"]) <= 500


@pytest.mark.parametrize("case", ["default", "missing_key", "wrong_model"])
def test_live_factory_fails_closed_without_full_explicit_approval(tmp_path, monkeypatch, case):
    for name in ("LIVE_ENABLED", "APPROVED_INSPECTION_ID", "APPROVED_IMAGE_SHA256", "MODEL"):
        monkeypatch.delenv("VISION_REVIEW_" + name, raising=False)
    if case != "default":
        monkeypatch.setenv("VISION_REVIEW_LIVE_ENABLED", "true")
    if case in {"missing_key", "wrong_model"}:
        monkeypatch.setenv("VISION_REVIEW_APPROVED_INSPECTION_ID", "INSP-900001")
        monkeypatch.setenv("VISION_REVIEW_APPROVED_IMAGE_SHA256", "a" * 64)
    if case == "wrong_model":
        monkeypatch.setenv("VISION_REVIEW_MODEL", "unverified-model")
    service = VisionReviewService.from_environment(tmp_path, None if case == "missing_key" else "SYNTHETIC")
    assert service.client is None
    assert not service.capabilities({"inspection_id": "INSP-900001", "image_sha256": "a" * 64})["enabled"]
    assert not (tmp_path / "state.json").exists()


@pytest.mark.parametrize("model", sorted(SUPPORTED_MODELS))
def test_live_configuration_is_dynamic_but_no_request_without_consent(tmp_path, monkeypatch, model):
    raw, draft = sample()
    digest = hashlib.sha256(raw).hexdigest()
    monkeypatch.setenv("VISION_REVIEW_LIVE_ENABLED", "true")
    monkeypatch.setenv("VISION_REVIEW_MODEL", model)
    monkeypatch.setenv("VISION_REVIEW_APPROVED_INSPECTION_ID", "INSP-900001")
    monkeypatch.setenv("VISION_REVIEW_APPROVED_IMAGE_SHA256", digest)
    service = VisionReviewService.from_environment(tmp_path, "SYNTHETIC_NOT_A_CREDENTIAL")
    image = {"inspection_id": "INSP-900001", "image_sha256": digest}
    assert service.capabilities(image)["live_enabled"]
    assert service.capabilities(image)["model_requested"] == model
    assert service.capabilities(image)["model_support"] == "DOCUMENTED_IMAGE_AND_JSON"
    assert service.capabilities({**image, "inspection_id": "INSP-900002"})["enabled"]
    assert service.capabilities({**image, "image_sha256": "b" * 64})["enabled"]
    assert service.client is None
    async def run():
        with pytest.raises(VisionReviewError, match="VISION_TRANSMISSION_CONSENT_REQUIRED"):
            await service.create("owner", {**image, "inspection_id": "INSP-900002"}, raw, "a" * 32, lambda: image)
    asyncio.run(run())
    assert service.client is None
    assert not (tmp_path / "state.json").exists()


@pytest.mark.parametrize("model", sorted(SUPPORTED_MODELS))
def test_saved_crop_traverses_service_and_installed_sdk_without_external_io(harness, model):
    record = first_warning(harness)
    raw = (harness.directory / "inputs" / f'{record["image_id"]}.png').read_bytes()
    image = {"inspection_id": record["inspection_id"], "image_id": record["image_id"],
             "capture_id": record["metrics"]["input_provenance"]["capture_id"],
             "image_sha256": hashlib.sha256(raw).hexdigest(), "crop_width": 160, "crop_height": 96,
             "reinspection_group_id": record["metrics"]["reinspection"]["group_id"]}
    _, draft = sample()
    captured = []
    def handler(request):
        captured.append(request)
        assert request.url.path == f"/v1beta/models/{model}:generateContent"
        parts = json.loads(request.content)["contents"][0]["parts"]
        assert base64.urlsafe_b64decode(parts[1]["inlineData"]["data"]) == raw
        assert "40.1631" not in parts[0]["text"] and "anomaly_score" not in parts[0]["text"]
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(draft)}]}, "finishReason": "STOP"}],
                                        "modelVersion": model})
    client = GeminiVisionTransport("SYNTHETIC_NOT_A_CREDENTIAL", test_transport=httpx.MockTransport(handler))
    service = VisionReviewService(harness.directory / "sdk-vision", VisionPolicy(model=model), fake_client=client, allow_fake=True)
    before = {path: path.read_bytes() for path in harness.directory.glob("*.jsonl")}
    async def run():
        review = await service.create("owner", image, raw, "c" * 32, lambda: image, confirmed=True)
        assert review["judge_verdict"] == "REINSPECT" and review["analysis_mode"] == "FAKE_TEST", (
            review.get("failure_code"), review.get("exception_class"))
        assert review["http_attempts"] == 1 and review["provider_http_status"] == 200
        assert review["image_sha256"] == image["image_sha256"]
        assert review["model_requested"] == review["model_resolved"] == model
        assert await service.create("owner", image, raw, "c" * 32, lambda: image, confirmed=True) == review
        assert len(captured) == 1
    asyncio.run(run())
    assert all(path.read_bytes() == value for path, value in before.items())
    assert harness.storage.get_inspection(record["inspection_id"]).final_result == "REINSPECT"


@pytest.mark.parametrize("configured_timeout", [None, "15", "30"])
@pytest.mark.parametrize("model", sorted(SUPPORTED_MODELS))
def test_dynamic_live_factory_uses_a_fresh_one_attempt_transport_per_image(harness, monkeypatch, model, configured_timeout):
    from types import SimpleNamespace
    import backend.main as main
    from tests.test_dynamic_vision_judge import new_crop

    records = [new_crop(SimpleNamespace(h=harness), variant) for variant in (1, 2)]
    expected = [(harness.runtime.root / f'{record["image_id"]}.png').read_bytes() for record in records]
    transports, requests = [], []
    expected_timeout = int(configured_timeout or "15")
    _, draft = sample()
    def handler(request):
        assert request.url.path == f"/v1beta/models/{model}:generateContent"
        assert request.headers["X-Server-Timeout"] == str(expected_timeout)
        assert request.extensions["timeout"] == dict.fromkeys(("connect", "read", "write", "pool"), expected_timeout)
        parts = json.loads(request.content)["contents"][0]["parts"]
        requests.append(base64.urlsafe_b64decode(parts[1]["inlineData"]["data"]))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(draft)}]},
                                                       "finishReason": "STOP"}], "modelVersion": model})
    def transport_factory(key, timeout):
        transport = GeminiVisionTransport(key, timeout, test_transport=httpx.MockTransport(handler))
        transports.append(transport)
        return transport
    monkeypatch.setattr("backend.vision_review.GeminiVisionTransport", transport_factory)
    monkeypatch.setenv("VISION_REVIEW_LIVE_ENABLED", "true")
    monkeypatch.setenv("VISION_REVIEW_MODEL", model)
    if configured_timeout is None:
        monkeypatch.delenv("VISION_REVIEW_TIMEOUT_SECONDS", raising=False)
    else:
        monkeypatch.setenv("VISION_REVIEW_TIMEOUT_SECONDS", configured_timeout)
    monkeypatch.delenv("VISION_REVIEW_APPROVED_INSPECTION_ID", raising=False)
    monkeypatch.delenv("VISION_REVIEW_APPROVED_IMAGE_SHA256", raising=False)
    service = VisionReviewService.from_environment(harness.directory / "dynamic-sdk", "SYNTHETIC_NOT_A_CREDENTIAL")
    assert service.policy.timeout_seconds == expected_timeout
    monkeypatch.setattr(main.app.state, "vision_review_service", service, raising=False)
    for record in records:
        result = harness.client.post(f'/inspections/{record["inspection_id"]}/vision-review', json={
            "request_id": uuid4().hex, "confirm_external_transmission": True})
        assert result.status_code == 200, result.text
        review = result.json()["review"]
        assert review["analysis_status"] == "COMPLETED" and review["analysis_mode"] == "FAKE_TEST"
        assert review["http_attempts"] == 1
        assert review["model_requested"] == review["model_resolved"] == model
    assert requests == expected and expected[0] != expected[1]
    assert len(transports) == 2 and transports[0] is not transports[1]
    assert all(transport.http_attempts == 1 for transport in transports)
    assert all(transport.timeout_seconds == expected_timeout for transport in transports)


@pytest.mark.parametrize("value", ["", "invalid", "15.5", "0", "-1", "31", "nan", "inf"])
def test_invalid_environment_timeout_fails_before_request_or_storage(tmp_path, monkeypatch, value):
    monkeypatch.setenv("VISION_REVIEW_TIMEOUT_SECONDS", value)
    monkeypatch.setenv("VISION_REVIEW_LIVE_ENABLED", "true")
    monkeypatch.setenv("VISION_REVIEW_MODEL", "gemini-3.8-flash")
    with pytest.raises(ValueError):
        VisionReviewService.from_environment(tmp_path, "SYNTHETIC_NOT_A_CREDENTIAL")
    assert not (tmp_path / "state.json").exists()


@pytest.mark.parametrize("model", sorted(SUPPORTED_MODELS))
def test_guard_binds_one_allowed_model_and_keeps_destination_restrictions(model):
    assert SUPPORTED_MODELS == frozenset({"gemini-4-argon", "gemini-3.8-flash"})
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={})
    async def run():
        guard = SingleAttemptTransport(httpx.MockTransport(handler), model=model)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        other_model = next(value for value in SUPPORTED_MODELS if value != model)
        rejected = [
            url.replace("https://", "http://"),
            url.replace("generativelanguage.googleapis.com", "unapproved.invalid"),
            url.replace("generativelanguage.googleapis.com", "generativelanguage.googleapis.com:8443"),
            url.replace(model, other_model),
            url.replace(model, "unapproved-model"),
            url.replace("/v1beta/", "/v1/"),
            url + "?key=SYNTHETIC",
        ]
        async with httpx.AsyncClient(transport=guard) as client:
            for destination in rejected:
                with pytest.raises(VisionTransportError, match="VISION_DESTINATION_REJECTED"):
                    await client.post(destination)
            with pytest.raises(VisionTransportError, match="VISION_DESTINATION_REJECTED"):
                await client.get(url)
            assert guard.attempts == 0 and calls == []
            assert (await client.post(url)).status_code == 200
            with pytest.raises(VisionTransportError, match="VISION_HTTP_ATTEMPT_LIMIT"):
                await client.post(url)
        assert guard.attempts == len(calls) == 1
    asyncio.run(run())


@pytest.mark.parametrize("model", ["unapproved-model", "gemini-3.8-flash-latest", "../gemini-3.8-flash", None])
def test_unapproved_models_fail_before_any_http_request(model):
    raw, _draft = sample()
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={})
    async def run():
        transport = GeminiVisionTransport("SYNTHETIC_NOT_A_CREDENTIAL", test_transport=httpx.MockTransport(handler))
        with pytest.raises(VisionTransportError, match="VISION_TRANSPORT_CONFIG_INVALID"):
            await transport.generate_content(**request_arguments(raw, model))
        assert transport.http_attempts == 0 and calls == []
        with pytest.raises(VisionTransportError, match="VISION_TRANSPORT_CONFIG_INVALID"):
            SingleAttemptTransport(httpx.MockTransport(handler), model=model)
    asyncio.run(run())
