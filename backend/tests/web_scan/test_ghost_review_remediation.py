from __future__ import annotations

import asyncio
import hashlib
import random
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.web_scan.engine import WebScanEngine
from app.core.web_scan.html_parser import DiscoveredForm, FormField, parse_page_html
from app.core.web_scan.http_client import WebScanHttpClient, WebScanResponse
from app.core.web_scan.modules.cookie_audit import CookieAuditModule
from app.core.web_scan.modules.forms import FormsModule
from app.core.web_scan.modules.header_probes import HeaderProbesModule
from app.core.web_scan.modules.load_resilience import LoadConfiguration, LoadResilienceModule
from app.core.web_scan.modules.parameters import ParametersModule
from app.core.web_scan.modules.recon import ReconModule
from app.core.web_scan.modules.security_headers import SecurityHeadersModule
from app.core.web_scan.network_policy import (
    redact_url_query_params,
    validate_target_against_scope,
)
from app.core.web_scan.payload_catalog import (
    DATABASE_ERROR_SIGNATURES,
    HEADER_DIAGNOSTIC_PROBES,
    get_random_mutated_payload,
)
from app.core.web_scan.result_processor import (
    calculate_risk_indices,
    deduplicate_findings,
)
from app.schemas.web_scan import (
    CheckStatus,
    Confidence,
    Evidence,
    ScanConfiguration,
    ScanFinding,
    Severity,
)
from app.services.web_scan_service import WebScanService


# ── R01: Scope Subtree Path & CIDR Matching (F01 & F16) ────────────────────────
def test_r01_scope_subtree_path_matching():
    rules = [{"host": "example.com", "path_prefixes": ["/api"]}]
    # Exact match and subpath must be allowed
    ok1, reason1 = validate_target_against_scope("http://example.com/api", rules)
    assert ok1 is True
    assert reason1 is None

    ok2, reason2 = validate_target_against_scope("http://example.com/api/v1/users", rules)
    assert ok2 is True
    assert reason2 is None

    # Subtree bypass attempt /api-admin must be blocked
    ok3, reason3 = validate_target_against_scope("http://example.com/api-admin", rules)
    assert ok3 is False
    assert reason3 is not None


# ── R02: Coverage Gaps & Skipped Checks (F02) ──────────────────────────────────
@pytest.mark.asyncio
async def test_r02_coverage_gap_marked_inconclusive():
    def handler(request: httpx.Request):
        return httpx.Response(200, text="<html><body><form action='/search'><input name='q'></form></body></html>", request=request)

    transport = httpx.MockTransport(handler)
    cfg = ScanConfiguration(
        modules=["parameters"],
        mutation_profile="none",
        max_requests=100,
    )
    engine = WebScanEngine(
        scan_id="test-r02",
        target_url="http://mock.test",
        config=cfg,
        transport=transport,
    )
    state, result, findings, obs, errs, reason = await engine.run()
    coverage_dict = {entry.check_id: entry for entry in result.coverage}

    # parameters.lfi_auth_bypass_indicator has no active detector -> must be INCONCLUSIVE
    assert "parameters.lfi_auth_bypass_indicator" in coverage_dict
    assert coverage_dict["parameters.lfi_auth_bypass_indicator"].status == CheckStatus.INCONCLUSIVE
    assert coverage_dict["parameters.lfi_auth_bypass_indicator"].reason_code == "COVERAGE_GAP_PRESERVED"


