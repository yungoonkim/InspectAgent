import os

from alembic import context
from dotenv import dotenv_values

from backend.db import ROOT, database_engine
from backend.roi_models import Base


def run():
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        context.configure(connection=supplied, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    values = dotenv_values(ROOT / ".env.roi-db.local")
    url = os.getenv("VISIONINSIGHT_MIGRATION_URL") or values.get("VISIONINSIGHT_MIGRATION_URL")
    if not url:
        raise RuntimeError("ROI_MIGRATION_URL_REQUIRED")
    engine = database_engine(url)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


try:
    run()
except Exception:
    raise RuntimeError("ROI_MIGRATION_FAILED_CREDENTIALS_SUPPRESSED") from None
