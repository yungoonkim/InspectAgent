"""Configuration module for InspectAgent.

Supports local development and Google Cloud Run deployment environments.
Ensures unified path management and configuration loading.
"""

from functools import lru_cache
import os
from pathlib import Path
from typing import Optional

# Base project directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    from pydantic import Field

    class Settings(BaseSettings):
        """Application settings loaded from environment variables or .env file."""

        # Application / Server
        APP_NAME: str = "InspectAgent"
        APP_VERSION: str = "0.1.0"
        ENVIRONMENT: str = Field(default="local", description="local | cloudrun | production")
        HOST: str = Field(default="0.0.0.0", description="Host address to bind")
        PORT: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")), description="Server port (Cloud Run sets PORT automatically)")

        # AI Agent / Gemini Model Configuration
        # Must strictly use gemini-3.8-flash as per project requirements
        GEMINI_MODEL: str = Field(default="gemini-3.8-flash", description="Target Gemini model name")
        GEMINI_API_KEY: Optional[str] = Field(default=None, description="Google Gemini API Key")

        # Paths (relative to PROJECT_ROOT or absolute)
        DATASET_PATH: str = Field(default="dataset/bottle", description="Path to MVTec AD bottle dataset")
        OUTPUT_DIR: str = Field(default="data/outputs", description="Path to save inspection output images")
        LOG_DIR: str = Field(default="data/logs", description="Path to store application and inspection logs")

        # Vision Quality & Fault Injection Settings
        # Normal bottle brightness mean is ~136.3 (p1: 133.5, p99: 139.5)
        BRIGHTNESS_LOW_THRESHOLD: float = Field(default=125.0, description="Lower threshold for image brightness warning")
        BRIGHTNESS_HIGH_THRESHOLD: float = Field(default=150.0, description="Upper threshold for image brightness warning")
        FAULT_INJECTION_FACTOR: float = Field(default=0.6, description="Multiplier for artificial brightness fault injection")

        model_config = SettingsConfigDict(
            env_file=str(PROJECT_ROOT / ".env"),
            env_file_encoding="utf-8",
            extra="ignore",
        )

        @property
        def absolute_dataset_path(self) -> Path:
            """Return resolved absolute path to dataset directory."""
            path = Path(self.DATASET_PATH)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        @property
        def absolute_output_path(self) -> Path:
            """Return resolved absolute path to outputs directory."""
            path = Path(self.OUTPUT_DIR)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        @property
        def absolute_log_path(self) -> Path:
            """Return resolved absolute path to logs directory."""
            path = Path(self.LOG_DIR)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        @property
        def absolute_injected_path(self) -> Path:
            """Return resolved absolute path to fault-injected outputs directory."""
            return self.absolute_output_path / "injected"

        def ensure_directories(self) -> None:
            """Create required output and log directories if they don't exist."""
            self.absolute_output_path.mkdir(parents=True, exist_ok=True)
            self.absolute_injected_path.mkdir(parents=True, exist_ok=True)
            self.absolute_log_path.mkdir(parents=True, exist_ok=True)

except ImportError:
    # Fallback when pydantic-settings is not yet installed
    class Settings:  # type: ignore[no-redef]
        """Fallback settings using os.getenv when dependencies are pending installation."""

        def __init__(self) -> None:
            self.APP_NAME = "InspectAgent"
            self.APP_VERSION = "0.1.0"
            self.ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
            self.HOST = os.getenv("HOST", "0.0.0.0")
            self.PORT = int(os.getenv("PORT", "8000"))
            self.GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
            self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
            self.DATASET_PATH = os.getenv("DATASET_PATH", "dataset/bottle")
            self.OUTPUT_DIR = os.getenv("OUTPUT_DIR", "data/outputs")
            self.LOG_DIR = os.getenv("LOG_DIR", "data/logs")
            self.BRIGHTNESS_LOW_THRESHOLD = float(os.getenv("BRIGHTNESS_LOW_THRESHOLD", "125.0"))
            self.BRIGHTNESS_HIGH_THRESHOLD = float(os.getenv("BRIGHTNESS_HIGH_THRESHOLD", "150.0"))
            self.FAULT_INJECTION_FACTOR = float(os.getenv("FAULT_INJECTION_FACTOR", "0.6"))

        @property
        def absolute_dataset_path(self) -> Path:
            path = Path(self.DATASET_PATH)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        @property
        def absolute_output_path(self) -> Path:
            path = Path(self.OUTPUT_DIR)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        @property
        def absolute_log_path(self) -> Path:
            path = Path(self.LOG_DIR)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        @property
        def absolute_injected_path(self) -> Path:
            return self.absolute_output_path / "injected"

        def ensure_directories(self) -> None:
            self.absolute_output_path.mkdir(parents=True, exist_ok=True)
            self.absolute_injected_path.mkdir(parents=True, exist_ok=True)
            self.absolute_log_path.mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """Retrieve cached application settings instance."""
    settings = Settings()
    settings.ensure_directories()
    return settings
