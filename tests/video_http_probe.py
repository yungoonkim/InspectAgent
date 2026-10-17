import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    arguments = parser.parse_args()
    root = arguments.evidence_dir
    for name, relative in {"OUTPUT_DIR": "outputs", "LOG_DIR": "logs", "TEST_DATA_DIR": "test_data",
                           "INSPECTIONS_FILE": "inspections.jsonl", "INSPECTION_LOGS_FILE": "logs.jsonl",
                           "CAPTURE_DIR": "captures"}.items():
        os.environ[name] = str(root / relative)
    os.environ["ENABLE_PATCHCORE"] = "false"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.main import app
    from backend.config import PROJECT_ROOT
    from backend.video_source import DEMO_VIDEO
    from fastapi.responses import HTMLResponse
    import uvicorn

    requests = []

    @app.middleware("http")
    async def record_http(request, call_next):
        response = await call_next(request)
        requests.append({"method": request.method, "path": request.url.path,
                         "range": request.headers.get("range"), "status": response.status_code,
                         "content_range": response.headers.get("content-range"),
                         "content_type": response.headers.get("content-type")})
        return response

    @app.get("/__video_probe", include_in_schema=False)
    def probe_page():
        return HTMLResponse('''<!doctype html><title>FastAPI video endpoint verification</title>
        <video id="clip" controls muted preload="auto" width="960"></video>
        <script>
          window.videoEvents=[];
          const video=document.getElementById('clip');
          for(const eventName of ['loadedmetadata','loadeddata','playing','pause','seeking','seeked','ended','error']) {
            video.addEventListener(eventName,()=>window.videoEvents.push({event:eventName,currentTime:video.currentTime,
              clock:performance.now(),error:video.error?{code:video.error.code,message:video.error.message}:null}));
          }
          video.src='/videos/VID-000001/stream';
        </script>''')

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    result = None
    try:
        with patch("google.genai.Client", side_effect=AssertionError("Live Gemini forbidden")):
            thread.start()
            for _attempt in range(100):
                if server.started:
                    break
                if not thread.is_alive():
                    raise RuntimeError("Isolated API server failed to start")
                time.sleep(0.1)
            if not server.started:
                raise RuntimeError("Isolated API server startup timeout")
            result = subprocess.run([
                "C:/Program Files/nodejs/node.exe", str(PROJECT_ROOT / "scripts/verify_conveyor_browser.mjs"),
                str(PROJECT_ROOT / "data/outputs/videos" / DEMO_VIDEO.relative_path),
                "C:/Program Files/Google/Chrome/Application/chrome.exe", str(root),
                f"http://127.0.0.1:{port}/videos/VID-000001/stream", f"http://127.0.0.1:{port}/__video_probe",
            ], capture_output=True, text=True, encoding="utf8", errors="replace", timeout=90,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            with (root / "browser_runner.json").open("x", encoding="utf8") as output:
                json.dump({"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}, output, indent=2)
    finally:
        server.should_exit = True
        if thread.ident:
            thread.join(10)
        listener.close()
        with (root / "api_http.json").open("x", encoding="utf8") as output:
            json.dump({"requests": requests, "server_stopped": not thread.is_alive()}, output, indent=2)
    if result is None or result.returncode:
        raise RuntimeError("Browser runner did not complete")
    summary = json.loads((root / "browser_validation.json").read_text())
    print(json.dumps({"status": summary["status"], "browser": summary.get("browserVersion"),
                      "checks": summary["checks"], "browser_http": summary["browserHttp"],
                      "api_http": requests, "server_stopped": not thread.is_alive()}, indent=2))
    if summary["status"] != "BROWSER_PASS" or thread.is_alive():
        raise RuntimeError("Real API browser verification failed")


if __name__ == "__main__":
    main()