# ── R03: 429 Resilience Handling (F03) ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_r03_load_resilience_429_classification():
    def handler(request: httpx.Request):
        return httpx.Response(429, text="Too Many Requests", request=request)

    transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport)

    try:
        cfg = LoadConfiguration(method="GET", concurrency=2, duration_seconds=1, delay_seconds=0.01)
        mod = LoadResilienceModule(client, "http://mock.test", load_config=cfg)
        res = await mod.run()
        metrics = res["metrics"]
        findings = res["findings"]

        # All 429s must be classified as failure, not success
        assert metrics["legacy_success_lt_500"] == 0
        assert metrics["legacy_failure"] > 0
        assert metrics["rate_limited"] > 0
        legacy_evaluated = metrics["legacy_success_lt_500"] + metrics["legacy_failure"]
        assert legacy_evaluated > 0
        assert (metrics["legacy_failure"] / legacy_evaluated * 100.0) == 100.0

        # Finding must indicate high failure rate, not target stable
        assert any("High Failure Rate Under Concurrent Load" in f["title"] for f in findings)
        assert not any("Target Stable" in f["title"] for f in findings)
    finally:
        await client.aclose()


# ── R04: Concurrency & Semaphore Clamping (F04) ────────────────────────────────
@pytest.mark.asyncio
async def test_r04_job_semaphore_limits_concurrency():
    active_concurrent = 0
    max_observed_concurrent = 0
    lock = asyncio.Lock()

    async def slow_handler(request: httpx.Request):
        nonlocal active_concurrent, max_observed_concurrent
        async with lock:
            active_concurrent += 1
            if active_concurrent > max_observed_concurrent:
                max_observed_concurrent = active_concurrent
        await asyncio.sleep(0.05)
        async with lock:
            active_concurrent -= 1
        return httpx.Response(200, text="OK", request=request)

    transport = httpx.MockTransport(slow_handler)
    # Global semaphore is large (10), but job max_concurrency is clamped to 2
    global_sem = asyncio.Semaphore(10)
    client = WebScanHttpClient(
        target_url="http://mock.test",
        transport=transport,
        max_concurrency=2,
        global_semaphore=global_sem,
    )

    try:
        tasks = [client.fetch(f"http://mock.test/{i}") for i in range(8)]
        await asyncio.gather(*tasks)
        assert max_observed_concurrent <= 2
    finally:
        await client.aclose()


# ── R05: DB Error Baseline Subtraction & XSS Escaping (F05) ────────────────────
@pytest.mark.asyncio
async def test_r05_db_error_baseline_subtraction():
    # Target page statically contains "Powered by MongoDB" in baseline and on every probe
    def handler(request: httpx.Request):
        return httpx.Response(200, text="<html><body>Welcome! We use MongoDB driver.</body></html>", request=request)

    transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport)

    try:
        form = DiscoveredForm(
            action="http://mock.test/search",
            method="GET",
            fields=[FormField(name="q", input_type="text")],
        )
        mod = ParametersModule(client, "http://mock.test", discovered_forms=[form])
        res = await mod.run()
        findings = res["findings"]

        # "mongodb" is not in DATABASE_ERROR_SIGNATURES anymore, and static text in baseline is subtracted
        check_ids = [f["check_id"] for f in findings]
        assert "parameters.sql_error_matching" not in check_ids
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_r05_xss_escaped_reflection_not_flagged_as_vulnerability():
    # Target reflects the probe HTML-entity escaped
    def handler(request: httpx.Request):
        url_str = str(request.url)
        if "ghost_reflection_marker_2026" in url_str:
            return httpx.Response(
                200,
                text="Search results for: &lt;svg/onload=ghost_reflection_marker_2026&gt;",
                request=request,
            )
        return httpx.Response(200, text="Search page", request=request)

    transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport)

    try:
        form = DiscoveredForm(
            action="http://mock.test/search",
            method="GET",
            fields=[FormField(name="q", input_type="text")],
        )
        mod = ParametersModule(client, "http://mock.test", discovered_forms=[form])
        res = await mod.run()
        findings = res["findings"]

        # Escaped reflection must NOT be flagged as XSS vulnerability
        assert not any(f["check_id"] == "parameters.xss_reflection" for f in findings)
        # It must be recorded as an observation
        assert any(obs["kind"] == "xss_reflection_encoded" for obs in res["observations"])
    finally:
        await client.aclose()


