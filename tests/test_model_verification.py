"""
VisionInsight - Day 3.5 Prompt 7
모델 및 임계값 버전 검증 단위 테스트
"""

import pytest
from pathlib import Path
from backend.ml.patchcore_inferencer import PatchCoreInferencer


def test_model_compatibility_verification_success():
    """정상 모델 체크포인트, 메타데이터, 공식 임계값(34.1442)이 일치할 때 검증 성공 확인."""
    ckpt_path = Path("models/patchcore/patchcore_bottle.ckpt")
    meta_path = Path("models/patchcore/model_metadata.json")

    inferencer = PatchCoreInferencer(checkpoint_path=ckpt_path, metadata_path=meta_path, device="cpu")
    res = inferencer.verify_compatibility(expected_threshold=34.1442)

    assert res["verified"] is True
    assert res["memory_bank_matched"] is True
    assert res["threshold_matched"] is True
    assert res["checkpoint_sha256"] == "4b239d28e72c63bf782cd1d31981d7f4362c591e7c23164e4c0ac8b5e99b52a3"
    assert len(res["reasons"]) == 0


def test_model_compatibility_verification_threshold_mismatch():
    """임계값이 메타데이터와 불일치할 때 verified=False 반환 및 사유 기록 확인."""
    ckpt_path = Path("models/patchcore/patchcore_bottle.ckpt")
    meta_path = Path("models/patchcore/model_metadata.json")

    inferencer = PatchCoreInferencer(checkpoint_path=ckpt_path, metadata_path=meta_path, device="cpu")
    # 고의로 잘못된 임계값(99.999) 전달
    res = inferencer.verify_compatibility(expected_threshold=99.999)

    assert res["verified"] is False
    assert res["threshold_matched"] is False
    assert any("Threshold mismatch" in r for r in res["reasons"])
