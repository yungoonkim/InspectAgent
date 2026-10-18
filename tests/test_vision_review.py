"""FAKE_TEST image second opinion; guarded by the offline safety harness."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from types import SimpleNamespace
import threading
from uuid import uuid4

import cv2
import numpy as np
import pytest

import backend.main as main
from backend.vision_review import VisionPolicy, VisionReviewError, VisionReviewService, validate_crop
from tests.test_grab_inspection import harness
from tests.test_reinspection_workflow import first_warning, three_warnings, review as manual_review


class FakeVisionClient:
    analysis_mode = "FAKE_TEST"

    def __init__(self):
        self.aio = SimpleNamespace(models=self)
        self.calls = []
        self.text = json.dumps({"classification": "QUALITY_ISSUE", "visible_observations": ["MOCK TEST: low contrast"],
            "limitations": ["Synthetic fixture; not a product evaluation"], "recommended_operator_action": "Human check only"})
        self.error = None
        self.finish_reason = None
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = False
        self.mutate = None

    async def generate_content(self, **arguments):
        self.calls.append(arguments)
        self.entered.set()
        while self.block and not self.release.is_set():
            await asyncio.sleep(0.002)
        if self.mutate:
            self.mutate()
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text, model_version="MOCK_MODEL_ONLY", finish_reason=self.finish_reason)


@pytest.fixture
def vision(harness, monkeypatch):
    record = first_warning(harness)
    fake = FakeVisionClient()
    service = VisionReviewService(harness.directory / "vision", fake_client=fake, allow_fake=True)
    monkeypatch.setattr(main.app.state, "vision_review_service", service, raising=False)
    return SimpleNamespace(h=harness, record=record, fake=fake, service=service,
        endpoint=f'/inspections/{record["inspection_id"]}/vision-review')


def post(vision, request_id=None, **extra):
    return vision.h.client.post(vision.endpoint, json={"request_id": request_id or uuid4().hex, **extra})


@pytest.mark.parametrize("classification", ["DEFECT_SUSPECTED", "QUALITY_ISSUE", "NO_VISIBLE_DEFECT", "INCONCLUSIVE"])
def test_verified_png_is_the_only_image_part_and_classification_is_not_engine_verdict(vision, classification):
    value = json.loads(vision.fake.text)
    value["classification"] = classification
    vision.fake.text = json.dumps(value)
    before = {name: (vision.h.directory / name).read_bytes() for name in ("inspections.jsonl", "logs.jsonl")}
    group_before = (vision.h.runtime.reinspections.root / "state.json").read_bytes()
    result = post(vision)
    assert result.status_code == 200, result.text
    body = result.json()
    saved = body["review"]
    assert saved["classification"] == classification and saved["analysis_mode"] == "FAKE_TEST"
    assert saved["inspection_id"] == vision.record["inspection_id"]
    assert saved["model_requested"] == "gemini-4-argon" and saved["model_resolved"] == "MOCK_MODEL_ONLY"
    assert body["capabilities"]["live_enabled"] is False
    assert len(vision.fake.calls) == 1 and len(vision.h.fake.images) == 1
    arguments = vision.fake.calls[0]
    parts = arguments["contents"][0]["parts"]
    expected = (vision.h.directory / "inputs" / f'{vision.record["image_id"]}.png').read_bytes()
    assert parts[1] == {"inline_data": {"mime_type": "image/png", "data": expected}}
    assert saved["image_sha256"] == hashlib.sha256(expected).hexdigest()
    for forbidden in ("34.1442", vision.record["inspection_id"], "REINSPECT", "anomaly_score", "input_provenance"):
        assert forbidden not in parts[0]["text"]
    for name, raw in before.items(): assert (vision.h.directory / name).read_bytes() == raw
    assert (vision.h.runtime.reinspections.root / "state.json").read_bytes() == group_before


@pytest.mark.parametrize("value", ["invalid", "{}", '{"classification":"OK"}',
    json.dumps({"classification":"NO_VISIBLE_DEFECT","visible_observations":[],"limitations":["none"],"recommended_operator_action":"check"}),
    json.dumps({"classification":"INCONCLUSIVE","visible_observations":[],"limitations":["unknown"],"recommended_operator_action":"check","final_result":"OK"})])
def test_invalid_response_is_persisted_failure_not_fabricated_success(vision, value):
    vision.fake.text = value
    result = post(vision).json()["review"]
    assert result["classification"] == "ANALYSIS_FAILED" and result["failure_code"] == "VISION_INVALID_RESPONSE"
    assert result["visible_observations"] == []


@pytest.mark.parametrize("kind,expected", [("timeout","VISION_TIMEOUT"), ("sdk","VISION_SDK_FAILED"),
    ("empty","VISION_EMPTY_RESPONSE"), ("tokens","VISION_MAX_TOKENS"), ("oversize","VISION_RESPONSE_TOO_LARGE")])
def test_failure_never_retries_or_changes_verdict(vision, kind, expected):
    if kind == "timeout": vision.fake.error = TimeoutError()
    if kind == "sdk": vision.fake.error = RuntimeError("PRIVATE_CREDENTIAL_MUST_NOT_APPEAR")
    if kind == "empty": vision.fake.text = None
    if kind == "tokens": vision.fake.finish_reason = "MAX_TOKENS"
    if kind == "oversize": vision.fake.text = "x" * 33000
    result = post(vision)
    assert result.json()["review"]["classification"] == "ANALYSIS_FAILED"
    assert result.json()["review"]["failure_code"] == expected
    assert "PRIVATE_CREDENTIAL" not in result.text and len(vision.fake.calls) == 1
    assert vision.h.storage.get_inspection(vision.record["inspection_id"]).final_result == "REINSPECT"


def test_default_disabled_even_with_enable_environment_flag(vision, monkeypatch):
    monkeypatch.setenv("VISION_REVIEW_ENABLED", "1")
    service = VisionReviewService(vision.h.directory / "disabled")
    monkeypatch.setattr(main.app.state, "vision_review_service", service)
    state = vision.h.client.get(vision.endpoint).json()
    assert state["capabilities"]["enabled"] is False and state["capabilities"]["live_enabled"] is False
    assert state["capabilities"]["model_support"] == "UNKNOWN"
    assert post(vision).status_code == 403 and len(vision.fake.calls) == 0
    assert not service.files.root.exists()


def test_model_setting_is_independent_of_diagnostic_agent(vision, monkeypatch):
    monkeypatch.setenv("VISION_REVIEW_MODEL", "MOCK_CANDIDATE")
    service = VisionReviewService(vision.h.directory / "candidate")
    assert service.policy.model == "MOCK_CANDIDATE"
    assert main.settings.GEMINI_MODEL == "gemini-3.8-flash"
    with pytest.raises(ValueError):
        VisionReviewService(vision.h.directory / "unsafe", fake_client=vision.fake)


@pytest.mark.parametrize("extra", [{"path":"C:/private.png"},{"image_url":"https://external.invalid"},{"image_bytes":"untrusted"},{"classification":"OK"},{"request_id":True}])
def test_strict_request_rejects_client_images_paths_and_results(vision, extra):
    assert post(vision, **extra).status_code == 422
    assert not vision.fake.calls


@pytest.mark.parametrize("kind", ["origin","csrf","owner"])
def test_access_control_precedes_fake_client(vision, kind):
    if kind == "origin": vision.h.client.headers["Origin"] = "http://untrusted.invalid"
    if kind == "csrf": vision.h.client.headers["X-Capture-CSRF"] = "invalid"
    if kind == "owner":
        token, csrf = vision.h.captures.bootstrap()
        vision.h.client.cookies.set(vision.h.captures.cookie_name, token)
        vision.h.client.headers["X-Capture-CSRF"] = csrf
    assert post(vision).status_code in {403,404}
    assert not vision.fake.calls


@pytest.mark.parametrize("change", ["source","verdict","missing"])
def test_only_grab_reinspect_is_eligible(vision, monkeypatch, change):
    record = vision.h.storage.get_inspection(vision.record["inspection_id"]).model_copy(deep=True)
    if change == "source": record.metrics["input_source"] = "REGISTERED_STATIC_IMAGE"
    if change == "verdict": record.final_result = "OK"
    if change == "missing": record = None
    monkeypatch.setattr(vision.h.storage, "get_inspection", lambda identifier: record)
    assert post(vision).status_code in {404,409} and not vision.fake.calls


@pytest.mark.parametrize("change", ["missing","hash"])
def test_durable_crop_integrity_is_checked(vision, change):
    path = vision.h.directory / "inputs" / f'{vision.record["image_id"]}.png'
    if change == "missing": path.unlink()
    else: path.write_bytes(b"changed")
    assert post(vision).status_code == 404 and not vision.fake.calls


@pytest.mark.parametrize("kind", ["format","gray","alpha","dimensions","oversize","group"])
def test_decode_size_channel_and_group_guards(vision, monkeypatch, kind):
    record = vision.h.storage.get_inspection(vision.record["inspection_id"]).model_copy(deep=True)
    source = record.metrics["input_provenance"]
    raw = (vision.h.directory / "inputs" / f'{record.image_id}.png').read_bytes()
    if kind in {"gray","alpha"}:
        shape = (source["crop_height"],source["crop_width"]) + (() if kind == "gray" else (4,))
        success, encoded = cv2.imencode('.png',np.full(shape,60,dtype=np.uint8))
        assert success
        raw = encoded.tobytes(); source["crop_sha256"] = hashlib.sha256(raw).hexdigest()
    if kind == "format": raw = b"not PNG"
    if kind == "dimensions": source["crop_width"] += 1
    if kind == "oversize": raw += b"x" * (4 * 1024 * 1024)
    if kind == "group": record.metrics["reinspection"]["group_id"] = 'RIG-WRONG'
    with pytest.raises(VisionReviewError): validate_crop(record,raw,vision.service.policy)
    assert not vision.fake.calls


def test_duplicate_request_and_persistent_one_attempt_policy(vision, monkeypatch):
    request_id = uuid4().hex
    first = post(vision, request_id).json()["review"]
    assert post(vision, request_id).json()["review"] == first
    assert post(vision).status_code == 409 and len(vision.fake.calls) == 1
    monkeypatch.setattr(main.app.state,"vision_review_service",VisionReviewService(vision.service.files.root))
    stored = vision.h.client.get(vision.endpoint).json()
    assert stored["review"] == first and not stored["capabilities"]["enabled"]


def test_other_inspection_cannot_reuse_request_id_or_image(vision):
    request_id = uuid4().hex
    post(vision,request_id)
    other = first_warning(vision.h)
    response = vision.h.client.post(f'/inspections/{other["inspection_id"]}/vision-review',json={"request_id":request_id})
    assert response.status_code == 409 and len(vision.fake.calls) == 1


def test_concurrent_duplicate_only_enters_sdk_once(vision):
    vision.fake.block = True
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(post,vision)
        try:
            assert vision.fake.entered.wait(5)
            assert post(vision).status_code == 409
        finally: vision.fake.release.set()
        assert future.result(timeout=5).status_code == 200
    assert len(vision.fake.calls) == 1


def test_actual_wait_for_timeout_has_no_automatic_resend(vision):
    vision.service.policy = VisionPolicy(timeout_seconds=0.01)
    vision.fake.block = True
    result = post(vision).json()["review"]
    assert result["classification"] == "ANALYSIS_FAILED" and result["failure_code"] == "VISION_TIMEOUT"
    assert len(vision.fake.calls) == 1


def test_changed_image_after_response_is_not_published_as_valid(vision):
    path = vision.h.directory / "inputs" / f'{vision.record["image_id"]}.png'
    vision.fake.mutate = lambda: path.write_bytes(b"changed during fake response")
    result = post(vision).json()["review"]
    assert result["classification"] == "ANALYSIS_FAILED" and result["failure_code"] == "VISION_INPUT_CHANGED"


def test_daily_attempt_limit_is_persistent(vision):
    vision.service.policy = VisionPolicy(daily_limit=1)
    post(vision)
    other = first_warning(vision.h)
    assert vision.h.client.post(f'/inspections/{other["inspection_id"]}/vision-review',json={"request_id":uuid4().hex}).status_code == 429
    assert len(vision.fake.calls) == 1


def test_existing_manual_review_and_group_are_byte_unchanged(vision):
    group = three_warnings(vision.h)
    assert manual_review(vision.h,group,"MANUAL_NG").status_code == 200
    before = (vision.h.runtime.reinspections.root / "state.json").read_bytes()
    identifier = group["attempts"][-1]["inspection_id"]
    assert vision.h.client.post(f'/inspections/{identifier}/vision-review',json={"request_id":uuid4().hex}).status_code == 200
    assert (vision.h.runtime.reinspections.root / "state.json").read_bytes() == before


def test_cancellation_leaves_uncertain_reservation_no_second_sdk_call(vision):
    record = vision.h.storage.get_inspection(vision.record["inspection_id"])
    raw = (vision.h.directory / "inputs" / f'{record.image_id}.png').read_bytes()
    image = validate_crop(record,raw,vision.service.policy)
    owner = vision.h.captures.authorize(vision.h.client.cookies.get(vision.h.captures.cookie_name))
    request_id = uuid4().hex
    vision.fake.error = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(vision.service.create(owner,image,raw,request_id,lambda:image))
    with pytest.raises(VisionReviewError,match="VISION_RESULT_UNCERTAIN"):
        asyncio.run(vision.service.create(owner,image,raw,request_id,lambda:image))
    assert vision.service.get(owner,image)["classification"] == "ANALYSIS_FAILED"
    assert len(vision.fake.calls) == 1


@pytest.mark.parametrize("change", [{"analysis_mode":"LIVE"},{"classification":"OK"},{"failure_code":"FAKE_FAILURE"}])
def test_persisted_result_is_revalidated_not_trusted_as_live(vision, change):
    assert post(vision).status_code == 200
    target = vision.service.files.root / "state.json"
    state = json.loads(target.read_text(encoding='utf-8'))
    state["reviews"][vision.record["inspection_id"]]["review"].update(change)
    target.write_text(json.dumps(state),encoding='utf-8')
    result = vision.h.client.get(vision.endpoint)
    assert result.status_code == 503 and result.json()["detail"]["error_code"] == "VISION_INVALID_STORED_REVIEW"
    assert len(vision.fake.calls) == 1
