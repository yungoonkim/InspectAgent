"""Judge A contract using synthetic PNGs and isolated stores, never operational results."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.capture_store import CaptureError, CaptureStore
from backend.grab_inspection import GrabInspectionError
from backend.reinspection_store import ReinspectionError
from backend.vision_review import INSTRUCTION, VisionJudgeDraft
from tests.test_grab_inspection import harness
from tests.test_vision_review import vision, post


@pytest.mark.parametrize("verdict", ["OK", "NG", "REINSPECT"])
def test_reference_inspection_identifier_isolated_fake_contract(vision, monkeypatch, verdict):
    identifier = "INSP-001669"
    original = vision.h.storage.get_inspection
    record = original(vision.record["inspection_id"]).model_copy(deep=True)
    record.inspection_id = identifier
    monkeypatch.setattr(vision.h.storage, "get_inspection", lambda value: record if value == identifier else original(value))
    vision.endpoint = f"/inspections/{identifier}/vision-review"
    draft = json.loads(vision.fake.text)
    draft.update(judge_verdict=verdict, defect_locations=["MOCK TEST: upper rim"] if verdict == "NG" else [])
    vision.fake.text = json.dumps(draft)
    paths = [*vision.h.directory.glob("*.jsonl"), vision.h.runtime.reinspections.root / "state.json"]
    before = {path: path.read_bytes() for path in paths}
    response = post(vision)
    assert response.status_code == 200, response.text
    review = response.json()["review"]
    assert review["inspection_id"] == identifier and review["image_id"] == record.image_id
    assert review["analysis_status"] == "COMPLETED" and review["judge_verdict"] == verdict
    assert review["analysis_mode"] == "FAKE_TEST" and record.final_result == "REINSPECT"
    assert response.json()["capabilities"]["result_contract"] == "VISION_JUDGE_A_V1"
    assert vision.h.client.get(vision.endpoint).json()["review"] == review
    assert all(path.read_bytes() == content for path, content in before.items())


@pytest.mark.parametrize("verdict", ["OK", "NG", "REINSPECT"])
@pytest.mark.parametrize("language", ["ko", "en"])
def test_korean_generation_and_existing_english_judge_remain_compatible(vision, verdict, language):
    korean = {
        "visible_observations": ["MOCK TEST: 입구 테두리에 밝은 반사가 관찰됩니다."],
        "defect_locations": ["MOCK TEST: 이미지 위쪽 입구 테두리"],
        "judge_rationale": "MOCK TEST: 관찰 의견이며 실제 결함 확정이나 정상 보증이 아닙니다.",
        "limitations": ["MOCK TEST: 합성 테스트이므로 실제 제품 상태를 확인할 수 없습니다."],
        "recommended_operator_action": "MOCK TEST: 작업자가 원본 이미지와 제품을 확인하세요.",
    }
    draft = json.loads(vision.fake.text)
    if language == "ko":
        draft.update(korean)
    else:
        draft["defect_locations"] = ["MOCK TEST: upper rim"]
    draft["judge_verdict"] = verdict
    if verdict != "NG":
        draft["defect_locations"] = []
    vision.fake.text = json.dumps(draft, ensure_ascii=False)
    protected = [*vision.h.directory.glob("*.jsonl"), vision.h.runtime.reinspections.root / "state.json"]
    before = {path: path.read_bytes() for path in protected}
    request_id = uuid4().hex
    result = post(vision, request_id)
    assert result.status_code == 200, result.text
    saved = result.json()["review"]
    assert saved["analysis_status"] == "COMPLETED" and saved["analysis_mode"] == "FAKE_TEST"
    for name, value in draft.items():
        if name == "limitations":
            assert saved[name][:-1] == value
        else:
            assert saved[name] == value
    instruction = vision.fake.calls[0]["contents"][0]["parts"][0]["text"]
    assert instruction == INSTRUCTION and "Write all natural-language explanations in Korean" in instruction
    assert all(name in instruction for name in korean)
    assert "Keep JSON field names" in instruction and "OK, NG, REINSPECT unchanged" in instruction
    path = vision.service.files.root / "state.json"
    stored_before = path.read_bytes()
    assert vision.h.client.get(vision.endpoint).json()["review"] == saved
    assert post(vision, request_id).json()["review"] == saved
    assert path.read_bytes() == stored_before and len(vision.fake.calls) == 1
    assert all(path.read_bytes() == content for path, content in before.items())
    assert vision.h.storage.get_inspection(vision.record["inspection_id"]).final_result == "REINSPECT"


@pytest.mark.parametrize("change", [
    {"judge_verdict": "UNKNOWN"}, {"judge_verdict": "NG", "defect_locations": []},
    {"judge_verdict": "OK", "visible_observations": []}, {"judge_rationale": " "},
    {"limitations": []}, {"visible_observations": [" "]}, {"analysis_status": "COMPLETED"},
    {"final_result": "OK"}, {"confidence": 0.99},
])
def test_invalid_judge_evidence_has_no_verdict(vision, change):
    draft = {**json.loads(vision.fake.text), **change}
    with pytest.raises(ValidationError):
        VisionJudgeDraft.model_validate(draft, strict=True)
    vision.fake.text = json.dumps(draft)
    response = post(vision).json()["review"]
    assert response["analysis_status"] == "ANALYSIS_FAILED"
    assert response["judge_verdict"] is None and response["visible_observations"] == []
    assert response["failure_code"] == "VISION_INVALID_RESPONSE"
    assert len(vision.fake.calls) == 1


@pytest.mark.parametrize("classification", ["DEFECT_SUSPECTED", "QUALITY_ISSUE", "NO_VISIBLE_DEFECT", "INCONCLUSIVE", "ANALYSIS_FAILED"])
def test_legacy_review_is_read_unchanged_never_converted_or_reanalysed(vision, classification):
    request_id = uuid4().hex
    assert post(vision, request_id).status_code == 200
    path = vision.service.files.root / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    entry = state["reviews"][vision.record["inspection_id"]]
    review = entry["review"]
    for name in ("image_id", "judge_verdict", "judge_rationale", "defect_locations", "analysis_status"):
        review.pop(name)
    review.update(prompt_version="bottle-independent-vision-v1", classification=classification,
                  failure_code="VISION_TIMEOUT" if classification == "ANALYSIS_FAILED" else None)
    if classification == "ANALYSIS_FAILED":
        review["visible_observations"] = []
    path.write_text(json.dumps(state), encoding="utf-8")
    before = path.read_bytes()
    restored = vision.h.client.get(vision.endpoint)
    assert restored.status_code == 200, restored.text
    assert restored.json()["review"] == review
    assert "judge_verdict" not in restored.json()["review"]
    assert post(vision, request_id).json()["review"] == review
    assert post(vision).status_code == 409
    assert path.read_bytes() == before and len(vision.fake.calls) == 1


@pytest.mark.parametrize("change", [
    {"analysis_status": "ANALYSIS_FAILED", "judge_verdict": "OK"},
    {"analysis_status": "COMPLETED", "judge_verdict": None},
    {"image_id": "IMG-GRAB-" + "0" * 32},
])
def test_stored_judge_status_and_image_identity_are_rechecked(vision, change):
    assert post(vision).status_code == 200
    path = vision.service.files.root / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["reviews"][vision.record["inspection_id"]]["review"].update(change)
    path.write_text(json.dumps(state), encoding="utf-8")
    result = vision.h.client.get(vision.endpoint)
    assert result.status_code in {409, 503}
    assert len(vision.fake.calls) == 1


def test_restart_loses_session_but_preserves_durable_crop_and_group_ownership(vision):
    record = vision.h.storage.get_inspection(vision.record["inspection_id"])
    cookie = vision.h.client.cookies.get(CaptureStore.cookie_name)
    csrf = vision.h.client.headers["X-Capture-CSRF"]
    image_path = vision.h.directory / "inputs" / f"{record.image_id}.png"
    group_path = vision.h.runtime.reinspections.root / "state.json"
    before = {path: path.read_bytes() for path in (image_path, group_path)}
    restarted = CaptureStore(vision.h.directory / "fresh-session-store", clock=lambda: vision.h.clock[0])
    with pytest.raises(CaptureError) as read_error:
        restarted.authorize(cookie)
    assert read_error.value.status_code == 404
    with pytest.raises(CaptureError) as write_error:
        restarted.authorize(cookie, csrf, write=True)
    assert write_error.value.status_code == 401
    new_cookie, _ = restarted.bootstrap(cookie)
    new_owner = restarted.authorize(new_cookie)
    with pytest.raises(GrabInspectionError, match="GRAB_INPUT_NOT_FOUND"):
        vision.h.runtime.authorize_record(record, new_owner)
    with pytest.raises(ReinspectionError, match="REINSPECTION_GROUP_NOT_FOUND"):
        vision.h.runtime.reinspections.get(record.metrics["reinspection"]["group_id"], new_owner)
    assert all(path.read_bytes() == content for path, content in before.items())
    assert not vision.fake.calls
