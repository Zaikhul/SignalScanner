import pytest
from datetime import datetime, timezone
import uuid
from fastapi import HTTPException

from app.db.session import init_db, AsyncSessionLocal
from app.db.web_scan_models import WebScanJobModel, WebScanFindingModel, WebScanObservationModel
from app.schemas.web_scan import (
    CreateScanRequest,
    ModuleId,
    Severity,
    Confidence,
    TriageFindingRequest,
)
from app.services.web_scan_service import WebScanService
from app.core.web_scan.geolocation import OfflineGeoIPService
from app.services.web_scan_geography_service import WebScanGeographyService


@pytest.mark.asyncio
async def test_f09_finding_triage_lifecycle_and_optimistic_locking():
    """Verify triage state transitions, audit trail, and optimistic version conflict (F09)."""
    await init_db()
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        scan_id = str(uuid.uuid4())
        job = WebScanJobModel(
            id=scan_id,
            tenant_id="tenant_triage_01",
            created_by="op_user_01",
            raw_target="https://target.local",
            normalized_target="https://target.local",
            target_display="https://target.local",
            status="completed",
            version=1,
            created_at=now,
        )
        db.add(job)

        finding_id = f"fnd_{uuid.uuid4().hex[:12]}"
        finding = WebScanFindingModel(
            id=finding_id,
            scan_id=scan_id,
            module="headers",
            check_id="tls_weak_cipher",
            category="crypto",
            severity="high",
            severity_reason="CBC cipher enabled",
            confidence="high",
            title="Weak TLS Cipher Suite",
            description="Server supports 3DES-CBC",
            remediation="Disable CBC ciphers",
            evidence={},
            fingerprint="fp_tls_001",
            triage_status="open",
            triage_version=1,
        )
        db.add(finding)
        await db.commit()

        # 1. Transition finding to false_positive
        triage_req = TriageFindingRequest(
            status="false_positive",
            reason="Internal legacy gateway behind WAF",
            expected_version=1,
        )
        res = await WebScanService.triage_finding(
            db, "tenant_triage_01", "op_user_01", scan_id, finding_id, triage_req
        )
        assert res.triage_status == "false_positive"
        assert res.triage_reason == "Internal legacy gateway behind WAF"
        assert res.triage_version == 2
        assert res.triage_actor == "op_user_01"

        # 2. Test optimistic locking conflict: passing expected_version=1 must fail
        with pytest.raises(HTTPException) as exc_info:
            await WebScanService.triage_finding(
                db, "tenant_triage_01", "op_user_01", scan_id, finding_id, triage_req
            )
        assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_f09_compare_scan_findings_recurring_new_resolved():
    """Verify cross-scan findings comparison with recurring, new, and resolved categorization (F09)."""
    await init_db()
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        scan_a = str(uuid.uuid4())
        scan_b = str(uuid.uuid4())

        job_a = WebScanJobModel(
            id=scan_a,
            tenant_id="tenant_cmp_01",
            created_by="op_user_01",
            raw_target="https://target.local",
            normalized_target="https://target.local",
            target_display="https://target.local",
            status="completed",
            version=1,
            created_at=now,
        )
        job_b = WebScanJobModel(
            id=scan_b,
            tenant_id="tenant_cmp_01",
            created_by="op_user_01",
            raw_target="https://target.local",
            normalized_target="https://target.local",
            target_display="https://target.local",
            status="completed",
            version=1,
            created_at=now,
        )
        db.add_all([job_a, job_b])

        # Scan A: has fp_recurring and fp_resolved
        f_rec_a = WebScanFindingModel(
            id="fnd_a1", scan_id=scan_a, module="header", check_id="missing_csp",
            category="headers", severity="medium", severity_reason="No CSP",
            confidence="high", title="Missing CSP", description="No CSP",
            remediation="Add CSP", evidence={}, fingerprint="fp_recurring",
            triage_status="open", triage_version=1,
        )
        f_res_a = WebScanFindingModel(
            id="fnd_a2", scan_id=scan_a, module="tls", check_id="tls10",
            category="crypto", severity="high", severity_reason="TLS 1.0",
            confidence="high", title="TLS 1.0 Enabled", description="TLS 1.0",
            remediation="Disable TLS 1.0", evidence={}, fingerprint="fp_resolved",
            triage_status="open", triage_version=1,
        )
        # Scan B: has fp_recurring and fp_new
        f_rec_b = WebScanFindingModel(
            id="fnd_b1", scan_id=scan_b, module="header", check_id="missing_csp",
            category="headers", severity="medium", severity_reason="No CSP",
            confidence="high", title="Missing CSP", description="No CSP",
            remediation="Add CSP", evidence={}, fingerprint="fp_recurring",
            triage_status="open", triage_version=1,
        )
        f_new_b = WebScanFindingModel(
            id="fnd_b2", scan_id=scan_b, module="cors", check_id="cors_wildcard",
            category="cors", severity="medium", severity_reason="Wildcard",
            confidence="high", title="CORS Wildcard", description="Wildcard",
            remediation="Restrict origin", evidence={}, fingerprint="fp_new",
            triage_status="open", triage_version=1,
        )
        db.add_all([f_rec_a, f_res_a, f_rec_b, f_new_b])
        await db.commit()

        cmp_res = await WebScanService.compare_scan_findings(db, "tenant_cmp_01", scan_a, scan_b)
        assert cmp_res.compatible is True
        statuses = {item.fingerprint: item.status for item in cmp_res.findings}
        assert statuses["fp_recurring"] == "recurring"
        assert statuses["fp_resolved"] == "resolved"
        assert statuses["fp_new"] == "new"


def test_f10_geolocation_regional_block_precision():
    """Verify that APNIC and RIPE /8 regional blocks are not mapped to city level (F10/T10)."""
    # 103.1.2.3 is within APNIC 103.0.0.0/8
    point_apnic, level_apnic, status_apnic, _, _ = OfflineGeoIPService.lookup_target_ip("103.1.2.3")
    assert status_apnic == "located"
    assert level_apnic == "region"
    assert point_apnic.city is None
    assert point_apnic.region == "Asia-Pacific"

    # 185.1.2.3 is within RIPE 185.0.0.0/8
    point_ripe, level_ripe, status_ripe, _, _ = OfflineGeoIPService.lookup_target_ip("185.1.2.3")
    assert status_ripe == "located"
    assert level_ripe == "region"
    assert point_ripe.city is None
    assert point_ripe.region == "Europe"


@pytest.mark.asyncio
async def test_f10_geography_service_module_correlation():
    """Verify that GeoRelations capture contributing module_ids for filtering (F10)."""
    await init_db()
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        scan_id = str(uuid.uuid4())
        job = WebScanJobModel(
            id=scan_id,
            tenant_id="tenant_geo_01",
            created_by="op_user_01",
            raw_target="https://example.com",
            normalized_target="https://example.com",
            target_display="https://example.com",
            status="completed",
            version=1,
            created_at=now,
        )
        db.add(job)

        obs = WebScanObservationModel(
            id=f"obs_{uuid.uuid4().hex[:8]}",
            scan_id=scan_id,
            module="tls",
            kind="http_response",
            data={"target_ip": "93.184.216.34", "status_code": 200, "method": "GET"},
            observed_at=now,
        )
        db.add(obs)
        await db.commit()

        geo_res = await WebScanGeographyService.get_scan_geography(db, "tenant_geo_01", scan_id)
        assert len(geo_res.relations) >= 1
        rel = geo_res.relations[0]
        assert "tls" in rel.module_ids
