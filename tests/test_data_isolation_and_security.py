"""
VisionInsight - Day 3.5 Prompt 8
데이터 격리, 보안 점검 및 Git/Docker 규칙 검증 테스트
"""

import json
import hashlib
import os
import re
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import get_settings
from backend.inspection import ImageRegistry
from backend.storage import JsonlInspectionStorage, get_inspection_storage


@pytest.fixture
def client():
    return TestClient(app)


def test_api_response_does_not_contain_absolute_paths(client):
    r"""POST /inspections 응답에 서버 내부 절대 경로(C:\, C:/, /app/)가 노출되지 않는지 검증."""
    resp = client.post("/inspections", json={"product_id": "SEC-TEST-001", "image_id": "IMG-BOTTLE-0001"})
    assert resp.status_code == 201
    resp_text = resp.text

    # Check for Windows or Linux absolute paths
    assert "C:\\" not in resp_text
    assert "C:/" not in resp_text
    assert "/app/" not in resp_text
    assert "/dataset/" not in resp_text
    assert "\\dataset\\" not in resp_text


def test_api_response_does_not_contain_ground_truth_classes(client):
    """API 응답에 결함 정답 클래스명(broken_large, contamination 등)이 노출되지 않는지 검증."""
    resp = client.post("/inspections", json={"product_id": "SEC-TEST-002", "image_id": "IMG-BOTTLE-0001"})
    assert resp.status_code == 201
    resp_text = resp.text.lower()

    prohibited_labels = ["broken_large", "broken_small", "contamination", "ground_truth"]
    for label in prohibited_labels:
        assert label not in resp_text, f"Prohibited label '{label}' found in API response!"


def test_list_images_does_not_leak_classes_or_paths(client):
    """GET /inspections/images 응답이 중립 ID 목록만 반환하고 원본 경로나 라벨을 누출하지 않는지 검증."""
    resp = client.get("/inspections/images")
    assert resp.status_code == 200
    data = resp.json()

    assert "image_ids" in data
    resp_text = json.dumps(data).lower()
    prohibited_markers = [":\\", ":/", "broken_large", "broken_small", "contamination", "ground_truth"]
    for marker in prohibited_markers:
        assert marker not in resp_text, f"Prohibited marker '{marker}' found in image listing!"


def test_path_traversal_attempts_are_blocked_and_sanitized(client):
    """경로 조작(Path Traversal) 공격 시도가 안전하게 차단되고 내부 정보가 노출되지 않는지 검증."""
    malicious_ids = [
        "../../../etc/passwd",
        "..\\..\\Windows\\System32\\cmd.exe",
        "C:\\dataset\\bottle\\train\\good\\000.png",
        "/etc/shadow",
    ]

    for mal_id in malicious_ids:
        resp = client.post("/inspections", json={"product_id": "ATTACK-TEST", "image_id": mal_id})
        assert resp.status_code in (400, 404, 422)
        resp_text = resp.text
        # Ensure raw traceback or internal server root is not exposed
        assert "Traceback" not in resp_text
        assert "C:\\Users" not in resp_text


def test_t06_defect_unhandled_score_preserved_without_hardcoding(client):
    """T06 결함 미검출 사례(점수 32.2679, 임계값 34.1442)가 인위적 조작 없이 그대로 유지되는지 검증."""
    resp = client.post("/inspections", json={"product_id": "PROD-BOTTLE-T06", "image_id": "IMG-BOTTLE-0001"})
    assert resp.status_code == 201
    data = resp.json()

    # T06은 현재 모델에서 미검출되어 result=OK, final_result=OK로 산출되는 한계 사례임
    assert data["result"] == "OK"
    assert data["final_result"] == "OK"
    assert data["decision_threshold"] == 34.1442
    assert abs(data["anomaly_score"] - 32.2679) < 0.5


def test_gitignore_and_dockerignore_rules():
    """.gitignore와 .dockerignore에 민감 데이터셋 및 평가 정답 제외 규칙이 포함되어 있는지 검증."""
    project_root = Path(__file__).resolve().parent.parent

    gitignore_path = project_root / ".gitignore"
    assert gitignore_path.exists()
    gi_content = gitignore_path.read_text(encoding="utf-8")
    assert ".env" in gi_content
    assert "dataset/**" in gi_content or "dataset/" in gi_content
    assert "models/**/*.ckpt" in gi_content
    assert "evaluation_private/" in gi_content
    assert "ground_truth/" in gi_content

    dockerignore_path = project_root / ".dockerignore"
    assert dockerignore_path.exists()
    di_content = dockerignore_path.read_text(encoding="utf-8")
    assert ".env" in di_content
    assert "dataset/" in di_content
    assert "data/splits/" in di_content
    assert "tests/" in di_content
    assert "evaluation_private/" in di_content
    assert "ground_truth/" in di_content


@pytest.fixture
def isolated_t03_input(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "test_data/injected_images/IMG-BOTTLE-INJ-0001.png"
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    target = tmp_path / source.name
    shutil.copyfile(source, target)
    assert target.resolve() != source.resolve()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == original_hash
    registry = ImageRegistry()
    registry.register_image("IMG-BOTTLE-INJ-0001", target)
    storage = JsonlInspectionStorage(tmp_path / "inspections.jsonl", tmp_path / "logs.jsonl")
    monkeypatch.setattr("backend.main.get_image_registry", lambda settings: registry)
    monkeypatch.setattr("backend.main.get_inspection_storage", lambda: storage)
    try:
        yield target
    finally:
        assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash


def test_t03_synthetic_injection_parameters_not_leaked(client, isolated_t03_input):
    """T03 조도 저하 검사 응답에 합성 주입 사실이나 0.6x 등의 조작 배율이 노출되지 않는지 검증."""
    resp = client.post("/inspections", json={"product_id": "PROD-BOTTLE-T03", "image_id": "IMG-BOTTLE-INJ-0001"})
    assert resp.status_code == 201
    data = resp.json()

    # 영상 품질 경고와 REINSPECT는 정상 산출
    assert data["image_quality_status"] == "WARNING_LOW_BRIGHTNESS"
    assert data["final_result"] == "REINSPECT"

    # 합성 주입 관련 내부 메타데이터가 노출되지 않아야 함
    resp_text = resp.text.lower()
    prohibited_injection_words = ["synthetic", "injection_factor", "0.6x", "fault_factor"]
    for word in prohibited_injection_words:
        assert word not in resp_text, f"Internal injection parameter '{word}' leaked in API response!"

