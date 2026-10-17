import ipaddress
import os
from pathlib import Path
import socket
import sys


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/outputs/roi-db-validation" / sys.argv[1]
if OUTPUT.exists():
    raise SystemExit("Existing test evidence preserved; use a new run name")
OUTPUT.mkdir(parents=True)
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
for key, relative in {
    "OUTPUT_DIR": "outputs", "LOG_DIR": "logs", "TEST_DATA_DIR": "test_data",
    "INSPECTIONS_FILE": "inspections.jsonl", "INSPECTION_LOGS_FILE": "inspection_logs.jsonl",
    "CAPTURE_DIR": "captures",
}.items():
    os.environ[key] = str(OUTPUT / relative)
os.environ["GEMINI_API_KEY"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["AGENT_FINAL_MODEL_TIMEOUT_SECONDS"] = "15"
private = str((ROOT.parent / "evaluation_private").absolute()).lower()
protected = set()
for relative in ("backend", "tests", "docs", "scripts", "models", "presentation",
                 "test_data/manual_validation", ".tmp_measurement_regressions", "data/outputs/videos"):
    directory = ROOT / relative
    if directory.is_dir():
        protected.update(str(path.absolute()).lower() for path in directory.rglob("*") if path.is_file())
protected.update(str(path.absolute()).lower() for path in (ROOT / "data").glob("*.jsonl"))


def filesystem_guard(event, arguments):
    if event not in ("open", "os.listdir", "os.scandir") or not arguments or not isinstance(arguments[0], (str, bytes, os.PathLike)):
        return
    path = str(Path(os.fsdecode(arguments[0])).absolute()).lower()
    if path == private or path.startswith(private + os.sep) or (str(ROOT / "dataset").lower() in path and "ground_truth" in Path(path).parts):
        raise AssertionError("Private evaluation access forbidden")
    if event == "open" and path in protected:
        mode, flags = arguments[1:3]
        if (isinstance(mode, str) and any(character in mode for character in "wax+")) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)):
            raise AssertionError("Protected asset write forbidden")


sys.addaudithook(filesystem_guard)
original_connect = socket.socket.connect


def local_connect(connection, address):
    if isinstance(address, tuple):
        try:
            permitted = ipaddress.ip_address(address[0]).is_loopback
        except ValueError:
            permitted = address[0] == "localhost"
        if not permitted:
            raise AssertionError("External network forbidden")
    return original_connect(connection, address)


socket.socket.connect = local_connect
import httpx
import pytest


def reject_http(*arguments, **keywords):
    raise AssertionError("Use ASGI/MockTransport; real HTTP is forbidden")


async def reject_async_http(*arguments, **keywords):
    reject_http()


httpx.HTTPTransport.handle_request = reject_http
httpx.AsyncHTTPTransport.handle_async_request = reject_async_http
from backend.ml.patchcore_inferencer import PatchCoreInferencer


def no_model_load(*arguments, **keywords):
    pytest.skip("B-1-DB policy: real PatchCore loading/inference excluded; normalization issue UNRESOLVED")


def no_real_prediction(*arguments, **keywords):
    raise AssertionError("Actual PatchCore prediction forbidden")


PatchCoreInferencer._load_model = no_model_load
PatchCoreInferencer.predict = no_real_prediction
raise SystemExit(pytest.main(sys.argv[2:] + ["-p", "no:cacheprovider", "--basetemp", str(OUTPUT / "pytest"),
                                            "--junitxml", str(OUTPUT / "results.xml")]))
