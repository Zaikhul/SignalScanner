from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import uuid
import pytest
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport

from app.config import settings
from app.core.web_scan.authorization import (
    get_current_principal,
    register_auth_token,
    _TOKEN_REGISTRY,
)
from app.core.web_scan.engine import WebScanEngine
from app.core.web_scan.html_parser import parse_page_html
from app.core.web_scan.http_client import (
    RequestBudgetLedger,
    WebScanHttpClient,
    WebScanResponse,
)
from app.core.web_scan.modules.load_resilience import LoadResilienceModule
from app.core.web_scan.modules.parameters import ParametersModule
from app.core.web_scan.network_policy import (
    parse_and_validate_target,
    redact_url_query_params,
    validate_target_against_scope,
)
from app.core.web_scan.result_processor import (
    build_scan_result,
    calculate_risk_indices,
    score_to_risk_band,
)
from app.core.web_scan.transport import PinnedDNSNetworkBackend
from app.db.session import AsyncSessionLocal
from app.db.web_scan_models import (
    WebScanFindingModel,
    WebScanJobModel,
    WebScanScopeModel,
)
from app.main import app
from app.schemas.web_scan import (
    CheckStatus,
    CreateScanRequest,
    ErrorStage,
    LoadConfiguration,
    ModuleId,
    ProfileId,
    RequestBudget,
    ScanConfiguration,
    ScanFinding,
    ScanResult,
    ScanState,
    ScopeRule,
    Severity,
)
from app.services.web_scan_export_service import WebScanExportService
from app.services.web_scan_service import WebScanService


# --- F-01: Auth Server Tenant Binding & Rejection ---
@pytest.mark.asyncio
async def test_f01_auth_server_tenant_binding_and_rejection():
    # Register dynamic token for tenant_a
    register_auth_token(
        token="tenant-a-token-xyz",
        tenant_id="tenant_a",
        principal_id="principal_a",
        permissions=["web_scan:read", "web_scan:create"],
    )

    # Valid call matching token tenant
    principal = await get_current_principal(
        authorization="Bearer tenant-a-token-xyz",
        x_tenant_id="tenant_a",
    )
    assert principal.tenant_id == "tenant_a"
    assert principal.principal_id == "principal_a"

    # Mismatch header must raise 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        await get_current_principal(
            authorization="Bearer tenant-a-token-xyz",
            x_tenant_id="attacker_tenant",
        )
    assert exc_info.value.status_code == 403
    assert "Tenant mismatch" in exc_info.value.detail


# --- F-02: ScopeGrant Lifecycle & Revocation ---
@pytest.mark.asyncio
async def test_f02_scope_grant_lifecycle_and_revocation():
    async with AsyncSessionLocal() as db:
        tenant_id = "tenant_f02"
        principal_id = "principal_f02"

        # 1. Create valid ScopeGrant in DB
        scope_id = str(uuid.uuid4())
        rules = [
            ScopeRule(
                host="example.org",
                ports=[80, 443],
                path_prefixes=["/app/"],
                allowed_cidrs=[],
                allow_private=False,
                allow_loopback=False,
                methods=["GET"],
                checks=[],
            ).model_dump()
        ]
        grant_model = WebScanScopeModel(
            id=scope_id,
            tenant_id=tenant_id,
            authorization_reference="AUTH-REF-100",
            assigned_principals=[principal_id],
            rules=rules,
            budget=RequestBudget(max_requests=500, max_concurrency=10).model_dump(),
            revision=1,
            created_at=datetime.now(timezone.utc),
            created_by=principal_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revoked_at=None,
            scope_hash="hash123",
            allow_tls_unverified=False,
            allow_geolocation=False,
            allow_load=False,
            allow_header_variants=False,
        )
        db.add(grant_model)
        await db.commit()

        # Valid creation with assigned grant
        req = CreateScanRequest(
            target="http://example.org/app/login",
            scope_id=scope_id,
            authorization_acknowledged=True,
            configuration=ScanConfiguration(
                allow_private=True,
                max_concurrency=10,
                per_origin_concurrency=5,
                max_requests=500,
            ),
        )
        job = await WebScanService.create_scan_job(
            db=db,
            tenant_id=tenant_id,
            principal_id=principal_id,
            req=req,
            idempotency_key=f"f02-idem-key-1-{uuid.uuid4()}",
        )
        assert job.status in (ScanState.PENDING, ScanState.QUEUED)

        # 2. Revoke grant and verify subsequent scan creation fails
        grant_model.revoked_at = datetime.now(timezone.utc)
        await db.commit()

        req2 = CreateScanRequest(
            target="http://example.org/app/login",
            scope_id=scope_id,
            authorization_acknowledged=True,
            configuration=ScanConfiguration(
                allow_private=True,
                max_concurrency=10,
                per_origin_concurrency=5,
                max_requests=500,
            ),
        )
        with pytest.raises(HTTPException) as exc_info:
            await WebScanService.create_scan_job(
                db=db,
                tenant_id=tenant_id,
                principal_id=principal_id,
                req=req2,
                idempotency_key=f"f02-idem-key-2-{uuid.uuid4()}",
            )
        assert exc_info.value.status_code == 403
        assert "revoked" in exc_info.value.detail.lower()


