import pytest
from fastapi import HTTPException
from app.config import settings
from app.core.web_scan.authorization import get_current_principal, require_permission
from app.core.web_scan.registry import CAPABILITIES_CATALOG, get_capabilities
from app.schemas.web_scan import ProfileId


def test_capabilities_catalog_traceability():
    caps = get_capabilities()
    assert caps.engine_version == "1.0.0"
    assert len(caps.profiles) == 4

    profile_ids = [p.profile_id for p in caps.profiles]
    assert ProfileId.V2 in profile_ids
    assert ProfileId.LEGACY_V47 in profile_ids
    assert ProfileId.LEGACY_V75 in profile_ids
    assert ProfileId.COMPREHENSIVE in profile_ids

    # Verify check capabilities C-01 to C-48 mapping
    c_ids = {c.c_id for c in caps.checks}
    # Check key capabilities from PRD
    for expected_c in [
        "C-11", "C-12", "C-13", "C-14", "C-15", "C-16", "C-17", "C-18",
        "C-20", "C-21", "C-23", "C-24", "C-25", "C-28", "C-29", "C-30",
        "C-31", "C-32", "C-33", "C-34", "C-36", "C-37"
    ]:
        assert expected_c in c_ids, f"Capability {expected_c} missing from catalog"


@pytest.mark.asyncio
async def test_authorization_principal_validation():
    # Valid Bearer token
    principal = await get_current_principal(authorization=f"Bearer {settings.API_AUTH_TOKEN}")
    assert principal.tenant_id == settings.WEB_SCAN_DEFAULT_TENANT
    assert "web_scan:read" in principal.permissions
    assert "web_scan:execute" in principal.permissions

    # Invalid token raises 401
    with pytest.raises(HTTPException) as exc_info:
        await get_current_principal(authorization="Bearer invalid-token")
    assert exc_info.value.status_code == 401

    # Missing token raises 401
    with pytest.raises(HTTPException) as exc_info_missing:
        await get_current_principal(authorization=None)
    assert exc_info_missing.value.status_code == 401
