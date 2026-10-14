"""Application runtime settings and environment configuration.

Loads and validates environment variables from the workspace .env file,
enforcing strict validation on secrets, CORS origins, and connection parameters.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_env_file_path = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Central application configuration schema."""

    PROJECT_NAME: str = "Cost-Sensitive Fraud Detection API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Runtime Environment
    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Cross-Origin Resource Sharing (CORS)
    CORS_ORIGINS: Union[List[str], str] = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]
    # Database
    DATABASE_URL: Optional[str] = None
    TEST_DATABASE_URL: Optional[str] = None

    # Security & JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    BCRYPT_ROUNDS: int = 12

    # Model & Artifact Governance
    MODEL_DIR: str = "./ml/models"
    ACTIVE_MODEL_VERSION: str = "xgb-cost-v1"

    model_config = SettingsConfigDict(
        env_file=str(_env_file_path) if _env_file_path.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        """Parses comma-separated CORS origin strings into a clean list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(origin).strip() for origin in v if str(origin).strip()]
        return ["http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("DATABASE_URL", "TEST_DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, v: Optional[str]) -> Optional[str]:
        """Normalizes standard postgresql:// URLs to postgresql+psycopg:// for psycopg v3."""
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        """Ensures that the JWT secret is secure and not a default placeholder in production."""
        if not v or len(v.strip()) < 16:
            raise ValueError("JWT_SECRET_KEY must be at least 16 characters long.")
        if "change_me" in v.lower() and os.getenv("APP_ENV", "development") == "production":
            raise ValueError("Insecure placeholder JWT_SECRET_KEY is not allowed in production.")
        return v


# Shared singleton instance
settings = Settings()
