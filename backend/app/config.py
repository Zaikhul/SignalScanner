import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "Pemindai Area - Signal Scanner API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Environment & Security
    SECRET_KEY: str = "secret-signal-scanner-key-hmac-salt-change-in-prod"
    TENANT_SALT: str = "tenant_default_salt_2026"
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "*"
    ]

    # Database: SQLite async by default for zero-friction local run, PostgreSQL+TimescaleDB in prod
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./signal_scanner.db")
    
    # Stream Engine: "memory" for zero-dependency standalone mode or "redis"
    STREAM_BACKEND: str = os.getenv("STREAM_BACKEND", "memory")
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL", None)

    # Signal Processing defaults
    DEFAULT_EMA_ALPHA: float = 0.35
    DEFAULT_NOISE_FLOOR_DBM: float = -95.0
    DEFAULT_NOISE_FLOOR_DBFS: float = -100.0


settings = Settings()
