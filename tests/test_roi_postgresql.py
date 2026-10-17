from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from backend.db import ROOT, RoiSettings, database_engine, sessions
from backend.roi_api import RoiRuntime, create_roi_app
from backend.roi_models import ActiveBinding, Preset, Version
from backend.roi_repository import RoiRepository
from backend.roi_schemas import RoiError
from backend.video_source import VideoEntry, VideoFileSource, DEMO_VIDEO


TOKEN = "test-admin-token-only-not-production-0001"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Origin": "http://localhost:5173"}


@pytest.fixture
def database(tmp_path):
    value = os.getenv("VISIONINSIGHT_TEST_DATABASE_URL") or dotenv_values(ROOT / ".env.roi-db.local").get("VISIONINSIGHT_TEST_DATABASE_URL")
    if not value:
        pytest.skip("Dedicated PostgreSQL test URL not configured")
    parsed = make_url(value)
    if parsed.database != "visioninsight_roi_test" or parsed.username != "vi_roi_test":
        pytest.fail("Only the isolated VisionInsight PostgreSQL test role/database is permitted")
    base = database_engine(value)
    schema = "roi_test_" + uuid.uuid4().hex
    with base.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = parsed.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    engine = database_engine(scoped)
    with engine.begin() as connection:
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield engine, scoped
    engine.dispose()
    with base.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    base.dispose()


@pytest.fixture
def api(database, tmp_path):
    path = tmp_path / "source.mp4"
    path.write_bytes(b"metadata-only registry fixture; no frame decoding")
    entry = VideoEntry("VID-000001", path.name, hashlib.sha256(path.read_bytes()).hexdigest(), 1920, 480, 30, 240)
    settings = RoiSettings(_env_file=None, database_url=database[1], roi_admin_token=TOKEN,
                           roi_product_ids="PRODUCT-0001", roi_video_root=tmp_path)
    runtime = RoiRuntime(settings)
    runtime.engine = database[0]
    runtime.source = VideoFileSource(tmp_path, [entry])
    app = create_roi_app(runtime)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50123)) as client:
        yield client, runtime, entry


def payload(entry, **overrides):
    return {"video_id": entry.video_id, "source_revision": entry.source_revision,
            "source_width": 1920, "source_height": 480, "product_id": "PRODUCT-0001",
            "roi": {"x": 750, "y": 110, "width": 280, "height": 310}, **overrides}


def create(api):
    response = api[0].post("/roi-presets", headers=HEADERS, json=payload(api[2]))
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["version"] == 1 and not result["active"] and not result["approved_for_auto"]
    return result["roi_config_id"]


def test_lifecycle_and_history(api):
    client = api[0]
    identifier = create(api)
    assert client.get("/roi-presets", headers=HEADERS).json()["roi_presets"][0]["roi_config_id"] == identifier
    activated = client.post(f"/roi-presets/{identifier}/activate", headers=HEADERS,
                            json={"version": 1, "expected_active_revision": 0})
    assert activated.status_code == 409 and activated.json()["detail"]["error_code"] == "ROI_APPROVAL_REQUIRED"
    new = client.post(f"/roi-presets/{identifier}/versions", headers=HEADERS,
                      json={"expected_version": 1, "roi": {"x": 800, "y": 100, "width": 300, "height": 300}})
    assert new.status_code == 201 and new.json()["version"] == 2 and not new.json()["approved_for_auto"]
    assert client.post(f"/roi-presets/{identifier}/approve", headers=HEADERS, json={"version": 2}).json()["approved_for_auto"]
    active = client.post(f"/roi-presets/{identifier}/activate", headers=HEADERS,
                         json={"version": 2, "expected_active_revision": 0})
    assert active.status_code == 200 and active.json()["active"] and active.json()["binding_revision"] == 1
    scope = payload(api[2]); scope.pop("roi")
    assert client.get("/roi-presets/active", headers=HEADERS, params=scope).json()["version"] == 2
    versions = client.get(f"/roi-presets/{identifier}/versions", headers=HEADERS).json()["versions"]
    assert [value["version"] for value in versions] == [1, 2]
    assert versions[0]["roi"]["x"] == 750 and not versions[0]["approved_for_auto"]
    assert versions[1]["roi"]["x"] == 800 and versions[1]["active"]
    assert client.get(f"/roi-presets/{identifier}", headers=HEADERS).json()["head_version"] == 2
    assert client.get(f"/roi-presets/{identifier}/versions?offset=1&limit=1", headers=HEADERS).json()["versions"][0]["version"] == 2


