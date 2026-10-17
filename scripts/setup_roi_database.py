import argparse
from pathlib import Path
import secrets

from dotenv import dotenv_values
import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.roi-db.local"


def prepare():
    if ENV_FILE.exists():
        raise SystemExit("Existing ROI environment preserved; no secrets regenerated")
    bootstrap = secrets.token_urlsafe(32)
    migrator = secrets.token_urlsafe(32)
    application = secrets.token_urlsafe(32)
    testing = secrets.token_urlsafe(32)
    token = secrets.token_urlsafe(32)
    values = {
        "VI_PG_BOOTSTRAP_PASSWORD": bootstrap,
        "VI_PG_MIGRATOR_PASSWORD": migrator,
        "VI_PG_APP_PASSWORD": application,
        "VI_PG_TEST_PASSWORD": testing,
        "VISIONINSIGHT_DATABASE_URL": f"postgresql+psycopg://vi_roi_app:{application}@127.0.0.1:55432/visioninsight_roi",
        "VISIONINSIGHT_MIGRATION_URL": f"postgresql+psycopg://vi_roi_migrator:{migrator}@127.0.0.1:55432/visioninsight_roi",
        "VISIONINSIGHT_TEST_DATABASE_URL": f"postgresql+psycopg://vi_roi_test:{testing}@127.0.0.1:55432/visioninsight_roi_test",
        "VISIONINSIGHT_ROI_ADMIN_TOKEN": token,
        "VISIONINSIGHT_ROI_PRODUCT_IDS": "",
    }
    with ENV_FILE.open("x", encoding="utf8") as output:
        output.write("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    print("Created ignored .env.roi-db.local; configure registered ROI product IDs before API use")


def initialize():
    values = dotenv_values(ENV_FILE)
    with psycopg.connect(host="127.0.0.1", port=55432, dbname="postgres",
                         user="visioninsight_bootstrap", password=values["VI_PG_BOOTSTRAP_PASSWORD"],
                         autocommit=True) as connection:
        for role, key in (("vi_roi_migrator", "VI_PG_MIGRATOR_PASSWORD"),
                          ("vi_roi_app", "VI_PG_APP_PASSWORD"), ("vi_roi_test", "VI_PG_TEST_PASSWORD")):
            if connection.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                raise RuntimeError("Existing ROI role preserved; initialization requires fresh dedicated resources")
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                sql.Identifier(role), sql.Literal(values[key])))
        for database, owner in (("visioninsight_roi", "vi_roi_migrator"), ("visioninsight_roi_test", "vi_roi_test")):
            connection.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database), sql.Identifier(owner)))
            connection.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))
        connection.execute("GRANT CONNECT ON DATABASE visioninsight_roi TO vi_roi_app")
    print("Created dedicated development/test databases and separate non-superuser roles")


def grants():
    values = dotenv_values(ENV_FILE)
    with psycopg.connect(host="127.0.0.1", port=55432, dbname="visioninsight_roi",
                         user="vi_roi_migrator", password=values["VI_PG_MIGRATOR_PASSWORD"]) as connection:
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        connection.execute("GRANT USAGE ON SCHEMA public TO vi_roi_app")
        connection.execute("GRANT SELECT, INSERT ON roi_presets, roi_preset_versions, roi_approvals TO vi_roi_app")
        connection.execute("GRANT UPDATE (head_version) ON roi_presets TO vi_roi_app")
        connection.execute("GRANT SELECT, INSERT, UPDATE ON roi_active_bindings TO vi_roi_app")
    print("Granted runtime DML only; no DDL or historical-version modification privileges")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "initialize", "grants"))
    arguments = parser.parse_args()
    try:
        {"prepare": prepare, "initialize": initialize, "grants": grants}[arguments.action]()
    except (psycopg.Error, KeyError, RuntimeError, OSError):
        raise SystemExit("ROI database setup failed; existing resources were not reset. Credentials suppressed") from None
