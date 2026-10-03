import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "Pemindai Area - Signal Scanner API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Environment & Security
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "secret-signal-scanner-key-hmac-salt-change-in-prod")
    TENANT_SALT: str = os.getenv("TENANT_SALT", "tenant_default_salt_2026")
    API_AUTH_TOKEN: str = os.getenv("API_AUTH_TOKEN", "signal-scanner-dev-token-2026")
    COLLECTOR_API_KEY: str = os.getenv("COLLECTOR_API_KEY", "collector-dev-key-2026")
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    def model_post_init(self, __context) -> None:
        if self.ENVIRONMENT == "production":
            if "change-in-prod" in self.SECRET_KEY or self.TENANT_SALT == "tenant_default_salt_2026":
                raise ValueError("Insecure default SECRET_KEY or TENANT_SALT detected in production mode!")

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