@pytest.mark.parametrize("overrides,status", [
    ({"source_revision": "a" * 64}, 409), ({"video_id": "VID-999999"}, 404),
    ({"source_width": 1919}, 422), ({"source_height": 479}, 422),
    ({"product_id": "UNREGISTERED"}, 422), ({"product_id": "x'; DROP TABLE roi_presets;--"}, 422),
    ({"approved_for_auto": True}, 422), ({"roi": {"x": -1, "y": 0, "width": 32, "height": 32}}, 422),
    ({"roi": {"x": 0, "y": 0, "width": True, "height": 32}}, 422),
    ({"roi": {"x": 0, "y": 0, "width": 32.0, "height": 32}}, 422),
    ({"roi": {"x": 0, "y": 0, "width": 0, "height": 32}}, 422),
    ({"roi": {"x": 0, "y": 0, "width": 31, "height": 32}}, 422),
    ({"roi": {"x": 1900, "y": 0, "width": 32, "height": 32}}, 422),
])
def test_invalid_input(api, overrides, status):
    response = api[0].post("/roi-presets", headers=HEADERS, json=payload(api[2], **overrides))
    assert response.status_code == status
    assert api[0].get("/roi-presets", headers=HEADERS).json()["roi_presets"] == []


def test_boundary_and_unique_ids(api):
    identifiers = []
    for unused in range(3):
        response = api[0].post("/roi-presets", headers=HEADERS,
                               json=payload(api[2], roi={"x": 1888, "y": 448, "width": 32, "height": 32}))
        assert response.status_code == 201
        identifiers.append(response.json()["roi_config_id"])
    assert len(set(identifiers)) == 3


@pytest.mark.parametrize("headers,status", [({}, 401), ({"Authorization": "Bearer invalid"}, 401),
    ({**HEADERS, "Origin": "https://untrusted.invalid"}, 403),
    ({**HEADERS, "X-Forwarded-For": "127.0.0.1"}, 403)])
def test_admin_authentication(api, headers, status):
    for method, path, body in (("get", "/roi-presets", None), ("post", "/roi-presets", payload(api[2])),
                               ("post", "/roi-presets/ROI-unknown/approve", {"version": 1}),
                               ("post", "/roi-presets/ROI-unknown/activate", {"version": 1, "expected_active_revision": 0})):
        response = api[0].request(method, path, headers=headers, json=body)
        assert response.status_code == status


def test_admin_disabled_and_network_boundary(api):
    client, runtime, entry = api
    token = runtime.settings.roi_admin_token
    runtime.settings.roi_admin_token = None
    assert client.get("/roi-presets", headers=HEADERS).status_code == 503
    runtime.settings.roi_admin_token = token
    runtime.settings.roi_environment = "production"
    assert client.get("/roi-presets", headers=HEADERS).status_code == 403
    runtime.settings.roi_environment = "local"
    app = create_roi_app(runtime)
    with TestClient(app, base_url="http://localhost", client=("203.0.113.2", 50000)) as remote:
        assert remote.get("/roi-presets", headers=HEADERS).status_code == 403


def test_missing_conflict_and_injection(api):
    client = api[0]
    assert client.get("/roi-presets/ROI-missing", headers=HEADERS).status_code == 404
    identifier = create(api)
    invalid = client.post(f"/roi-presets/{identifier}/versions", headers=HEADERS,
                          json={"expected_version": 2, "roi": {"x": 0, "y": 0, "width": 32, "height": 32}})
    assert invalid.status_code == 409
    assert client.post(f"/roi-presets/{identifier}/approve", headers=HEADERS, json={"version": 99}).status_code == 404
    assert client.get("/roi-presets/ROI-' OR '1'='1", headers=HEADERS).status_code == 404
    assert len(client.get("/roi-presets", headers=HEADERS).json()["roi_presets"]) == 1


def test_changed_source_is_rejected_before_approval(api):
    identifier = create(api)
    path = api[1].source.root / api[2].relative_path
    path.write_bytes(b"changed")
    response = api[0].post(f"/roi-presets/{identifier}/approve", headers=HEADERS, json={"version": 1})
    assert response.status_code == 409
    assert not api[0].get(f"/roi-presets/{identifier}", headers=HEADERS).json()["approved_for_auto"]