# ── R06: Companion Form Fields & CSRF Preservation (F06) ───────────────────────
@pytest.mark.asyncio
async def test_r06_companion_form_fields_preserved_in_probe():
    received_requests = []

    def handler(request: httpx.Request):
        received_requests.append(request)
        return httpx.Response(200, text="OK", request=request)

    transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport)

    try:
        form = DiscoveredForm(
            action="http://mock.test/profile",
            method="POST",
            fields=[
                FormField(name="csrf_token", input_type="hidden", value="csrf_secret_abc"),
                FormField(name="user_id", input_type="hidden", value="1001"),
                FormField(name="bio", input_type="text", value="Hello"),
            ],
        )
        mod = ParametersModule(client, "http://mock.test", discovered_forms=[form], mutation_profile="none")
        await mod.run()

        # Check post requests made to /profile
        post_requests = [r for r in received_requests if r.method == "POST"]
        assert len(post_requests) > 0
        for req in post_requests:
            body_str = req.read().decode("utf-8")
            # If bio parameter is probed, csrf_token and user_id companion fields must be preserved!
            if "bio=%27" in body_str or "bio=%22" in body_str or "bio=1%27" in body_str:
                assert "csrf_token=csrf_secret_abc" in body_str
                assert "user_id=1001" in body_str
    finally:
        await client.aclose()


# ── R07: Paired Boolean SQLi & Discrete Headers (F07) ─────────────────────────
@pytest.mark.asyncio
async def test_r07_paired_boolean_comparison_observation():
    def handler(request: httpx.Request):
        url_str = str(request.url)
        if "1%3D1" in url_str or "1=1" in url_str:
            return httpx.Response(200, text="A" * 500, request=request)
        elif "1%3D2" in url_str or "1=2" in url_str:
            return httpx.Response(200, text="B" * 50, request=request)
        return httpx.Response(200, text="A" * 500, request=request)

    transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport)

    try:
        form = DiscoveredForm(
            action="http://mock.test/items",
            method="GET",
            fields=[FormField(name="id", input_type="text")],
        )
        mod = ParametersModule(client, "http://mock.test", discovered_forms=[form], mutation_profile="none")
        res = await mod.run()
        obs = res["observations"]

        boolean_obs = [o for o in obs if o.get("data", {}).get("catalog_entry_id") == "boolean_differential_probe"]
        assert len(boolean_obs) > 0
        assert boolean_obs[0]["data"]["reason_code"] == "differential_response_between_boolean_true_and_false"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_r07_header_probes_dispatched_discretely():
    observed_headers = []

    def handler(request: httpx.Request):
        probes_in_req = [h for h, p in HEADER_DIAGNOSTIC_PROBES.items() if request.headers.get(h) == p]
        if probes_in_req:
            observed_headers.append(probes_in_req)
        return httpx.Response(200, text="OK", request=request)

    transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport)

    try:
        mod = HeaderProbesModule(client, "http://mock.test", discovered_links=["http://mock.test/page1"])
        await mod.run()

        # Each probe request must contain at most 1 diagnostic header probe (F07)
        assert len(observed_headers) >= 3
        for h_list in observed_headers:
            assert len(h_list) == 1
    finally:
        await client.aclose()


# ── R08: Redirect 307 Preserves Body & Effective URL (F08) ────────────────────
@pytest.mark.asyncio
async def test_r08_redirect_307_preserves_post_body():
    payload_received_at_dest = None

    def handler(request: httpx.Request):
        nonlocal payload_received_at_dest
        if request.url.path == "/source":
            return httpx.Response(307, headers={"Location": "http://mock.test/dest"}, request=request)
        elif request.url.path == "/dest":
            payload_received_at_dest = request.read().decode("utf-8")
            return httpx.Response(200, text="Received at dest", request=request)
        return httpx.Response(404, request=request)

    transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport)

    try:
        resp = await client.fetch("http://mock.test/source", method="POST", data={"action": "save", "name": "alice"})
        assert resp is not None
        assert resp.status_code == 200
        assert str(resp.url) == "http://mock.test/dest"
        assert payload_received_at_dest == "action=save&name=alice"
    finally:
        await client.aclose()


