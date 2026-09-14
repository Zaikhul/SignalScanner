import hashlib
import hmac
from typing import Optional
from collector.app.config import collector_settings


def pseudonymize_id(raw_id: str, salt: Optional[str] = None) -> str:
    """Creates a deterministic HMAC-SHA256 hash for BSSID/MAC/UUID on the client before upload."""
    if not raw_id:
        return ""
    clean_id = raw_id.strip().lower()
    effective_salt = (salt or collector_settings.TENANT_SALT).encode("utf-8")
    key = collector_settings.SECRET_KEY.encode("utf-8")
    
    h = hmac.new(key, msg=effective_salt + b":" + clean_id.encode("utf-8"), digestmod=hashlib.sha256)
    return f"hmac:{h.hexdigest()[:16]}"