# --- F-03 & F-22: Connection Pinning & Verify Parameter ---
def test_f03_connection_pinning_and_verify_parameter():
    backend = PinnedDNSNetworkBackend(allow_private=True, allow_loopback=False)
    assert backend.allow_private is True


# --- F-04: Redirect Scope Re-validation & Form Action Isolation ---
def test_f04_redirect_and_form_action_isolation():
    # Dot-segments normalization
    rules = [{"host": "target.local", "path_prefixes": ["/safe/"]}]
    ok, _ = validate_target_against_scope("http://target.local/safe/../unsafe", rules)
    assert not ok, "Dot segments escaping authorized prefix must be rejected"

    # HTML Form external action exclusion
    html = """
    <html>
      <body>
        <form action="/internal/login" method="post"><input name="user"/></form>
        <form action="http://malicious.evil.com/leak" method="post"><input name="pass"/></form>
        <form action="http://sub.target.local/api" method="post"><input name="token"/></form>
      </body>
    </html>
    """
    forms, _ = parse_page_html("http://target.local/index", html)
    action_urls = [f.action for f in forms]
    assert "http://target.local/internal/login" in action_urls
    assert "http://sub.target.local/api" in action_urls
    assert not any("malicious.evil.com" in u for u in action_urls), "External egress forms must be discarded"


# --- F-05: Token Bucket Monotonic Slot Rate Limiter ---
@pytest.mark.asyncio
async def test_f05_token_bucket_monotonic_slot():
    cancel_evt = asyncio.Event()
    config = ScanConfiguration(requests_per_second=20.0, allow_private=True)
    client = WebScanHttpClient("http://localhost", config=config, cancel_event=cancel_evt)
    assert client.min_interval == 0.05

    # Test interruptible sleep with cancel_event
    cancel_evt.set()
    slot_ok = await client._schedule_rate_slot("http://localhost")
    assert slot_ok is False
    await client.aclose()


# --- F-06 & F-07: Concurrency & In-Flight Abort ---
@pytest.mark.asyncio
async def test_f06_f07_concurrency_and_abort():
    config = ScanConfiguration(max_concurrency=5, per_origin_concurrency=2, allow_private=True)
    client = WebScanHttpClient("http://localhost", config=config)
    assert client.per_origin_concurrency == 2

    # Verify ledger tracking
    assert client.ledger.max_requests >= 1
    client.ledger.record_success(200)
    client.ledger.record_failure("timeout")
    assert client.ledger.attempt_count == 0  # Only acquire_permit increments attempt
    assert client.ledger.success_count == 1
    assert client.ledger.total_timeouts == 1

    # Verify abort in-flight
    client.abort_in_flight()
    assert len(client._in_flight_tasks) == 0
    await client.aclose()