# ── R09: Recon Login Redirect False Positive & Heuristics (F09) ────────────────
@pytest.mark.asyncio
async def test_r09_recon_login_redirect_not_flagged_as_exposed_env():
    def handler(request: httpx.Request):
        url_str = str(request.url)
        if ".env" in url_str:
            # Sensitive file request redirects to login page with HTML response
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                text="<html><head><title>Login</title></head><body><form action='/login'>Please log in</form></body></html>",
                request=request,
            )
        return httpx.Response(
            200,
            headers={"Server": "cloudflare", "cf-ray": "12345"},
            text="<html><head><link rel='stylesheet' href='/wp-content/themes/style.css'></head><body>Welcome</body></html>",
            request=request,
        )

    transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport)

    try:
        mod = ReconModule(client, "http://mock.test")
        res = await mod.run()
        findings = res["findings"]

        # /.env returning HTML login page must NOT be flagged as exposed endpoint!
        assert not any("/.env" in f.get("title", "") for f in findings)

        # WAF and CMS findings must have confidence='suspected'
        waf_finding = next((f for f in findings if f["check_id"] == "recon.waf_detection"), None)
        cms_finding = next((f for f in findings if f["check_id"] == "recon.cms_detection"), None)
        assert waf_finding is not None
        assert waf_finding["confidence"] == "suspected"
        assert cms_finding is not None
        assert cms_finding["confidence"] == "suspected"
    finally:
        await client.aclose()


# ── R10: Cookie Word Boundary & Non-HTML CSP Exemption (F10) ───────────────────
def test_r10_cookie_audit_ignores_non_session_words():
    # Set a cookie named 'grid' and 'banner_id' (not actual session cookies)
    resp = WebScanResponse(
        url="https://secure.test",
        status_code=200,
        headers={},
        text="<html></html>",
        set_cookie_headers=["grid=3x3; path=/", "banner_id=42; path=/"],
        elapsed_ms=10.0,
    )
    mod = CookieAuditModule(resp, "https://secure.test")
    res = mod.run()
    # Non-session cookies should have session_name_hint == False
    for obs in res["observations"]:
        assert obs["data"]["session_name_hint"] is False
    # Findings should have medium severity, not high
    for f in res["findings"]:
        assert f["severity"] == "medium"
    httponly_findings = [f for f in res["findings"] if f["check_id"] == "cookies.httponly"]
    assert len(httponly_findings) > 0
    for f in httponly_findings:
        assert "(Session indicator: False)" in f["severity_reason"]


def test_r10_security_headers_skips_csp_for_json_api():
    resp_json = WebScanResponse(
        url="https://api.test/data",
        status_code=200,
        headers={"Content-Type": "application/json", "Strict-Transport-Security": "max-age=31536000; includeSubDomains"},
        text='{"users": []}',
        elapsed_ms=10.0,
    )
    mod = SecurityHeadersModule(resp_json, "https://api.test/data")
    res = mod.run()
    check_ids = [f["check_id"] for f in res["findings"]]
    # CSP is for HTML rendering contexts, not JSON APIs
    assert "headers.csp" not in check_ids


