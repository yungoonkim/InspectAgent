import json
import math

import numpy as np
import pytest

from scripts.experiments.compare_patchcore_synthetic_ab import (
    FORWARD_LIMIT,
    THRESHOLD,
    compare_scores,
    synthetic_inputs,
    threshold_side,
)


def test_synthetic_generation_is_exact_and_repeatable():
    initial = synthetic_inputs()
    repeated = synthetic_inputs()
    assert list(initial) == ["SYN-001", "SYN-002", "SYN-003"]
    for input_id, image in initial.items():
        assert image.shape == (256, 256, 3)
        assert image.dtype == np.uint8
        assert np.array_equal(image, repeated[input_id])
    assert np.all(initial["SYN-001"] == 128)
    assert np.array_equal(initial["SYN-002"][0, :, 0], np.arange(256, dtype=np.uint8))
    assert np.array_equal(initial["SYN-003"][:, :, 0], initial["SYN-003"][:, :, 1].T)
    assert set(np.unique(initial["SYN-003"][:, :, 2])) == {0, 255}


def test_synthetic_arrays_are_independent():
    initial = synthetic_inputs()
    initial["SYN-001"][:] = 0
    assert np.all(synthetic_inputs()["SYN-001"] == 128)
    assert initial["SYN-002"][0, 255, 0] == 255


@pytest.mark.parametrize("score, expected", [(THRESHOLD, "AT_OR_BELOW"), (THRESHOLD + 0.001, "ABOVE")])
def test_threshold_is_mathematical_only(score, expected):
    assert threshold_side(score) == expected


@pytest.mark.parametrize("score", [math.nan, math.inf, -math.inf])
def test_nonfinite_score_rejected(score):
    with pytest.raises(RuntimeError, match="NONFINITE_SCORE"):
        threshold_side(score)


def test_score_comparison_and_json_schema():
    result = compare_scores("SYN-001", 40.0, 20.0)
    assert result == {
        "input_id": "SYN-001", "a_score": 40.0, "b_score": 20.0,
        "absolute_difference": 20.0, "relative_difference_abs_over_abs_a": 0.5,
        "a_threshold_side": "ABOVE", "b_threshold_side": "AT_OR_BELOW", "threshold_crossing": True,
    }
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert not any(key in result for key in ("inspection_id", "final_result", "image_path"))
    assert FORWARD_LIMIT == 12


def test_zero_baseline_relative_difference_is_undefined():
    assert compare_scores("SYN-002", 0.0, 1.0)["relative_difference_abs_over_abs_a"] is None
