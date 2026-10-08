from __future__ import annotations

import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.web_scan.geolocation import OfflineGeoIPService
from app.db.models import Base
from app.db.web_scan_models import (
    WebScanFindingModel,
    WebScanJobModel,
    WebScanObservationModel,
)
from app.schemas.web_scan_geography import WebScanGeographyResponse
from app.services.web_scan_geography_service import WebScanGeographyService


@pytest.fixture
async def geo_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        yield session
    await engine.dispose()


def test_offline_geoip_private_and_loopback():
    """Verify that private, loopback, and reserved IPs are safely marked unsupported with no egress."""
    for ip in ["127.0.0.1", "10.0.1.5", "192.168.0.1", "172.16.5.10", "::1", "169.254.1.1"]:
        point, level, status, basis, reason = OfflineGeoIPService.lookup_target_ip(ip)
        assert point is None
        assert status == "unsupported"
        assert "private" in reason.lower() or "loopback" in reason.lower() or "reserved" in reason.lower()


def test_offline_geoip_public_resolution():
    """Verify that public Anycast and cloud IPs resolve accurately in offline mode."""
    # 1. Cloudflare Anycast
    point, level, status, basis, reason = OfflineGeoIPService.lookup_target_ip("1.1.1.1")
    assert status == "located"
    assert point is not None
    assert point.country == "Australia"
    assert -90.0 <= point.latitude <= 90.0
    assert -180.0 <= point.longitude <= 180.0

    # 2. Google Public DNS
    point, level, status, basis, reason = OfflineGeoIPService.lookup_target_ip("8.8.8.8")
    assert status == "located"
    assert point is not None
    assert point.country == "United States"
    assert point.city == "Mountain View"

    # 3. Quad9
    point, level, status, basis, reason = OfflineGeoIPService.lookup_target_ip("9.9.9.9")
    assert status == "located"
    assert point is not None
    assert point.country == "Switzerland"


def test_offline_geoip_source_resolution():
    """Verify that the execution worker source endpoint uses configured metadata with proper labels."""
    from app.config import Settings

    # Case A: Configured source
    custom_settings = Settings(
        WEB_SCAN_EXECUTOR_ORIGIN_ID="worker-us-east-1",
        WEB_SCAN_EXECUTOR_LATITUDE=38.9072,
        WEB_SCAN_EXECUTOR_LONGITUDE=-77.0369,
        WEB_SCAN_EXECUTOR_COUNTRY="United States",
        WEB_SCAN_EXECUTOR_CITY="Washington",
    )
    src = OfflineGeoIPService.resolve_source_endpoint(custom_settings)
    assert src.role == "source"
    assert src.location_status == "located"
    assert src.location_basis == "configured"
    assert src.location is not None
    assert src.location.city == "Washington"
    assert "configuration" in src.status_reason.lower()

    # Case B: Unconfigured source location
    unconfigured_settings = Settings(
        WEB_SCAN_EXECUTOR_ORIGIN_ID="worker-anonymous",
        WEB_SCAN_EXECUTOR_LATITUDE=None,
        WEB_SCAN_EXECUTOR_LONGITUDE=None,
    )
    src_anon = OfflineGeoIPService.resolve_source_endpoint(unconfigured_settings)
    assert src_anon.role == "source"
    assert src_anon.location_status == "unknown"
    assert src_anon.location is None


