"""A-3-2 isolated activation gates; does not start or contact a server."""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

SELECTION = [
    "tests/test_quality_shadow_activation_readiness.py",
    "tests/test_quality_shadow_integration.py::test_default_off_preserves_existing_gemini_settings_and_pipeline",
    "tests/test_quality_shadow_integration.py::test_shadow_is_after_log_and_rig_commit_without_response_or_record_changes",
    "tests/test_quality_shadow_integration.py::test_background_compute_and_write_failure_preserve_committed_records",
    "tests/test_quality_shadow_integration.py::test_lifespan_only_starts_worker_when_enabled_and_closes_it",
    "tests/test_quality_shadow_worker.py::test_off_starts_no_thread_and_creates_no_sidecar_root",
    "tests/test_quality_shadow_worker.py::test_one_active_one_pending_third_rejected_duplicate_rejected",
    "tests/test_quality_shadow_worker.py::test_existing_result_is_reused_without_recalculation",
    "tests/test_quality_shadow_store.py::test_publication_is_immutable_idempotent_and_fully_validated",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    if (ROOT / "data/outputs/quality-shadow-validation").resolve() not in output.parents:
        raise ValueError("ISOLATED_OUTPUT_REQUIRED")
    output.mkdir(parents=True, exist_ok=False)
    with (output / "selection.json").open("x", encoding="utf-8") as stream:
        json.dump(SELECTION, stream, indent=2)
    os.environ.update({"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "QUALITY_SHADOW_ENABLED": "false", "VISION_REVIEW_LIVE_ENABLED": "false"})
    from scripts.safe_regression_backend import run_tests

    return run_tests(output, SELECTION)


if __name__ == "__main__":
    raise SystemExit(main())
