from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]


class RoiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VISIONINSIGHT_", extra="ignore",
                                     env_file=(ROOT / ".env", ROOT / ".env.roi-db.local"))
    application_environment: str = Field(default="local", validation_alias="ENVIRONMENT")
    database_url: SecretStr | None = None
    roi_admin_token: SecretStr | None = None
    roi_product_ids: str = ""
    roi_min_size: int = Field(default=32, ge=1, le=256)
    roi_environment: str = "local"
    roi_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    roi_video_root: Path = ROOT / "data/outputs/videos"


def database_engine(url: str):
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("POSTGRESQL_REQUIRED")
    return create_engine(parsed, hide_parameters=True, pool_pre_ping=True,
                         pool_size=3, max_overflow=2,
                         connect_args={"connect_timeout": 5}, pool_timeout=5)


def sessions(engine):
    return sessionmaker(engine, expire_on_commit=False)
