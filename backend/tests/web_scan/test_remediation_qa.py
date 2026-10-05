from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import AsyncBaseTransport, Request, Response

from app.config import Settings
from app.core.channel_health_engine import ChannelHealthEngine
from app.core.web_scan.engine import WebScanEngine
from app.core.web_scan.http_client import WebScanHttpClient
from app.core.web_scan.modules.security_headers import SecurityHeadersModule
from app.core.web_scan.network_policy import redact_url_query_params
from app.db.session import AsyncSessionLocal
from app.db.web_scan_models import WebScanJobModel, WebScanScopeModel
from app.schemas.web_scan import (
    CreateScanRequest,
    CreateScopeGrant,
    Evidence,
    ModuleId,
    ScanConfiguration,
    ScanState,
)
from app.services.web_scan_scheduler import WebScanScheduler
from app.services.web_scan_service import WebScanService


class MockTransport(AsyncBaseTransport):
    def __init__(self, handler=None):
        self.handler = handler or self.default_handler

    async def default_handler(self, request: Request) -> Response:
        return Response(200, json={"status": "ok"}, headers={"content-type": "application/json"})

    async def handle_async_request(self, request: Request) -> Response:
        resp = await self.handler(request)
        resp.request = request
        return resp


@pytest_asyncio.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


@pytest.mark.asyncio
async def test_qa_01_production_credential_validation():
    """QA-01: Settings rejects default dev credentials in production mode."""
    with pytest.raises(ValueError, match="Insecure default or empty API_AUTH_TOKEN"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-strong-secret-key-that-is-not-default-at-all",
            TENANT_SALT="a-strong-salt-that-is-not-default",
            API_AUTH_TOKEN="signal-scanner-dev-token-2026",
            COLLECTOR_API_KEY="valid-custom-key-12345",
        )

    with pytest.raises(ValueError, match="Insecure default or empty COLLECTOR_API_KEY"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-strong-secret-key-that-is-not-default-at-all",
            TENANT_SALT="a-strong-salt-that-is-not-default",
            API_AUTH_TOKEN="valid-custom-api-token-12345",
            COLLECTOR_API_KEY="collector-dev-key-2026",
        )


@pytest.mark.asyncio
async def test_qa_02_scope_budget_and_revocation(db_session):
    """QA-02: Scope grant enforces rate limit budget and revocation."""
    from app.schemas.web_scan import RequestBudget, ScopeRule

    # 1. Create scope grant with 1.0 RPS limit
    grant = await WebScanService.create_scope_grant(
        db=db_session,
        tenant_id="test_tenant",
        principal_id="test_principal",
        req=CreateScopeGrant(
            authorization_reference="AUTH-REF-TEST-01",
            rules=[ScopeRule(host="allowed.local", path_prefixes=["/api/"], allow_private=True, allow_loopback=True)],
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            budget=RequestBudget(requests_per_second=1.0, max_concurrency=2),
        ),
    )

    # 2. Creating scan with 50.0 RPS requests should either be rejected or clamped to 1.0
    with pytest.raises(HTTPException) as exc_info:
        await WebScanService.create_scan_job(
            db=db_session,
            tenant_id="test_tenant",
            principal_id="test_principal",
            req=CreateScanRequest(
                target="https://allowed.local/api/test",
                scope_id=grant.id,
                configuration=ScanConfiguration(requests_per_second=50.0, max_concurrency=2, per_origin_concurrency=2, max_requests=100),
                authorization_acknowledged=True,
            ),
        )
    assert exc_info.value.status_code == 403
    assert "exceeds scope grant budget limit" in exc_info.value.detail

    # 3. Create job with 1.0 RPS (valid)
    job = await WebScanService.create_scan_job(
        db=db_session,
        tenant_id="test_tenant",
        principal_id="test_principal",
        req=CreateScanRequest(
            target="https://allowed.local/api/test",
            scope_id=grant.id,
            configuration=ScanConfiguration(requests_per_second=1.0, max_concurrency=2, per_origin_concurrency=2, max_requests=100),
            authorization_acknowledged=True,
        ),
    )
    assert job.effective_configuration.requests_per_second <= 1.0

    # 4. Revoke the scope grant
    await WebScanService.revoke_scope_grant(
        db=db_session,
        tenant_id="test_tenant",
        principal_id="test_principal",
        scope_id=grant.id,
    )

    # 5. Run scheduler execution wrapper and verify revocation is caught
    scheduler = WebScanScheduler()
    cancel_event = asyncio.Event()
    await scheduler._execute_job_wrapper(job.id, cancel_event)

    updated_job = await db_session.get(WebScanJobModel, job.id)
    assert updated_job.status == ScanState.CANCELLED.value
    assert "revoked" in (updated_job.status_reason or "").lower()