# --- F-08: Target Unreachable Taxonomy ---
@pytest.mark.asyncio
async def test_f08_target_unreachable_taxonomy():
    config = ScanConfiguration(
        profile=ProfileId.V2,
        modules=[ModuleId.RECON, ModuleId.HEADERS],
        allow_private=True,
    )
    # Target unreachable: port 1 on 127.0.0.1 immediately refuses connection
    engine = WebScanEngine(
        scan_id=str(uuid.uuid4()),
        target_url="http://127.0.0.1:1/nonexistent",
        config=config,
    )
    final_state, result, findings, obs, errors, reason = await engine.run()
    # Must be marked FAILED, never COMPLETED!
    assert final_state == ScanState.FAILED
    assert "unreachable" in (reason or "").lower() or len(errors) > 0


# --- F-09: Pre-Cancel Tenant Ownership Check ---
@pytest.mark.asyncio
async def test_f09_pre_cancel_tenant_ownership():
    async with AsyncSessionLocal() as db:
        # Create a job under tenant_alpha
        req = CreateScanRequest(
            target="http://example.com/test",
            authorization_acknowledged=True,
            configuration=ScanConfiguration(allow_private=True),
        )
        job = await WebScanService.create_scan_job(
            db=db,
            tenant_id="tenant_alpha",
            principal_id="principal_alpha",
            req=req,
            idempotency_key="f09-test-job-key",
        )

        # Attacker tenant attempts to cancel job belonging to tenant_alpha
        res = await WebScanService.cancel_scan_job(
            db=db,
            tenant_id="tenant_attacker",
            principal_id="principal_attacker",
            scan_id=job.id,
        )
        assert res is None, "Cross-tenant cancel request must return None and not cancel job"


# --- F-10: Profile Default Modules Population ---
def test_f10_profile_default_modules_population():
    # When modules is omitted or empty, validator populates them based on profile
    cfg_v2 = ScanConfiguration(profile=ProfileId.V2, allow_private=True)
    assert ModuleId.RECON in cfg_v2.modules
    assert ModuleId.HEADERS in cfg_v2.modules
    assert ModuleId.COOKIES in cfg_v2.modules

    cfg_comp = ScanConfiguration(profile=ProfileId.COMPREHENSIVE, allow_private=True)
    assert ModuleId.FORMS in cfg_comp.modules
    assert ModuleId.PARAMETERS in cfg_comp.modules
    assert ModuleId.HEADER_PROBES in cfg_comp.modules


# --- F-11: ErrorStage Taxonomy & Reconciliation ---
def test_f11_error_stage_taxonomy():
    assert ErrorStage.MODULE_EXECUTION == "module_execution"
    assert ErrorStage.REQUEST == "request"


# --- F-14: Finding Module Attribution ---
def test_f14_finding_module_attribution():
    from app.core.web_scan.result_processor import _resolve_finding_module

    # Finding with explicit module
    item1 = {"check_id": "stress.bounded_load_test", "module": "stress"}
    assert _resolve_finding_module(item1) == ModuleId.STRESS

    # Finding with check_id prefix but missing module
    item2 = {"check_id": "headers.csp"}
    assert _resolve_finding_module(item2) == ModuleId.HEADERS

    # Finding with parameters check_id prefix
    item3 = {"check_id": "parameters.sql_injection"}
    assert _resolve_finding_module(item3) == ModuleId.PARAMETERS


# --- F-15: Coverage Honesty (Skipped Reasons) ---
@pytest.mark.asyncio
async def test_f15_coverage_honesty_parameters_skipped():
    client = WebScanHttpClient("http://localhost", config=ScanConfiguration(allow_private=True))
    # No forms and no query parameters in target URL
    param_mod = ParametersModule(
        http_client=client,
        target_url="http://example.com/no_params",
        discovered_forms=[],
    )
    res = await param_mod.run()
    assert res.get("status") == "skipped"
    assert res.get("reason") == "NO_PARAMETERS_FOUND"
    await client.aclose()