def test_database_constraints_and_history(api, database):
    identifier = create(api)
    factory = sessions(database[0])
    for statement in ("UPDATE roi_preset_versions SET x=1", "DELETE FROM roi_preset_versions",
                      "UPDATE roi_presets SET product_id='OTHER'", "UPDATE roi_presets SET head_version=99"):
        with factory() as session, pytest.raises(IntegrityError):
            with session.begin():
                session.execute(text(statement))
    with factory() as session, pytest.raises(IntegrityError):
        with session.begin():
            session.add(Version(roi_config_id=identifier, version=1, x=0, y=0, width=32, height=32))
    scope = payload(api[2]); scope.pop("roi")
    with factory() as session, pytest.raises(IntegrityError):
        with session.begin():
            session.add(ActiveBinding(**scope, roi_config_id=identifier, version=1, binding_revision=1))


def test_parallel_versions_and_activation(api, database):
    identifier = create(api)
    factory = sessions(database[0])

    def add():
        try:
            with factory() as session, session.begin():
                repo = RoiRepository(session)
                repo.preset(identifier)
                repo.add_version(identifier, 1, {"x": 1, "y": 1, "width": 32, "height": 32})
            return 201
        except RoiError as failure:
            return failure.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda unused: add(), range(2))) == [201, 409]
    second = create(api)
    with factory() as session, session.begin():
        repo = RoiRepository(session)
        repo.approve(identifier, 1)
        repo.approve(second, 1)

    def activate(current):
        try:
            with factory() as session, session.begin():
                RoiRepository(session).activate(current, 1, 0)
            return 200
        except RoiError as failure:
            return failure.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(activate, [identifier, second])) == [200, 409]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ActiveBinding)) == 1


def test_rollback_keeps_previous_binding(api, database):
    identifier = create(api)
    factory = sessions(database[0])
    with factory() as session, session.begin():
        repo = RoiRepository(session)
        repo.add_version(identifier, 1, {"x": 1, "y": 1, "width": 32, "height": 32})
        repo.approve(identifier, 1)
        repo.approve(identifier, 2)
        repo.activate(identifier, 1, 0)
    with pytest.raises(RuntimeError):
        with factory() as session, session.begin():
            RoiRepository(session).activate(identifier, 2, 1)
            raise RuntimeError("synthetic failure after binding flush")
    with factory() as session:
        assert RoiRepository(session).view(RoiRepository(session).preset(identifier), 1)["active"]


def test_new_app_and_process_persistence(api, database):
    identifier = create(api)
    client = api[0]
    assert client.post(f"/roi-presets/{identifier}/versions", headers=HEADERS,
                       json={"expected_version": 1, "roi": {"x": 10, "y": 10, "width": 64, "height": 64}}).status_code == 201
    assert client.post(f"/roi-presets/{identifier}/approve", headers=HEADERS, json={"version": 2}).status_code == 200
    assert client.post(f"/roi-presets/{identifier}/activate", headers=HEADERS,
                       json={"version": 2, "expected_active_revision": 0}).status_code == 200
    api[1].close()
    environment = {**os.environ, "VISIONINSIGHT_DATABASE_URL": database[1],
                   "VISIONINSIGHT_ROI_ADMIN_TOKEN": TOKEN, "ROI_RESTART_ID": identifier}
    script = """import os,json
from fastapi.testclient import TestClient
from backend.roi_api import create_roi_app
with TestClient(create_roi_app(),base_url='http://localhost',client=('127.0.0.1',50001)) as client:
 response=client.get('/roi-presets/'+os.environ['ROI_RESTART_ID']+'/versions',headers={'Authorization':'Bearer '+os.environ['VISIONINSIGHT_ROI_ADMIN_TOKEN']})
 assert response.status_code==200
 values=response.json()['versions']
 assert [value['version'] for value in values]==[1,2]
 assert values[1]['approved_for_auto'] and values[1]['active']
 print('NEW_PROCESS_PERSISTENCE_PASS')
"""
    completed = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT, env=environment,
                               capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, "Persistence subprocess failed; credentials suppressed"
    assert "NEW_PROCESS_PERSISTENCE_PASS" in completed.stdout