@pytest.mark.asyncio
async def test_qa_02_redirect_outside_scope():
    """QA-02: Redirect hop to target outside scope is rejected by HTTP client."""
    scope_rules = [{"host": "allowed.local", "path_prefixes": ["/api/"]}]

    async def redirect_handler(request: Request) -> Response:
        if "allowed.local" in request.url.host:
            return Response(302, headers={"Location": "https://unauthorized.external.com/secret"})
        return Response(200, text="Forbidden access")

    transport = MockTransport(handler=redirect_handler)
    client = WebScanHttpClient(
        target_url="https://allowed.local/api/test",
        transport=transport,
        scope_rules=scope_rules,
    )

    resp = await client.fetch("https://allowed.local/api/test")
    # Redirect target is outside scope, so request must fail/be blocked
    assert resp is None
    assert any(err.get("code") == "SCOPE_VIOLATION" for err in client.recorded_errors)


@pytest.mark.asyncio
async def test_qa_06_scheduler_no_deadlock_concurrency_one():
    """QA-06: Concurrency capacity 1 does not cause deadlock between scheduler and HTTP client."""
    async def mock_handler(request: Request) -> Response:
        return Response(
            200,
            text="<html><head></head><body><h1>Scan Target</h1></body></html>",
            headers={
                "content-type": "text/html",
                "content-security-policy": "default-src 'self'",
                "strict-transport-security": "max-age=31536000",
                "x-frame-options": "DENY",
                "x-content-type-options": "nosniff",
            },
        )

    transport = MockTransport(handler=mock_handler)
    global_sem = asyncio.Semaphore(1)

    engine = WebScanEngine(
        scan_id="test_concurrency_one",
        target_url="https://example.com/test",
        config=ScanConfiguration(
            modules=[ModuleId.HEADERS],
            max_concurrency=1,
            per_origin_concurrency=1,
        ),
        transport=transport,
        global_semaphore=global_sem,
    )

    # This should complete rapidly without deadlock
    final_state, result, findings, observations, errors, status_reason = await asyncio.wait_for(
        engine.run(), timeout=5.0
    )
    assert final_state == ScanState.COMPLETED


@pytest.mark.asyncio
async def test_qa_08_deadline_and_cancellation():
    """QA-08: Job deadline and cancellation stop waiting/running requests."""
    # 1. Deadline exceeded
    client_expired = WebScanHttpClient(
        target_url="https://example.com/",
        job_timeout_seconds=0,  # immediate deadline expiration
    )
    client_expired.job_deadline = 0.0  # past deadline
    resp = await client_expired.fetch("https://example.com/test")
    assert resp is None
    assert any(err.get("code") == "JOB_DEADLINE_EXCEEDED" for err in client_expired.recorded_errors)

    # 2. Cancel event set
    cancel_evt = asyncio.Event()
    cancel_evt.set()
    client_cancelled = WebScanHttpClient(
        target_url="https://example.com/",
        cancel_event=cancel_evt,
    )
    resp2 = await client_cancelled.fetch("https://example.com/test")
    assert resp2 is None


