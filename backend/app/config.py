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
            if not self.API_AUTH_TOKEN or self.API_AUTH_TOKEN == "signal-scanner-dev-token-2026":
                raise ValueError("Insecure default or empty API_AUTH_TOKEN detected in production mode!")
            if not self.COLLECTOR_API_KEY or self.COLLECTOR_API_KEY == "collector-dev-key-2026":
                raise ValueError("Insecure default or empty COLLECTOR_API_KEY detected in production mode!")

    # Database: SQLite async by default for zero-friction local run, PostgreSQL+TimescaleDB in prod
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./signal_scanner.db")
    
    # Stream Engine: "memory" for zero-dependency standalone mode or "redis"
    STREAM_BACKEND: str = os.getenv("STREAM_BACKEND", "memory")
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL", None)

    # Signal Processing defaults
    DEFAULT_EMA_ALPHA: float = 0.35
    DEFAULT_NOISE_FLOOR_DBM: float = -95.0
    DEFAULT_NOISE_FLOOR_DBFS: float = -100.0

    # Web Scanner (Ghost Web Scanner integration - disabled by default)
    WEB_SCANNER_ENABLED: bool = os.getenv("WEB_SCANNER_ENABLED", "true").lower() in ("true", "1", "yes")
    WEB_SCAN_GLOBAL_MAX_CONCURRENCY: int = int(os.getenv("WEB_SCAN_GLOBAL_MAX_CONCURRENCY", "100000"))
    WEB_SCAN_PER_ORIGIN_CONCURRENCY: int = int(os.getenv("WEB_SCAN_PER_ORIGIN_CONCURRENCY", "50000"))
    WEB_SCAN_DEFAULT_TIMEOUT_SEC: float = float(os.getenv("WEB_SCAN_DEFAULT_TIMEOUT_SEC", "600.0"))
    WEB_SCAN_MAX_BODY_BYTES: int = int(os.getenv("WEB_SCAN_MAX_BODY_BYTES", str(1024 * 1024)))  # 1 MiB
    WEB_SCAN_ALLOW_PRIVATE_NETWORKS: bool = os.getenv("WEB_SCAN_ALLOW_PRIVATE_NETWORKS", "true").lower() in ("true", "1")
    WEB_SCAN_DEFAULT_TENANT: str = os.getenv("WEB_SCAN_DEFAULT_TENANT", "default_tenant")

    # Web Scan Geography & Executor Identification
    WEB_SCAN_EXECUTOR_ORIGIN_ID: str = os.getenv("WEB_SCAN_EXECUTOR_ORIGIN_ID", "scanner-backend-worker-1")
    WEB_SCAN_EXECUTOR_LATITUDE: Optional[float] = (
        float(os.getenv("WEB_SCAN_EXECUTOR_LATITUDE")) if os.getenv("WEB_SCAN_EXECUTOR_LATITUDE") else None
    )
    WEB_SCAN_EXECUTOR_LONGITUDE: Optional[float] = (
        float(os.getenv("WEB_SCAN_EXECUTOR_LONGITUDE")) if os.getenv("WEB_SCAN_EXECUTOR_LONGITUDE") else None
    )
    WEB_SCAN_EXECUTOR_COUNTRY: Optional[str] = os.getenv("WEB_SCAN_EXECUTOR_COUNTRY")
    WEB_SCAN_EXECUTOR_CITY: Optional[str] = os.getenv("WEB_SCAN_EXECUTOR_CITY")
    WEB_SCAN_GEOGRAPHY_ENABLED: bool = os.getenv("WEB_SCAN_GEOGRAPHY_ENABLED", "true").lower() in ("true", "1", "yes")



settings = Settings()
