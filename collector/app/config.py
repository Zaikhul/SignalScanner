import os
import platform
import socket
from pydantic_settings import BaseSettings, SettingsConfigDict


class CollectorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    COLLECTOR_ID: str = os.getenv("COLLECTOR_ID", f"col_{socket.gethostname().lower().replace('-', '_')}")
    COLLECTOR_NAME: str = os.getenv("COLLECTOR_NAME", f"Scanner ({socket.gethostname()})")
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
    SECRET_KEY: str = "secret-signal-scanner-key-hmac-salt-change-in-prod"
    TENANT_SALT: str = "tenant_default_salt_2026"
    
    PLATFORM: str = platform.system().lower()  # windows, linux, darwin
    BUFFER_DB_PATH: str = os.getenv("BUFFER_DB_PATH", "./collector_offline_buffer.db")
    MAX_BUFFER_RECORDS: int = 5000

    # Polling intervals
    HEARTBEAT_INTERVAL_SECONDS: int = 5
    DEFAULT_SAMPLE_INTERVAL_MS: int = 500


collector_settings = CollectorSettings()
