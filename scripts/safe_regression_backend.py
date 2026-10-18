"""Offline test harness and read-only operational asset fingerprints."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import sys
import tempfile
import traceback


ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    "tests/test_inspection_anomaly_map.py", "tests/test_anomaly_map_regression.py",
    "tests/test_inspection_image_file.py", "tests/test_inspections.py", "tests/test_storage.py",
    "tests/test_agent_tools.py", "tests/test_agent_service.py", "tests/test_agent_day5_counterexamples.py",
    "tests/test_agent_reporting_integration.py", "tests/test_day7_step2_agent_offline_mock.py",
    "tests/test_agent_day7_error_observability.py",
    "tests/test_day7_step5_agent_e2e.py", "tests/test_agent_api.py",
    "tests/test_day7_step6b_runtime_safety.py",
    "tests/test_grab_inspection.py",
    "tests/test_reinspection_workflow.py",
    "tests/test_vision_review.py",
]


def protected_snapshot():
    paths = [ROOT / ".env", ROOT / "backend/ml/patchcore_inferencer.py", ROOT / "backend/decision.py"]
    paths.extend((ROOT / "data").glob("*.jsonl"))
    for relative in ("models/patchcore", "data/outputs/inspection_anomaly_maps", "data/outputs/agent_reports",
                     "data/outputs/captures", "data/outputs/grab_inspection_inputs",
                     "data/outputs/reinspection_history", "data/outputs/vision_reviews", "data/logs", "data/outputs/videos"):
        directory = ROOT / relative
        if directory.is_dir():
            paths.extend(path for path in directory.rglob("*") if path.is_file())
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(paths)) if path.is_file()}


def run_tests(output, selected):
    for key, relative in {
        "OUTPUT_DIR": "output", "LOG_DIR": "logs", "TEST_DATA_DIR": "test_data", "DATASET_PATH": "images",
        "INSPECTIONS_FILE": "inspections.jsonl", "INSPECTION_LOGS_FILE": "inspection_logs.jsonl",
        "CAPTURE_DIR": "captures", "ANOMALY_MAP_DIR": "maps", "VIDEO_ROOT": "videos",
        "PATCHCORE_CHECKPOINT_PATH": "stub/unloadable.ckpt", "PATCHCORE_METADATA_PATH": "stub/metadata.json",
    }.items():
        os.environ[key] = str(output / relative)
    for key in ("TEMP", "TMP", "TMPDIR", "MPLCONFIGDIR"):
        os.environ[key] = str(output / "temporary")
    (output / "temporary").mkdir(exist_ok=True)
    tempfile.tempdir = str(output / "temporary")
    (output / "stub").mkdir(exist_ok=True)
    (output / "stub/unloadable.ckpt").write_bytes(b"not a model; loading is forbidden")
    (output / "stub/metadata.json").write_text("{}", encoding="utf-8")
    os.environ.update({"GEMINI_API_KEY": "", "VISIONINSIGHT_DATABASE_URL": "", "VISIONINSIGHT_TEST_DATABASE_URL": "",
                       "VISIONINSIGHT_ROI_ADMIN_TOKEN": "", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                       "PYTHONDONTWRITEBYTECODE": "1", "AGENT_FINAL_MODEL_TIMEOUT_SECONDS": "15"})
    reports = output / "data/outputs/agent_reports"
    reports.mkdir(parents=True, exist_ok=True)
    for identifier in ("INSP-001396", "INSP-001398"):
        (reports / f"{identifier}.json").write_text(json.dumps({
            "inspection_id": identifier, "analysis_status": "COMPLETED",
            "provenance": "RECORDED_TEST_FIXTURE", "overall_summary": "Synthetic offline report fixture",
            "observed_facts": [], "recommended_checks": [], "limitations": ["SYNTHETIC_TEST_ONLY"],
        }), encoding="utf-8")
    platform.uname()
    sys.dont_write_bytecode = True
    forbidden = [ROOT / "dataset", ROOT / "test_data", ROOT / "models", ROOT.parent / "evaluation_private"]
    counters = {"forbidden_io": 0, "network": 0, "real_prediction": 0, "real_load": 0}
    blocked_events = []
    warning_categories = []

    def record_io(event, path):
        counters["forbidden_io"] += 1
        blocked_events.append({"event": event, "target": str(path.relative_to(ROOT)) if ROOT in path.parents else path.name,
                               "frames": [f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
                                          for frame in traceback.extract_stack()[-7:-1]]})

    def audit(event, arguments):
        if event in ("open", "os.listdir", "os.scandir") and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(arguments[0])).resolve()
            if (any(path == directory or directory in path.parents for directory in forbidden)
                    or path == ROOT / ".env" or (event == "open" and path.suffix == ".ckpt")):
                record_io(event, path)
                raise AssertionError("Operational data/model/private access forbidden")
            if event == "open":
                mode, flags = arguments[1:3]
                writing = isinstance(mode, str) and any(character in mode for character in "wax+")
                writing |= isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
                if writing and path != output and output not in path.parents:
                    record_io(event, path)
                    raise AssertionError("Test writes must stay in the unique run directory")
        if event in ("os.remove", "os.rmdir", "os.mkdir", "os.rename", "os.link", "os.symlink", "os.chmod", "shutil.rmtree"):
            values = arguments[:2] if event in ("os.rename", "os.link", "os.symlink") else arguments[:1]
            for value in values:
                if isinstance(value, (str, bytes, os.PathLike)):
                    path = Path(os.fsdecode(value)).resolve()
                    if path != output and output not in path.parents:
                        record_io(event, path)
                        raise AssertionError("Test mutation outside run directory forbidden")

    def no_connect(*arguments, **keywords):
        if any(frame.name in ("socketpair", "_fallback_socketpair") and Path(frame.filename).name == "socket.py"
               for frame in traceback.extract_stack()):
            return original_connect(*arguments, **keywords)
        counters["network"] += 1
        raise AssertionError("Network/DB connection forbidden; use ASGI or MockTransport")

    original_connect = socket.socket.connect
    sys.addaudithook(audit)
    socket.socket.connect = no_connect
    socket.socket.connect_ex = no_connect
    import httpx
    import pytest
    from backend.config import Settings, get_settings
    Settings.model_config["env_file"] = None
    get_settings.cache_clear()
    from backend.ml.patchcore_inferencer import PatchCoreInferencer

    def no_load(*arguments, **keywords):
        pytest.skip("SAFE_REGRESSION: real checkpoint loading/inference is excluded")

    def no_prediction(*arguments, **keywords):
        counters["real_prediction"] += 1
        raise AssertionError("Actual PatchCore prediction forbidden")

    def no_http(*arguments, **keywords):
        counters["network"] += 1
        raise AssertionError("Real HTTP transport forbidden")

    async def no_async_http(*arguments, **keywords):
        no_http()

    PatchCoreInferencer._load_model = no_load
    PatchCoreInferencer.predict = no_prediction
    httpx.HTTPTransport.handle_request = no_http
    httpx.AsyncHTTPTransport.handle_async_request = no_async_http
    from google import genai
    genai.Client = no_http

    class Isolation:
        def pytest_warning_recorded(self, warning_message, when, nodeid, location):
            warning_categories.append(warning_message.category.__name__)

        @pytest.fixture(autouse=True)
        def api_files(self, request, monkeypatch, tmp_path):
            names = {"test_inspections.py"}
            if request.node.path.name not in names:
                return
            import cv2
            import numpy as np
            import backend.inspection as inspection
            import backend.main as main
            import backend.storage as storage_module
            import backend.anomaly_map_store as maps
            image = np.random.default_rng(42).integers(32, 224, (900, 900, 3), dtype=np.uint8)
            api_directory = output / "api" / hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:16]
            api_directory.mkdir(parents=True, exist_ok=True)
            image_path = api_directory / "synthetic.png"
            assert cv2.imwrite(str(image_path), image)
            registry = inspection.ImageRegistry()
            registry.register_image("IMG-BOTTLE-0001", image_path)
            registry.register_image("IMG-BOTTLE-NONEXISTENT", api_directory / "missing.png")
            storage = storage_module.JsonlInspectionStorage(api_directory / "inspections.jsonl", api_directory / "logs.jsonl")
            monkeypatch.setattr(get_settings(), "DATASET_PATH", str(api_directory))
            monkeypatch.setattr(inspection, "_image_registry", registry)
            monkeypatch.setattr(inspection, "_id_generator", inspection.InspectionIdGenerator())
            monkeypatch.setattr(storage_module, "_storage_instance", storage)
            monkeypatch.setattr(main, "get_inspection_storage", lambda: storage)
            monkeypatch.setattr(maps, "get_anomaly_map_dir", lambda: api_directory / "maps")

    selection = [str(ROOT / name) for name in (selected or TESTS)]
    os.chdir(output)
    exit_code = pytest.main(selection + ["-q", "-rs", "--tb=short", "-p", "no:cacheprovider",
                                         "--log-file", str(output / "pytest.log"),
                                         "--basetemp", str(output / "pytest"), "--junitxml", str(output / "backend.xml")],
                            plugins=[Isolation()])
    (output / "safety.json").write_text(json.dumps({**counters, "blocked_events": blocked_events,
        "warnings": len(warning_categories), "warning_categories": warning_categories,
        "real_gemini_api_calls": 0}, indent=2), encoding="utf-8")
    if any(counters.values()):
        return 1
    return int(exit_code)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("snapshot", "verify", "backend"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("tests", nargs="*")
    arguments = parser.parse_intermixed_args()
    output = arguments.output.resolve()
    run_root = (ROOT / "data/outputs/safe-regression").resolve()
    if run_root not in output.parents:
        raise SystemExit("Use a unique directory under data/outputs/safe-regression")
    output.mkdir(parents=True, exist_ok=True)
    if arguments.mode == "snapshot":
        target = output / "protected-before.json"
        if target.exists():
            raise SystemExit("Existing run evidence must not be overwritten")
        target.write_text(json.dumps(protected_snapshot(), indent=2), encoding="utf-8")
        return 0
    if arguments.mode == "verify":
        before = json.loads((output / "protected-before.json").read_text(encoding="utf-8"))
        unchanged = before == protected_snapshot()
        (output / "protection.json").write_text(json.dumps({"unchanged": unchanged, "files": len(before)}), encoding="utf-8")
        print("Operational assets:", "PASS" if unchanged else "FAIL")
        return 0 if unchanged else 1
    return run_tests(output, arguments.tests)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