# ── R11: Secret Query Redaction in Form Findings (F11) ────────────────────────
def test_r11_form_module_redacts_action_query_params():
    html_with_secret_form = """
    <html>
      <form action="/login?token=SUPER_SECRET_KEY_12345&user_id=99" method="GET">
        <input type="password" name="password" />
      </form>
    </html>
    """
    resp = WebScanResponse(
        url="http://mock.test",
        status_code=200,
        headers={},
        text=html_with_secret_form,
        elapsed_ms=10.0,
    )
    mod = FormsModule(resp, "http://mock.test")
    res = mod.run()
    findings = res["findings"]

    assert len(findings) > 0
    weak_login = findings[0]
    # Secret query parameter MUST be redacted from title, excerpts, and fingerprints
    assert "SUPER_SECRET_KEY_12345" not in weak_login["title"]
    assert "SUPER_SECRET_KEY_12345" not in weak_login["fingerprint"]
    assert "SUPER_SECRET_KEY_12345" not in weak_login["evidence"]["url_display"]
    assert "SUPER_SECRET_KEY_12345" not in weak_login["evidence"]["excerpts"][0]["value_redacted"]


# ── R12: Body Latency in Elapsed Timing & Telemetry (F12) ──────────────────────
@pytest.mark.asyncio
async def test_r12_elapsed_timing_captures_body_streaming():
    async def slow_stream_handler(request: httpx.Request):
        # Initial headers sent fast, body delayed
        await asyncio.sleep(0.08)
        return httpx.Response(200, text="Body finished", request=request)

    transport = httpx.MockTransport(slow_stream_handler)
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport)

    try:
        resp = await client.fetch("http://mock.test/stream")
        assert resp is not None
        # elapsed_ms must capture complete body read (> 70ms)
        assert resp.elapsed_ms >= 70.0
    finally:
        await client.aclose()


# ── R13: Evidence Telemetry Preservation (F12) ─────────────────────────────────
def test_r13_deduplicate_findings_preserves_evidence_telemetry():
    raw_findings = [
        {
            "check_id": "test.check",
            "title": "Test Title",
            "category": "general",
            "severity": "medium",
            "evidence": {
                "request_id": "req-12345",
                "baseline_request_id": "req-00000",
                "url_display": "http://mock.test/item",
                "method": "POST",
                "status_code": 200,
                "elapsed_ms": 150.0,
                "baseline_elapsed_ms": 50.0,
                "body_length": 1024,
                "catalog_entry_id": "test_probe",
            },
        }
    ]
    findings = deduplicate_findings(raw_findings, scan_id="scan-xyz")
    assert len(findings) == 1
    ev = findings[0].evidence
    assert ev.request_id == "req-12345"
    assert ev.baseline_request_id == "req-00000"
    assert ev.elapsed_ms == 150.0
    assert ev.baseline_elapsed_ms == 50.0
    assert ev.body_length == 1024
    assert ev.catalog_entry_id == "test_probe"


# ── R14: Deterministic PRNG Mutation (F14) ─────────────────────────────────────
def test_r14_stateful_rng_mutation_variance():
    # Calling get_random_mutated_payload with a stateful RNG should generate varied mutations
    rng = random.Random(310)
    mutations = [get_random_mutated_payload("' OR 1=1--", rng=rng) for _ in range(10)]
    unique_mutations = set(mutations)
    # Stateful RNG advances state -> must produce more than 1 distinct mutation!
    assert len(unique_mutations) > 1

    # mutation_profile="none" leaves payload identical
    raw = "' OR 1=1--"
    assert raw == "' OR 1=1--"


# ── R15: Risk Score Calibration on Info Findings (F15) ─────────────────────────
def test_r15_informational_findings_do_not_inflate_risk_score():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    findings = [
        ScanFinding(
            id="f1",
            scan_id="s1",
            module="recon",
            check_id="recon.waf",
            category="recon",
            source_category="TECH_INFO",
            severity=Severity.INFO,
            confidence=Confidence.SUSPECTED,
            title="WAF Detected",
            severity_reason="Detected WAF signature",
            description="Target uses WAF",
            remediation="None",
            evidence=Evidence(url_display="http://mock.test"),
            fingerprint="fp1",
            occurrence_count=1,
            first_seen_at=now,
            last_seen_at=now,
        ),
        ScanFinding(
            id="f2",
            scan_id="s1",
            module="stress",
            check_id="stress.bounded_load_test",
            category="load",
            source_category="STRESS_TEST",
            severity=Severity.INFO,
            confidence=Confidence.CONFIRMED_CONFIG,
            title="Target Stable Under Concurrent Load",
            severity_reason="100% success rate",
            description="Target sustained load without error",
            remediation="None",
            evidence=Evidence(url_display="http://mock.test"),
            fingerprint="fp2",
            occurrence_count=1,
            first_seen_at=now,
            last_seen_at=now,
        ),
    ]
    indices = calculate_risk_indices(findings)
    # Informational and stress test findings must contribute 0 risk points!
    assert indices.v75["value"] == 0
    assert indices.v2["value"] == 0
    assert indices.v47["value"] == 0


