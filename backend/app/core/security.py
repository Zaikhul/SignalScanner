import hashlib
import hmac
from typing import Optional
from app.config import settings


def pseudonymize_identifier(raw_id: str, salt: Optional[str] = None) -> str:
    """
    Creates a tenant-scoped HMAC-SHA256 pseudonymized hash for MAC / BSSID / UUID.
    Returns format: "hmac:xxxx..."
    """
    if not raw_id:
        return ""
    clean_id = raw_id.strip().lower()
    effective_salt = (salt or settings.TENANT_SALT).encode("utf-8")
    key = settings.SECRET_KEY.encode("utf-8")
    
    # Combined HMAC key with salt
    h = hmac.new(key, msg=effective_salt + b":" + clean_id.encode("utf-8"), digestmod=hashlib.sha256)
    digest_hex = h.hexdigest()
    # 16-character truncated hex for clean display and consistency
    return f"hmac:{digest_hex[:16]}"


def verify_device_signature(payload_bytes: bytes, signature_hex: str, secret: str) -> bool:
    """Verifies that an incoming collector batch was signed with the expected device key."""
    expected = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_hex)
