"""Settings and API regression using synthetic inputs and explicit Fake providers."""

from uuid import uuid4

import pytest

import backend.main as main
from backend.config import Settings
from backend.vision_review import VisionReviewService
from tests.test_grab_inspection import harness
from tests.test_reinspection_workflow import first_warning
from tests.test_vision_review import FakeVisionClient


@pytest.mark.parametrize("enabled,key,model,expected", [
    (True, "SYNTHETIC_SETTINGS_KEY", "gemini-3.8-flash", True),
    (False, "SYNTHETIC_SETTINGS_KEY", "gemini-3.8-flash", False),
    (True, None, "gemini-3.8-flash", False),
    (True, "", "gemini-3.8-flash", False),
    (True, "   ", "gemini-3.8-flash", False),
    (True, "SYNTHETIC_SETTINGS_KEY", "unverified-model", False),
])
def test_settings_factory_fails_closed_without_constructing_transport(tmp_path, enabled, key, model, expected):
    settings = Settings(_env_file=None, VISION_REVIEW_LIVE_ENABLED=enabled, GEMINI_API_KEY=key,
                        VISION_REVIEW_MODEL=model, VISION_REVIEW_TIMEOUT_SECONDS=30)
    service = VisionReviewService.from_settings(tmp_path / "reviews", settings)
    capabilities = service.capabilities({"inspection_id": "INSP-900001"})
    assert capabilities["live_enabled"] is expected
    assert capabilities["enabled"] is expected
    assert capabilities["result_contract"] == "VISION_JUDGE_A_V1"
    assert capabilities["consent_policy"] == "PER_REQUEST_CROP_V1"
    assert service.policy.timeout_seconds == 30
    assert service.client is None
    assert not service.files.root.exists()


def test_dotenv_is_consumed_without_exporting_live_flag_to_os(tmp_path, monkeypatch):
    for name in ("VISION_REVIEW_LIVE_ENABLED", "VISION_REVIEW_MODEL", "VISION_REVIEW_TIMEOUT_SECONDS", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    environment = tmp_path / "synthetic.env"
    environment.write_text("VISION_REVIEW_LIVE_ENABLED=true\nVISION_REVIEW_MODEL=gemini-3.8-flash\n"
                           "VISION_REVIEW_TIMEOUT_SECONDS=30\nGEMINI_API_KEY=SYNTHETIC_DOTENV_KEY\n", encoding="utf-8")
    settings = Settings(_env_file=environment)
    service = VisionReviewService.from_settings(tmp_path / "reviews", settings)
    assert service.capabilities({"inspection_id": "INSP-900001"})["live_enabled"]
    assert service.policy.model == "gemini-3.8-flash"
    assert service.policy.timeout_seconds == 30
    assert service.client is None


def test_os_disable_has_priority_over_dotenv_enable(tmp_path, monkeypatch):
    environment = tmp_path / "synthetic.env"
    environment.write_text("VISION_REVIEW_LIVE_ENABLED=true\n", encoding="utf-8")
    monkeypatch.setenv("VISION_REVIEW_LIVE_ENABLED", "false")
    settings = Settings(_env_file=environment, GEMINI_API_KEY="SYNTHETIC_SETTINGS_KEY")
    assert not VisionReviewService.from_settings(tmp_path / "reviews", settings).capabilities({})["enabled"]


@pytest.fixture
def settings_api(harness, monkeypatch):
    state = dict(main.app.state._state)
    state.pop("vision_review_service", None)
    monkeypatch.setattr(main.app.state, "_state", state)
    settings = harness.client.app.state.video_runtime.settings
    monkeypatch.setattr(settings, "VISION_REVIEW_LIVE_ENABLED", True)
    monkeypatch.setattr(settings, "VISION_REVIEW_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(settings, "VISION_REVIEW_TIMEOUT_SECONDS", 30)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "SYNTHETIC_API_SETTINGS_KEY")
    for name in ("VISION_REVIEW_LIVE_ENABLED", "VISION_REVIEW_MODEL", "VISION_REVIEW_TIMEOUT_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    return harness, first_warning(harness)


def test_api_uses_runtime_settings_and_get_never_sends_image(settings_api):
    runtime, record = settings_api
    response = runtime.client.get(f'/inspections/{record["inspection_id"]}/vision-review')
    assert response.status_code == 200
    assert response.json()["capabilities"]["live_enabled"]
    assert response.json()["capabilities"]["model_requested"] == "gemini-3.8-flash"
    assert main.app.state.vision_review_service.policy.timeout_seconds == 30
    assert main.app.state.vision_review_service.client is None
    assert "SYNTHETIC_API_SETTINGS_KEY" not in response.text
    assert not main.app.state.vision_review_service.files.root.exists()


@pytest.mark.parametrize("confirmed", [False, True])
def test_configured_api_preserves_consent_idempotency_and_primary_verdict(settings_api, monkeypatch, confirmed):
    runtime, record = settings_api
    fake = FakeVisionClient()
    transports = []

    def transport(key, timeout):
        transports.append(timeout)
        return fake

    monkeypatch.setattr("backend.vision_review.GeminiVisionTransport", transport)
    endpoint = f'/inspections/{record["inspection_id"]}/vision-review'
    before = {path: path.read_bytes() for path in runtime.directory.glob("*.jsonl")}
    payload = {"request_id": uuid4().hex, "confirm_external_transmission": confirmed}
    response = runtime.client.post(endpoint, json=payload)
    if not confirmed:
        assert response.status_code == 403
        assert not transports and not fake.calls
    else:
        assert response.status_code == 200
        review = response.json()["review"]
        assert review["analysis_mode"] == "FAKE_TEST"
        assert review["analysis_status"] == "COMPLETED"
        assert transports == [30] and len(fake.calls) == 1
        assert runtime.client.post(endpoint, json=payload).json()["review"] == review
        assert runtime.client.get(endpoint).json()["review"] == review
        assert runtime.client.post(endpoint, json={**payload, "request_id": uuid4().hex}).status_code == 409
        assert len(fake.calls) == 1
    assert all(path.read_bytes() == value for path, value in before.items())
    assert runtime.storage.get_inspection(record["inspection_id"]).final_result == "REINSPECT"


def test_judge_enablement_is_independent_of_workflow_policy(tmp_path):
    for enabled in (False, True):
        settings = Settings(_env_file=None, JUDGE_ASSISTED_WORKFLOW_ENABLED=enabled,
                            VISION_REVIEW_LIVE_ENABLED=True, GEMINI_API_KEY="SYNTHETIC_SETTINGS_KEY")
        assert VisionReviewService.from_settings(tmp_path / str(enabled), settings).capabilities({})["live_enabled"]