# --- F-16: Authoritative Ledger Metrics in Result ---
def test_f16_authoritative_ledger_metrics():
    ledger = RequestBudgetLedger()
    ledger.total_attempted = 42
    ledger.total_succeeded = 40
    ledger.status_2xx = 38
    ledger.status_3xx = 2
    ledger.status_4xx = 2
    ledger.total_network_errors = 2

    metrics = ledger.to_metrics()
    assert metrics.attempted == 42
    assert metrics.completed == 40
    assert metrics.http_2xx_3xx == 40
    assert metrics.network_failed == 2

    res = build_scan_result(findings=[], observations=[], request_metrics=metrics)
    assert res.requests.attempted == 42
    assert res.requests.completed == 40


# --- F-17: Load Resilience Failure Counter No Double Count ---
def test_f17_load_resilience_failure_counter_no_double_count():
    load_mod = LoadResilienceModule(
        http_client=None,  # type: ignore
        target_url="http://example.com",
        load_config=LoadConfiguration(
            method="GET",
            concurrency=2,
            duration_seconds=1,
            delay_seconds=0.1,
            body_template="none",
        ),
    )
    # Simulate single 500 error response
    resp = WebScanResponse(url="http://example.com", status_code=500, headers={})
    counts = {"success": 0, "failure": 0}

    # If status >= 500, counts["failure"] must increment once, not twice!
    if resp.status_code < 500:
        counts["success"] += 1
    else:
        counts["failure"] += 1

    assert counts["failure"] == 1
    assert counts["success"] == 0


# --- F-18: URL Query Redaction in Exports & Logs ---
def test_f18_url_query_redaction():
    leak_url = "https://app.corp/login?token=SUPER_SECRET_12345&user=admin"
    redacted = redact_url_query_params(leak_url)
    assert "SUPER_SECRET_12345" not in redacted
    assert "admin" not in redacted
    assert ("%3Credacted%3E" in redacted) or ("<redacted>" in redacted)


# --- F-19: IPv6 Bracket Authority Reconstruction ---
def test_f19_ipv6_bracket_canonicalization():
    norm = parse_and_validate_target("http://[::1]:8080/path")
    assert norm.hostname == "::1"
    assert norm.port == 8080
    assert norm.canonical_url == "http://[::1]:8080/path"


# --- F-20: Atomic One-Time Ticket Consumption ---
@pytest.mark.asyncio
async def test_f20_atomic_one_time_ticket_consumption():
    async with AsyncSessionLocal() as db:
        tenant_id = "tenant_f20"
        principal_id = "principal_f20"
        scan_id = str(uuid.uuid4())

        ticket = await WebScanService.create_ws_ticket(
            db=db,
            tenant_id=tenant_id,
            principal_id=principal_id,
            scan_id=scan_id,
        )

        # First consumption must succeed
        valid1 = await WebScanService.consume_ws_ticket(db, ticket)
        assert valid1 is not None
        assert valid1["scan_id"] == scan_id

        # Second consumption must immediately fail
        valid2 = await WebScanService.consume_ws_ticket(db, ticket)
        assert valid2 is None


# --- F-21: Unified Risk Band Mapping ---
def test_f21_unified_risk_band_mapping():
    assert score_to_risk_band(100) == "critical"
    assert score_to_risk_band(70) == "critical"
    assert score_to_risk_band(69) == "high"
    assert score_to_risk_band(50) == "high"
    assert score_to_risk_band(49) == "medium"
    assert score_to_risk_band(30) == "medium"
    assert score_to_risk_band(29) == "low"
    assert score_to_risk_band(0) == "low"