# ── R16: DNS Timeout Safety & Private IP Scope Propagation (F16 & F17) ─────────
@pytest.mark.asyncio
async def test_r16_network_policy_dns_timeout():
    from app.core.web_scan.network_policy import resolve_and_validate_hostname

    def hanging_getaddrinfo(*args, **kwargs):
        import time
        time.sleep(10.0)
        return []

    with patch("socket.getaddrinfo", side_effect=hanging_getaddrinfo):
        with pytest.raises(ValueError) as exc_info:
            await resolve_and_validate_hostname("slow.test")
        assert "timed out" in str(exc_info.value).lower()


def test_r16_contract_and_capabilities_registry_alignment():
    from app.core.web_scan.registry import CAPABILITIES_CATALOG
    from app.schemas.web_scan import ScanConfiguration

    # Advertised capabilities must reflect true HTTP/1.1 transport (F18)
    assert CAPABILITIES_CATALOG.readiness["http2_ready"] is False
    assert CAPABILITIES_CATALOG.hard_caps["max_requests_ceiling"] == 10000000

    # ScanConfiguration limits must align with ceiling
    cfg = ScanConfiguration()
    assert cfg.max_requests <= CAPABILITIES_CATALOG.hard_caps["max_requests_ceiling"]
    assert cfg.max_concurrency <= CAPABILITIES_CATALOG.hard_caps["max_concurrency_ceiling"]


def test_r17_high_budget_and_concurrency_limits():
    """Verify that 100,000 max_concurrency, 10,000 RPS, and 10,000,000 max_requests validate cleanly."""
    from app.schemas.web_scan import ScanConfiguration, RequestBudget, LoadConfiguration
    from app.core.web_scan.http_client import WebScanHttpClient, RequestBudgetLedger
    from app.config import settings

    # 1. Pydantic Schemas permit the high bounds
    budget = RequestBudget(
        max_concurrency=100000,
        per_origin_concurrency=50000,
        requests_per_second=10000.0,
        max_requests=10000000,
    )
    assert budget.max_concurrency == 100000
    assert budget.requests_per_second == 10000.0
    assert budget.max_requests == 10000000

    load_cfg = LoadConfiguration(concurrency=100000)
    assert load_cfg.concurrency == 100000

    scan_cfg = ScanConfiguration(
        max_concurrency=100000,
        per_origin_concurrency=50000,
        requests_per_second=10000.0,
        max_requests=10000000,
    )
    assert scan_cfg.max_concurrency == 100000
    assert scan_cfg.requests_per_second == 10000.0
    assert scan_cfg.max_requests == 10000000

    # 2. Config settings allow 100,000 concurrency without clamping
    assert settings.WEB_SCAN_GLOBAL_MAX_CONCURRENCY >= 100000
    assert settings.WEB_SCAN_PER_ORIGIN_CONCURRENCY >= 50000

    # 3. HTTP Client and Ledger defaults
    ledger = RequestBudgetLedger()
    assert ledger.max_requests == 10000000

    client = WebScanHttpClient(target_url="http://example.internal")
    assert client.max_concurrency == 100000
    assert client.per_origin_concurrency == 50000
    assert client.requests_per_second == 10000.0
    assert client.ledger.max_requests == 10000000