@pytest.mark.asyncio
async def test_qa_09_sensitive_query_redaction():
    """QA-09: Sensitive query parameters in response URLs are redacted on Evidence."""
    sensitive_url = "https://internal.test.local/auth/callback?token=SECRET_BEARER_TOKEN_9999&api_key=XYZ123"

    # Direct helper test
    redacted = redact_url_query_params(sensitive_url)
    assert "SECRET_BEARER_TOKEN_9999" not in redacted
    assert "<redacted>" in redacted or "%3Credacted%3E" in redacted

    # Evidence model validator test
    ev = Evidence(
        url_display=sensitive_url,
        method="GET",
        status_code=200,
    )
    assert "SECRET_BEARER_TOKEN_9999" not in ev.url_display

    # Security headers module test
    resp = Response(
        200,
        request=Request("GET", sensitive_url),
        headers={"content-type": "text/html"},
    )
    from app.core.web_scan.http_client import WebScanResponse
    web_resp = WebScanResponse(
        url=sensitive_url,
        status_code=200,
        headers={"content-type": "text/html"},
    )
    mod = SecurityHeadersModule(root_response=web_resp, target_url=sensitive_url)
    res = mod.run()
    for f in res["findings"]:
        ev_dict = f.get("evidence", {})
        assert "SECRET_BEARER_TOKEN_9999" not in ev_dict.get("url_display", "")


@pytest.mark.asyncio
async def test_qa_10_http_status_mapping(db_session):
    """QA-10: Service validation errors preserve 4xx HTTP status and do not convert to 500."""
    from app.api.v1.web_scans import create_web_scan
    from app.core.web_scan.authorization import OperatorPrincipal

    principal = OperatorPrincipal(
        principal_id="test_op",
        tenant_id="default_tenant",
        permissions=["web_scan:execute"],
    )

    req = CreateScanRequest(
        target="https://example.com",
        scope_id="non_existent_scope_12345",
        authorization_acknowledged=True,
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_web_scan(
            req=req,
            idempotency_key=None,
            principal=principal,
            db=db_session,
        )
    # Must be 404 Not Found, not 500
    assert exc_info.value.status_code == 404


def test_qa_13_channel_health_temporal_instability_multiple_aps():
    """QA-13: Two stable APs with different RSSIs do not incur temporal instability penalty."""
    engine = ChannelHealthEngine()

    # Two APs on channel 1, measured across 3 cycles:
    # AP1 has constant -50 dBm
    # AP2 has constant -80 dBm
    measurements = [
        {"target_id": "ap_01", "channel": 1, "band": "2.4GHz", "signal_value": -50.0, "sequence": 1},
        {"target_id": "ap_02", "channel": 1, "band": "2.4GHz", "signal_value": -80.0, "sequence": 1},
        {"target_id": "ap_01", "channel": 1, "band": "2.4GHz", "signal_value": -50.0, "sequence": 2},
        {"target_id": "ap_02", "channel": 1, "band": "2.4GHz", "signal_value": -80.0, "sequence": 2},
        {"target_id": "ap_01", "channel": 1, "band": "2.4GHz", "signal_value": -50.0, "sequence": 3},
        {"target_id": "ap_02", "channel": 1, "band": "2.4GHz", "signal_value": -80.0, "sequence": 3},
    ]

    targets = [
        {"target_id": "ap_01", "channel": 1, "band": "2.4GHz", "signal_value": -50.0},
        {"target_id": "ap_02", "channel": 1, "band": "2.4GHz", "signal_value": -80.0},
    ]

    channel_items, quality_flags = engine.evaluate_channels(
        band="2.4GHz",
        channel_width_mhz=20,
        targets=targets,
        measurements=measurements,
    )

    ch1_item = next((item for item in channel_items if item.channel == 1), None)
    assert ch1_item is not None
    # Temporal instability penalty should be 0.0 because both APs are completely steady over time
    assert ch1_item.components.temporal_instability.value == 0.0