def test_real_approved_video_metadata_only(database):
    settings = RoiSettings(_env_file=None, database_url=database[1], roi_admin_token=TOKEN,
                           roi_product_ids="PRODUCT-0001")
    runtime = RoiRuntime(settings)
    with TestClient(create_roi_app(runtime), base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        response = client.post("/roi-presets", headers=HEADERS, json=payload(DEMO_VIDEO))
        assert response.status_code == 201
        assert response.json()["source_revision"] == DEMO_VIDEO.source_revision
        assert not response.json()["approved_for_auto"] and not response.json()["active"]


def test_database_failure_is_sanitized(api, monkeypatch):
    from sqlalchemy.exc import OperationalError
    def fail():
        raise OperationalError("password-private-internal-path", {}, Exception("secret"))
    monkeypatch.setattr(api[1], "connection", fail)
    response = api[0].get("/roi-presets", headers=HEADERS)
    assert response.status_code == 503
    assert response.json() == {"detail": {"error_code": "ROI_DATABASE_UNAVAILABLE"}}


def test_approval_and_scope_database_guards(api, database):
    identifier = create(api)
    factory = sessions(database[0])
    with factory() as session, session.begin():
        RoiRepository(session).approve(identifier, 1)
    for statement in ("UPDATE roi_approvals SET version=99", "DELETE FROM roi_approvals"):
        with factory() as session, pytest.raises(IntegrityError):
            with session.begin():
                session.execute(text(statement))
    scope = payload(api[2]); scope.pop("roi"); scope["product_id"] = "OTHER"
    with factory() as session, pytest.raises(IntegrityError):
        with session.begin():
            session.add(ActiveBinding(**scope, roi_config_id=identifier, version=1, binding_revision=1))
    with factory() as session, pytest.raises(IntegrityError):
        with session.begin():
            preset = RoiRepository(session).preset(identifier)
            preset.head_version = 2
            session.flush()
            session.add(Version(roi_config_id=identifier, version=2, x=1900, y=0, width=100, height=32))
    assert api[0].get(f"/roi-presets/{identifier}", headers=HEADERS).json()["head_version"] == 1


def test_upgrade_existing_data_and_schema(database, api):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from backend.roi_models import Base
    identifier = create(api)
    with database[0].begin() as connection:
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001_roi_persistence"
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    assert api[0].get(f"/roi-presets/{identifier}", headers=HEADERS).status_code == 200


def test_error_does_not_echo_untrusted_fields(api):
    response = api[0].post("/roi-presets", headers=HEADERS,
                           json=payload(api[2], password="private-should-not-echo"))
    assert response.status_code == 422 and "private-should-not-echo" not in response.text


def test_commit_failure_prevents_success_response(api, monkeypatch):
    from sqlalchemy.exc import OperationalError
    original = api[1].connection

    def failing_connection():
        session = original()
        def fail_commit():
            raise OperationalError("private", {}, Exception("secret"))
        from sqlalchemy import event
        event.listen(session, "before_commit", lambda current: fail_commit())
        return session

    monkeypatch.setattr(api[1], "connection", failing_connection)
    response = api[0].post("/roi-presets", headers=HEADERS, json=payload(api[2]))
    assert response.status_code == 503 and "secret" not in response.text
    monkeypatch.setattr(api[1], "connection", original)
    assert api[0].get("/roi-presets", headers=HEADERS).json()["roi_presets"] == []


def test_roi_module_does_not_load_vision_or_model():
    script = "import sys; import backend.roi_api; assert 'torch' not in sys.modules; assert 'backend.vision' not in sys.modules; assert 'backend.ml.patchcore_inferencer' not in sys.modules"
    completed = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT, capture_output=True, timeout=30)
    assert completed.returncode == 0


def test_existing_main_router_and_cors(api):
    from backend.main import app
    from backend.roi_api import get_roi_runtime
    app.dependency_overrides[get_roi_runtime] = lambda: api[1]
    try:
        client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50301))
        response = client.post("/roi-presets", headers=HEADERS, json=payload(api[2]))
        assert response.status_code == 201
        assert "inspection_id" not in response.json() and "set-cookie" not in response.headers
        assert client.get("/roi-presets", headers=HEADERS).status_code == 200
        preflight = client.options("/roi-presets", headers={"Origin": "http://localhost:5173",
                                   "Access-Control-Request-Method": "POST",
                                   "Access-Control-Request-Headers": "authorization,content-type"})
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert client.get("/roi-presets", headers={**HEADERS, "Origin": "https://untrusted.invalid"}).status_code == 403
    finally:
        app.dependency_overrides.pop(get_roi_runtime, None)