@pytest.mark.asyncio
async def test_geography_service_endpoint_and_relations(geo_test_db: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    """Verify that WebScanGeographyService builds web_scan.geo.v1 responses with accurate relations and coverage."""
    monkeypatch.setattr("app.services.web_scan_geography_service.settings.WEB_SCAN_EXECUTOR_LATITUDE", -6.2088)
    monkeypatch.setattr("app.services.web_scan_geography_service.settings.WEB_SCAN_EXECUTOR_LONGITUDE", 106.8456)
    monkeypatch.setattr("app.services.web_scan_geography_service.settings.WEB_SCAN_EXECUTOR_CITY", "Jakarta")
    monkeypatch.setattr("app.services.web_scan_geography_service.settings.WEB_SCAN_EXECUTOR_COUNTRY", "Indonesia")

    scan_id = str(uuid.uuid4())
    tenant_id = "test_tenant"

    # 1. Create Job
    job = WebScanJobModel(
        id=scan_id,
        tenant_id=tenant_id,
        created_by="test_op",
        raw_target="https://cloudflare.com",
        normalized_target="https://cloudflare.com",
        target_display="cloudflare.com",
        status="completed",
        version=1,
        summary_data={"observations_total": 1},
    )
    geo_test_db.add(job)

    # 2. Create Observation
    obs = WebScanObservationModel(
        id=str(uuid.uuid4()),
        scan_id=scan_id,
        module="recon",
        kind="http_response",
        data={
            "url_display": "https://cloudflare.com",
            "method": "GET",
            "status_code": 200,
            "target_ip": "1.1.1.1",
            "peer_ip": "1.1.1.1",
            "dns_candidates": ["1.1.1.1", "1.0.0.1"],
        },
    )
    geo_test_db.add(obs)
    await geo_test_db.commit()

    # 3. Query Geography
    res = await WebScanGeographyService.get_scan_geography(geo_test_db, tenant_id, scan_id)
    assert res is not None
    assert isinstance(res, WebScanGeographyResponse)
    assert res.schema_version == "web_scan.geo.v1"
    assert res.scan_id == scan_id
    assert res.readiness_status == "ready"

    # Endpoints: source and target
    assert len(res.endpoints) == 2
    roles = {ep.role for ep in res.endpoints}
    assert roles == {"source", "target"}

    target_ep = next(ep for ep in res.endpoints if ep.role == "target")
    assert target_ep.ip == "1.1.1.1"
    assert target_ep.location_status == "located"
    assert target_ep.location is not None
    assert target_ep.location.country == "Australia"

    # Relations
    assert len(res.relations) == 1
    rel = res.relations[0]
    assert rel.direction == "source_to_target"
    assert rel.record_count == 1
    assert 200 in rel.status_codes
    assert "GET" in rel.methods
    assert obs.id in rel.supporting_observation_ids

    # Coverage
    assert res.coverage.observations_stored == 1
    assert res.coverage.eligible_records == 1
    assert res.coverage.both_located_count == 1
    assert res.coverage.unlocated_count == 0


@pytest.mark.asyncio
async def test_geography_aggregation_and_evidence_linking(geo_test_db: AsyncSession):
    """Verify that multiple requests to the same endpoint aggregate cleanly and link matching findings."""
    scan_id = str(uuid.uuid4())
    tenant_id = "test_tenant"

    job = WebScanJobModel(
        id=scan_id,
        tenant_id=tenant_id,
        created_by="test_op",
        raw_target="https://example.com",
        normalized_target="https://example.com",
        target_display="example.com",
        status="completed",
        version=2,
        summary_data={"observations_total": 2},
    )
    geo_test_db.add(job)

    obs_id_1 = str(uuid.uuid4())
    obs_id_2 = str(uuid.uuid4())

    obs1 = WebScanObservationModel(
        id=obs_id_1,
        scan_id=scan_id,
        module="recon",
        kind="http_response",
        data={
            "url_display": "https://example.com/",
            "method": "GET",
            "status_code": 200,
            "target_ip": "93.184.216.34",
            "peer_ip": "93.184.216.34",
        },
    )
    obs2 = WebScanObservationModel(
        id=obs_id_2,
        scan_id=scan_id,
        module="recon",
        kind="http_response",
        data={
            "url_display": "https://example.com/login",
            "method": "POST",
            "status_code": 403,
            "target_ip": "93.184.216.34",
            "peer_ip": "93.184.216.34",
        },
    )
    geo_test_db.add_all([obs1, obs2])

    # Add security finding referencing obs_id_2
    finding_id = str(uuid.uuid4())
    finding = WebScanFindingModel(
        id=finding_id,
        scan_id=scan_id,
        module="recon",
        check_id="recon.waf_detection",
        category="security",
        severity="medium",
        severity_reason="WAF block",
        confidence="suspected",
        title="WAF detected on /login",
        description="WAF block observed",
        remediation="Ensure rules allow trusted traffic",
        evidence={"observation_ids": [obs_id_2]},
        fingerprint="fp_waf_123",
        occurrence_count=1,
    )
    geo_test_db.add(finding)
    await geo_test_db.commit()

    res = await WebScanGeographyService.get_scan_geography(geo_test_db, tenant_id, scan_id)
    assert res is not None
    assert len(res.relations) == 1
    rel = res.relations[0]
    assert rel.record_count == 2
    assert set(rel.status_codes) == {200, 403}
    assert set(rel.methods) == {"GET", "POST"}
    assert set(rel.supporting_observation_ids) == {obs_id_1, obs_id_2}
    assert rel.linked_finding_ids == [finding_id]


@pytest.mark.asyncio
async def test_geography_tenant_isolation(geo_test_db: AsyncSession):
    """Verify that requests across different tenants are strictly rejected (returns None)."""
    scan_id = str(uuid.uuid4())
    job = WebScanJobModel(
        id=scan_id,
        tenant_id="alpha_tenant",
        created_by="operator_alpha",
        raw_target="https://target.internal",
        normalized_target="https://target.internal",
        target_display="target.internal",
        status="completed",
        version=1,
    )
    geo_test_db.add(job)
    await geo_test_db.commit()

    # Query with mismatching tenant
    res = await WebScanGeographyService.get_scan_geography(geo_test_db, "beta_tenant", scan_id)
    assert res is None


def test_offline_geoip_unmapped_public_ip_returns_unknown():
    """Verify that unmapped public IPs return unknown status and None point rather than inventing fake coordinates."""
    # 204.79.197.200 is a public IP not in the offline known database
    point, level, status, basis, reason = OfflineGeoIPService.lookup_target_ip("204.79.197.200")
    assert point is None
    assert status == "unknown"
    assert basis == "unknown"
    assert level == "unknown"
    assert "not found" in reason.lower()