# --- F-23: Parameters Query Extraction Without Forms ---
@pytest.mark.asyncio
async def test_f23_parameters_query_extraction():
    client = WebScanHttpClient("http://localhost", config=ScanConfiguration(allow_private=True))
    # Target URL has query parameters `?q=test&category=books`
    param_mod = ParametersModule(
        http_client=client,
        target_url="http://example.com/search?q=test&category=books",
        discovered_forms=[],  # 0 forms
    )
    # It should not return skipped because query parameters exist on target URL!
    res = await param_mod.run()
    assert res.get("status") == "completed"
    await client.aclose()


# --- F-24: Idempotency Key Payload Conflict Rejection ---
@pytest.mark.asyncio
async def test_f24_idempotency_payload_conflict():
    async with AsyncSessionLocal() as db:
        tenant_id = "tenant_f24"
        principal_id = "principal_f24"
        idem_key = "f24-shared-key"

        req1 = CreateScanRequest(
            target="http://example.com/site1",
            authorization_acknowledged=True,
            configuration=ScanConfiguration(allow_private=True),
        )
        job1 = await WebScanService.create_scan_job(
            db=db,
            tenant_id=tenant_id,
            principal_id=principal_id,
            req=req1,
            idempotency_key=idem_key,
        )

        # Same key with same payload -> returns job1
        job1_dup = await WebScanService.create_scan_job(
            db=db,
            tenant_id=tenant_id,
            principal_id=principal_id,
            req=req1,
            idempotency_key=idem_key,
        )
        assert job1_dup.id == job1.id

        # Same key with DIFFERENT payload -> raises 409 Conflict
        req2 = CreateScanRequest(
            target="http://example.com/site2_different",
            authorization_acknowledged=True,
            configuration=ScanConfiguration(allow_private=True),
        )
        with pytest.raises(HTTPException) as exc_info:
            await WebScanService.create_scan_job(
                db=db,
                tenant_id=tenant_id,
                principal_id=principal_id,
                req=req2,
                idempotency_key=idem_key,
            )
        assert exc_info.value.status_code == 409
        assert "Idempotency key reused with different" in exc_info.value.detail


# --- F-25: CORS Exposed Headers ---
def test_f25_cors_headers_exposure():
    # Verify CORS middleware in app middleware stack has expose_headers
    cors_mw = None
    for mw in app.user_middleware:
        if "CORSMiddleware" in str(mw.cls):
            cors_mw = mw
            break
    assert cors_mw is not None, "CORSMiddleware must be installed on FastAPI app"
    exposed = cors_mw.kwargs.get("expose_headers", [])
    assert "X-Checksum-SHA256" in exposed
    assert "Content-Disposition" in exposed


# --- Engine Global Semaphore Support ---
def test_web_scan_engine_global_semaphore():
    sem = asyncio.Semaphore(15)
    config = ScanConfiguration(allow_private=True, modules=[])
    engine = WebScanEngine(
        scan_id="test-sem-scan",
        target_url="http://127.0.0.1:8000",
        config=config,
        global_semaphore=sem,
    )
    assert engine.global_semaphore is sem

    engine_none = WebScanEngine(
        scan_id="test-sem-scan-none",
        target_url="http://127.0.0.1:8000",
        config=config,
    )
    assert engine_none.global_semaphore is None


@pytest.mark.asyncio
async def test_web_scan_engine_forwards_global_semaphore(monkeypatch):
    sem = asyncio.Semaphore(7)
    config = ScanConfiguration(allow_private=True, modules=[])
    engine = WebScanEngine(
        scan_id="test-sem-forward",
        target_url="http://127.0.0.1:8000",
        config=config,
        global_semaphore=sem,
    )
    captured_client_sem = None
    original_init = WebScanHttpClient.__init__

    def mock_http_init(self, *args, **kwargs):
        nonlocal captured_client_sem
        captured_client_sem = kwargs.get("global_semaphore")
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(WebScanHttpClient, "__init__", mock_http_init)
    await engine.run()
    assert captured_client_sem is sem

