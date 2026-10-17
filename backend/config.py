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
    from pydantic import Field, field_validator

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
        AGENT_MAX_TOOL_ROUNDS: int = Field(default=4, ge=1, le=10)
        AGENT_MAX_TOOL_CALLS: int = Field(default=8, ge=1, le=30)
        AGENT_MAX_REPEAT_CALLS: int = Field(default=2, ge=1, le=3)
        AGENT_REQUEST_TIMEOUT_SECONDS: float = Field(default=60, gt=0, le=180)
        AGENT_MODEL_TIMEOUT_SECONDS: float = Field(default=15, gt=0, le=60)
        AGENT_FINAL_MODEL_TIMEOUT_SECONDS: int = Field(default=15, ge=1, le=30)
        AGENT_TOOL_TIMEOUT_SECONDS: float = Field(default=3, gt=0, le=10)
        AGENT_MAX_PAYLOAD_BYTES: int = Field(default=65536, ge=1024, le=262144)

        @field_validator("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", mode="before")
        @classmethod
        def validate_final_timeout(cls, value):
            if isinstance(value, bool):
                raise ValueError("INVALID_FINAL_MODEL_TIMEOUT")
            return value

        # Paths (relative to PROJECT_ROOT or absolute)
        DATASET_PATH: str = Field(default="dataset/bottle", description="Path to MVTec AD bottle dataset")
        OUTPUT_DIR: str = Field(default="data/outputs", description="Path to save inspection output images")
        LOG_DIR: str = Field(default="data/logs", description="Path to store application and inspection logs")
        INSPECTIONS_FILE: str = Field(default="data/inspections.jsonl", description="Path to inspections JSONL file")
        INSPECTION_LOGS_FILE: str = Field(default="data/inspection_logs.jsonl", description="Path to inspection logs JSONL file")
        TEST_DATA_DIR: str = Field(default="test_data", description="Path to test scenarios and test injected images")
        VIDEO_ROOT: str = "data/outputs/videos"
        VIDEO_MAX_BYTES: int = Field(default=128 * 1024 * 1024, gt=0)
        VIDEO_MAX_WIDTH: int = Field(default=1920, gt=0)
        VIDEO_MAX_HEIGHT: int = Field(default=1080, gt=0)
        VIDEO_MAX_FRAMES: int = Field(default=900, gt=0)
        VIDEO_MAX_DECODERS: int = Field(default=2, ge=1, le=8)
        CAPTURE_DIR: str = "data/outputs/captures"
        CAPTURE_TTL_SECONDS: int = Field(default=1800, gt=0)
        CAPTURE_SESSION_SECONDS: int = Field(default=3600, gt=0)
        CAPTURE_MAX_BYTES: int = Field(default=256 * 1024 * 1024, gt=0)
        CAPTURE_MAX_COUNT: int = Field(default=128, gt=0)
        CAPTURE_MAX_PER_SESSION: int = Field(default=32, gt=0)
        CAPTURE_MAX_SESSIONS: int = Field(default=256, gt=0)
        CAPTURE_COOKIE_SECURE: bool = False
        CORS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

        # Vision Quality & Fault Injection Settings
        # Normal bottle brightness mean is ~136.3 (p1: 133.5, p99: 139.5)
        BRIGHTNESS_LOW_THRESHOLD: float = Field(default=125.0, description="Lower threshold for image brightness warning")
        BRIGHTNESS_HIGH_THRESHOLD: float = Field(default=150.0, description="Upper threshold for image brightness warning")
        FAULT_INJECTION_FACTOR: float = Field(default=0.6, description="Multiplier for artificial brightness fault injection")

        # PatchCore ML Defect Inspection Settings
        ENABLE_PATCHCORE: bool = Field(default=True, description="Enable PatchCore ML defect inspection")
        PATCHCORE_CHECKPOINT_PATH: str = Field(default="models/patchcore/patchcore_bottle.ckpt", description="Path to PatchCore checkpoint")
        PATCHCORE_METADATA_PATH: str = Field(default="models/patchcore/model_metadata.json", description="Path to PatchCore model metadata")
        PATCHCORE_DEVICE: str = Field(default="cpu", description="Computing device for PatchCore inference ('cpu' or 'cuda')")
        DECISION_THRESHOLD: Optional[float] = Field(
            default=34.1442,
            description="Calibrated anomaly score threshold for OK/NG decision (None = UNKNOWN)",
        )

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

        @property
        def absolute_inspections_path(self) -> Path:
            """Return resolved absolute path to inspections JSONL file."""
            path = Path(self.INSPECTIONS_FILE)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        @property
        def absolute_inspection_logs_path(self) -> Path:
            """Return resolved absolute path to inspection logs JSONL file."""
            path = Path(self.INSPECTION_LOGS_FILE)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        @property
        def absolute_test_data_path(self) -> Path:
            """Return resolved absolute path to test_data directory."""
            path = Path(self.TEST_DATA_DIR)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        @property
        def absolute_injected_images_path(self) -> Path:
            """Return resolved absolute path to test_data/injected_images directory."""
            return self.absolute_test_data_path / "injected_images"

        @property
        def absolute_patchcore_checkpoint_path(self) -> Path:
            """Return resolved absolute path to PatchCore model checkpoint."""
            path = Path(self.PATCHCORE_CHECKPOINT_PATH)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        @property
        def absolute_patchcore_metadata_path(self) -> Path:
            """Return resolved absolute path to PatchCore model metadata JSON."""
            path = Path(self.PATCHCORE_METADATA_PATH)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        def ensure_directories(self) -> None:
            """Create required output, log, data, and test directories if they don't exist."""
            self.absolute_output_path.mkdir(parents=True, exist_ok=True)
            self.absolute_injected_path.mkdir(parents=True, exist_ok=True)
            self.absolute_log_path.mkdir(parents=True, exist_ok=True)
            self.absolute_inspections_path.parent.mkdir(parents=True, exist_ok=True)
            self.absolute_inspection_logs_path.parent.mkdir(parents=True, exist_ok=True)
            self.absolute_injected_images_path.mkdir(parents=True, exist_ok=True)
            self.absolute_patchcore_checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

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
            self.AGENT_MAX_TOOL_ROUNDS = int(os.getenv("AGENT_MAX_TOOL_ROUNDS", "4"))
            self.AGENT_MAX_TOOL_CALLS = int(os.getenv("AGENT_MAX_TOOL_CALLS", "8"))
            self.AGENT_MAX_REPEAT_CALLS = int(os.getenv("AGENT_MAX_REPEAT_CALLS", "2"))
            self.AGENT_REQUEST_TIMEOUT_SECONDS = float(os.getenv("AGENT_REQUEST_TIMEOUT_SECONDS", "60"))
            self.AGENT_MODEL_TIMEOUT_SECONDS = float(os.getenv("AGENT_MODEL_TIMEOUT_SECONDS", "15"))
            self.AGENT_FINAL_MODEL_TIMEOUT_SECONDS = int(os.getenv("AGENT_FINAL_MODEL_TIMEOUT_SECONDS", "15"))
            if not 1 <= self.AGENT_FINAL_MODEL_TIMEOUT_SECONDS <= 30:
                raise ValueError("INVALID_FINAL_MODEL_TIMEOUT")
            self.AGENT_TOOL_TIMEOUT_SECONDS = float(os.getenv("AGENT_TOOL_TIMEOUT_SECONDS", "3"))
            self.AGENT_MAX_PAYLOAD_BYTES = int(os.getenv("AGENT_MAX_PAYLOAD_BYTES", "65536"))
            self.DATASET_PATH = os.getenv("DATASET_PATH", "dataset/bottle")
            self.OUTPUT_DIR = os.getenv("OUTPUT_DIR", "data/outputs")
            self.LOG_DIR = os.getenv("LOG_DIR", "data/logs")
            self.INSPECTIONS_FILE = os.getenv("INSPECTIONS_FILE", "data/inspections.jsonl")
            self.INSPECTION_LOGS_FILE = os.getenv("INSPECTION_LOGS_FILE", "data/inspection_logs.jsonl")
            self.BRIGHTNESS_LOW_THRESHOLD = float(os.getenv("BRIGHTNESS_LOW_THRESHOLD", "125.0"))
            self.BRIGHTNESS_HIGH_THRESHOLD = float(os.getenv("BRIGHTNESS_HIGH_THRESHOLD", "150.0"))
            self.FAULT_INJECTION_FACTOR = float(os.getenv("FAULT_INJECTION_FACTOR", "0.6"))
            self.TEST_DATA_DIR = os.getenv("TEST_DATA_DIR", "test_data")
            self.VIDEO_ROOT = os.getenv("VIDEO_ROOT", "data/outputs/videos")
            self.VIDEO_MAX_BYTES = int(os.getenv("VIDEO_MAX_BYTES", str(128 * 1024 * 1024)))
            self.VIDEO_MAX_WIDTH = int(os.getenv("VIDEO_MAX_WIDTH", "1920"))
            self.VIDEO_MAX_HEIGHT = int(os.getenv("VIDEO_MAX_HEIGHT", "1080"))
            self.VIDEO_MAX_FRAMES = int(os.getenv("VIDEO_MAX_FRAMES", "900"))
            self.VIDEO_MAX_DECODERS = int(os.getenv("VIDEO_MAX_DECODERS", "2"))
            self.CAPTURE_DIR = os.getenv("CAPTURE_DIR", "data/outputs/captures")
            self.CAPTURE_TTL_SECONDS = int(os.getenv("CAPTURE_TTL_SECONDS", "1800"))
            self.CAPTURE_SESSION_SECONDS = int(os.getenv("CAPTURE_SESSION_SECONDS", "3600"))
            self.CAPTURE_MAX_BYTES = int(os.getenv("CAPTURE_MAX_BYTES", str(256 * 1024 * 1024)))
            self.CAPTURE_MAX_COUNT = int(os.getenv("CAPTURE_MAX_COUNT", "128"))
            self.CAPTURE_MAX_PER_SESSION = int(os.getenv("CAPTURE_MAX_PER_SESSION", "32"))
            self.CAPTURE_MAX_SESSIONS = int(os.getenv("CAPTURE_MAX_SESSIONS", "256"))
            self.CAPTURE_COOKIE_SECURE = os.getenv("CAPTURE_COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
            self.CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
            self.ENABLE_PATCHCORE = os.getenv("ENABLE_PATCHCORE", "true").lower() in ("1", "true", "yes")
            self.PATCHCORE_CHECKPOINT_PATH = os.getenv("PATCHCORE_CHECKPOINT_PATH", "models/patchcore/patchcore_bottle.ckpt")
            self.PATCHCORE_METADATA_PATH = os.getenv("PATCHCORE_METADATA_PATH", "models/patchcore/model_metadata.json")
            self.PATCHCORE_DEVICE = os.getenv("PATCHCORE_DEVICE", "cpu")
            thresh_env = os.getenv("DECISION_THRESHOLD", "34.1442")
            self.DECISION_THRESHOLD = None if thresh_env.lower() in ("none", "null", "") else float(thresh_env)

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

        @property
        def absolute_test_data_path(self) -> Path:
            path = Path(self.TEST_DATA_DIR)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        @property
        def absolute_injected_images_path(self) -> Path:
            return self.absolute_test_data_path / "injected_images"

        @property
        def absolute_inspections_path(self) -> Path:
            path = Path(self.INSPECTIONS_FILE)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        @property
        def absolute_inspection_logs_path(self) -> Path:
            path = Path(self.INSPECTION_LOGS_FILE)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        @property
        def absolute_patchcore_checkpoint_path(self) -> Path:
            path = Path(self.PATCHCORE_CHECKPOINT_PATH)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        @property
        def absolute_patchcore_metadata_path(self) -> Path:
            path = Path(self.PATCHCORE_METADATA_PATH)
            return path if path.is_absolute() else (PROJECT_ROOT / path)

        def ensure_directories(self) -> None:
            self.absolute_output_path.mkdir(parents=True, exist_ok=True)
            self.absolute_injected_path.mkdir(parents=True, exist_ok=True)
            self.absolute_test_data_path.mkdir(parents=True, exist_ok=True)
            self.absolute_injected_images_path.mkdir(parents=True, exist_ok=True)
            self.absolute_log_path.mkdir(parents=True, exist_ok=True)
            self.absolute_inspections_path.parent.mkdir(parents=True, exist_ok=True)
            self.absolute_inspection_logs_path.parent.mkdir(parents=True, exist_ok=True)
            self.absolute_patchcore_checkpoint_path.parent.mkdir(parents=True, exist_ok=True)



@lru_cache()
def get_settings() -> Settings:
    """Retrieve cached application settings instance."""
    settings = Settings()
    settings.ensure_directories()
    return settings
