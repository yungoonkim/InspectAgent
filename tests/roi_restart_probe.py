import argparse
import json
from pathlib import Path
import uuid

from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from backend.db import ROOT, RoiSettings, database_engine
from backend.roi_api import RoiRuntime, create_roi_app
from backend.video_source import DEMO_VIDEO


def probe(action, path):
    url = dotenv_values(ROOT / ".env.roi-db.local")["VISIONINSIGHT_TEST_DATABASE_URL"]
    parsed = make_url(url)
    if parsed.database != "visioninsight_roi_test" or parsed.username != "vi_roi_test":
        raise RuntimeError("ISOLATED_TEST_DB_REQUIRED")
    base = database_engine(url)
    if action == "prepare":
        if path.exists():
            raise RuntimeError("EXISTING_EVIDENCE_PRESERVED")
        state = {"owner": "VisionInsight ROI restart probe", "schema": "roi_restart_" + uuid.uuid4().hex}
        with base.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{state["schema"]}"'))
    else:
        state = json.loads(path.read_text(encoding="utf8"))
        if state.get("owner") != "VisionInsight ROI restart probe" or not state["schema"].startswith("roi_restart_"):
            raise RuntimeError("UNRECOGNIZED_EVIDENCE")
        if len(state["schema"]) != len("roi_restart_") + 32 or not all(character in "0123456789abcdef" for character in state["schema"][12:]):
            raise RuntimeError("UNRECOGNIZED_SCHEMA")
    scoped = parsed.update_query_dict({"options": "-csearch_path=" + state["schema"]}).render_as_string(hide_password=False)
    runtime = RoiRuntime(RoiSettings(_env_file=None, database_url=scoped, roi_admin_token="restart-probe-token-not-a-real-admin-0001",
                                    roi_product_ids="PRODUCT-RESTART-PROBE"))
    headers = {"Authorization": "Bearer restart-probe-token-not-a-real-admin-0001"}
    if action == "prepare":
        engine = database_engine(scoped)
        with engine.begin() as connection:
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        engine.dispose()
    with TestClient(create_roi_app(runtime), base_url="http://localhost", client=("127.0.0.1", 50201)) as client:
        if action == "prepare":
            body = {"video_id": DEMO_VIDEO.video_id, "source_revision": DEMO_VIDEO.source_revision,
                    "source_width": 1920, "source_height": 480, "product_id": "PRODUCT-RESTART-PROBE",
                    "roi": {"x": 0, "y": 0, "width": 64, "height": 64}}
            response = client.post("/roi-presets", headers=headers, json=body)
            assert response.status_code == 201
            state["roi_config_id"] = response.json()["roi_config_id"]
            identifier = state["roi_config_id"]
            assert client.post(f"/roi-presets/{identifier}/versions", headers=headers,
                               json={"expected_version": 1, "roi": {"x": 32, "y": 32, "width": 64, "height": 64}}).status_code == 201
            assert client.post(f"/roi-presets/{identifier}/approve", headers=headers, json={"version": 2}).status_code == 200
            assert client.post(f"/roi-presets/{identifier}/activate", headers=headers,
                               json={"version": 2, "expected_active_revision": 0}).status_code == 200
        else:
            response = client.get(f'/roi-presets/{state["roi_config_id"]}/versions', headers=headers)
            assert response.status_code == 200
            versions = response.json()["versions"]
            assert [record["version"] for record in versions] == [1, 2]
            assert versions[1]["active"] and versions[1]["approved_for_auto"]
            state["database_restart_persistence"] = "PASS"
    with base.begin() as connection:
        state["server_version"] = connection.scalar(text("SHOW server_version"))
        if action == "verify":
            connection.execute(text(f'DROP SCHEMA "{state["schema"]}" CASCADE'))
            state["test_schema_cleaned"] = True
    base.dispose()
    path.write_text(json.dumps(state, indent=2), encoding="utf8")
    print(json.dumps(state))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "verify"))
    parser.add_argument("evidence", type=Path)
    arguments = parser.parse_args()
    probe(arguments.action, arguments.evidence)
