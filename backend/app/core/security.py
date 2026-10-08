import hashlib
import hmac
from typing import Optional
from fastapi import Header, HTTPException, status
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


async def verify_operator_auth(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_collector_key: Optional[str] = Header(None, alias="X-Collector-Key"),
) -> str:
    """FastAPI dependency to verify operator / UI caller credentials."""
    token = None
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        elif len(parts) == 1:
            token = parts[0]
    elif x_api_key:
        token = x_api_key
    elif x_collector_key:
        token = x_collector_key

    valid_keys = [settings.API_AUTH_TOKEN, settings.COLLECTOR_API_KEY]
    is_valid = any(hmac.compare_digest(token, key) for key in valid_keys if token)

    if not token or not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="UNAUTHORIZED: Missing or invalid operator credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def verify_collector_auth(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_collector_key: Optional[str] = Header(None, alias="X-Collector-Key"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> str:
    """FastAPI dependency to verify collector daemon credentials."""
    token = None
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        elif len(parts) == 1:
            token = parts[0]
    elif x_collector_key:
        token = x_collector_key
    elif x_api_key:
        token = x_api_key

    valid_keys = [settings.COLLECTOR_API_KEY, settings.API_AUTH_TOKEN, settings.LOCAL_AGENT_TOKEN]
    is_valid = any(hmac.compare_digest(token, key) for key in valid_keys if token)

    if not token or not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="UNAUTHORIZED: Missing or invalid collector credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def verify_ws_token(token: Optional[str]) -> bool:
    """Validates token passed via query parameter for WebSocket connections."""
    if not token:
        return False
    return hmac.compare_digest(token, settings.API_AUTH_TOKEN) or hmac.compare_digest(token, settings.COLLECTOR_API_KEY)

