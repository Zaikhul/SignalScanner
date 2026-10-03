import asyncio
import httpx
import pytest

from app.core.web_scan.html_parser import DiscoveredField, DiscoveredForm
from app.core.web_scan.http_client import WebScanHttpClient, WebScanResponse
from app.core.web_scan.modules.cookie_audit import CookieAuditModule
from app.core.web_scan.modules.forms import FormsModule
from app.core.web_scan.modules.header_probes import HeaderProbesModule
from app.core.web_scan.modules.load_resilience import LoadResilienceModule
from app.core.web_scan.modules.parameters import ParametersModule
from app.core.web_scan.modules.recon import ReconModule
from app.core.web_scan.modules.security_headers import SecurityHeadersModule
from app.schemas.web_scan import LoadConfiguration


@pytest.mark.asyncio
async def test_recon_module_passive_and_active():
    def handler(request: httpx.Request):
        url_str = str(request.url)
        if "robots.txt" in url_str:
            return httpx.Response(200, text="User-agent: *\nDisallow: /admin", request=request)
        if "admin" in url_str:
            return httpx.Response(200, text="Admin Portal Login", request=request)
        # Root response with Cloudflare and WordPress signature
        return httpx.Response(
            200,
            text="<html><head><link rel='stylesheet' href='/wp-content/themes/style.css'></head><body>cf-ray active</body></html>",
            headers={"Server": "cloudflare", "cf-ray": "8472917abcd"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport)

    try:
        recon = ReconModule(client, "http://mock.test")
        res = await recon.run()
        findings = res["findings"]
        check_ids = [f["check_id"] for f in findings]

        assert "recon.server_banner" in check_ids
        assert "recon.waf_detection" in check_ids
        assert "recon.cms_detection" in check_ids
        assert "recon.path_enumeration" in check_ids
    finally:
        await client.aclose()


def test_security_headers_module():
    # Response missing all 6 security headers on HTTPS
    resp_empty = WebScanResponse(
        url="https://secure.test",
        status_code=200,
        headers={"Server": "nginx"},
        text="<html></html>",
        elapsed_ms=50.0,
    )
    mod = SecurityHeadersModule(resp_empty, "https://secure.test")
    res = mod.run()
    check_ids = [f["check_id"] for f in res["findings"]]

    assert "headers.csp" in check_ids
    assert "headers.hsts" in check_ids
    assert "headers.x_frame_options" in check_ids
    assert "headers.x_content_type_options" in check_ids
    assert "headers.permissions_policy" in check_ids
    assert "headers.referrer_policy" in check_ids


def test_cookie_audit_module():
    # Cookie missing HttpOnly, Secure, SameSite
    resp = WebScanResponse(
        url="https://secure.test",
        status_code=200,
        headers={},
        text="<html></html>",
        set_cookie_headers=["session_token=super_secret_jwt_value; path=/"],
        elapsed_ms=30.0,
    )
    mod = CookieAuditModule(resp, "https://secure.test")
    res = mod.run()
    findings = res["findings"]

    assert len(findings) == 3
    reasons = [f["severity_reason"] for f in findings]
    assert any("HttpOnly" in r for r in reasons)
    assert any("Secure" in r for r in reasons)
    assert any("SameSite" in r for r in reasons)

    # Verify secret value is never in evidence excerpts
    for f in findings:
        for ex in f["evidence"]["excerpts"]:
            assert "super_secret" not in ex["value_redacted"]
            assert "<redacted>" in ex["value_redacted"]


def test_forms_module():
    # Form with GET method transmitting password, and POST form without CSRF
    html_content = """
    <html>
      <form action="/login" method="GET">
        <input type="text" name="user" />
        <input type="password" name="pass" />
      </form>
      <form action="/update-email" method="POST">
        <input type="text" name="email" />
      </form>
    </html>
    """
    resp = WebScanResponse(
        url="http://mock.test",
        status_code=200,
        headers={},
        text=html_content,
        elapsed_ms=20.0,
    )
    mod = FormsModule(resp, "http://mock.test")
    res = mod.run()
    check_ids = [f["check_id"] for f in res["findings"]]

    assert "forms.weak_login_get" in check_ids
    assert "forms.missing_csrf_token" in check_ids


@pytest.mark.asyncio
async def test_parameters_module_sql_injection_detection():
    def handler(request: httpx.Request):
        url_str = str(request.url)
        # Reflect database error when diagnostic quote is injected
        if "'" in url_str or "%27" in url_str:
            return httpx.Response(
                500,
                text="Database error: You have an error in your SQL syntax near line 1",
                request=request,
            )
        return httpx.Response(200, text="Welcome page", request=request)

    transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport)

    try:
        form = DiscoveredForm(
            action="http://mock.test/search",
            method="GET",
            fields=[DiscoveredField(name="q", input_type="text")],
        )
        mod = ParametersModule(client, "http://mock.test", discovered_forms=[form])
        res = await mod.run()
        findings = res["findings"]
        check_ids = [f["check_id"] for f in findings]

        assert "parameters.sql_error_matching" in check_ids
        sqli_finding = [f for f in findings if f["check_id"] == "parameters.sql_error_matching"][0]
        assert sqli_finding["severity"] == "critical"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_load_resilience_module():
    def handler(request: httpx.Request):
        return httpx.Response(200, text="OK", request=request)

    transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport)

    try:
        cfg = LoadConfiguration(method="GET", concurrency=2, duration_seconds=1, delay_seconds=0.05)
        mod = LoadResilienceModule(client, "http://mock.test", load_config=cfg)
        res = await mod.run()
        metrics = res["metrics"]
        assert metrics["attempted"] > 0
        assert metrics["legacy_success_lt_500"] > 0
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_load_resilience_does_not_abort_on_429():
    def handler(request: httpx.Request):
        return httpx.Response(429, text="Too Many Requests", request=request)

    transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport)

    try:
        cfg = LoadConfiguration(method="GET", concurrency=2, duration_seconds=1, delay_seconds=0.05)
        mod = LoadResilienceModule(client, "http://mock.test", load_config=cfg)
        res = await mod.run()
        metrics = res["metrics"]
        assert metrics["rate_limited"] > 0
        assert metrics["http_4xx"] > 0
        assert metrics["aborted"] == 0
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_load_resilience_cooperative_cancellation():
    import asyncio
    cancel_evt = asyncio.Event()
    cancel_evt.set()  # Simulate operator clicking Cancel Audit

    def handler(request: httpx.Request):
        return httpx.Response(200, text="OK", request=request)

    transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport)

    try:
        cfg = LoadConfiguration(method="GET", concurrency=2, duration_seconds=5, delay_seconds=0.05)
        mod = LoadResilienceModule(client, "http://mock.test", load_config=cfg, cancel_event=cancel_evt)
        res = await mod.run()
        metrics = res["metrics"]
        assert metrics["aborted"] == 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_load_resilience_stops_cleanly_on_budget_exhaustion():
    def handler(request: httpx.Request):
        return httpx.Response(200, text="OK", request=request)

    transport = httpx.MockTransport(handler)
    # Small budget: exactly 5 requests
    client = WebScanHttpClient(target_url="http://mock.test", transport=transport, max_requests=5)

    try:
        cfg = LoadConfiguration(method="GET", concurrency=4, duration_seconds=5, delay_seconds=0.01)
        mod = LoadResilienceModule(client, "http://mock.test", load_config=cfg)
        res = await mod.run()
        metrics = res["metrics"]
        findings = res["findings"]

        # Exactly 5 requests dispatched before budget hit
        assert client.ledger.total_attempted == 5
        assert client.is_budget_exhausted is True
        assert metrics["budget_exhausted"] == 1
        # Crucial: budget rejection must NOT be counted as target network failure!
        assert metrics["network_failed"] == 0
        assert metrics["legacy_failure"] == 0
        # Workers stopped cleanly so recorded_errors remained <= 1
        assert len(client.recorded_errors) <= 1

        # Explicit fetch on exhausted client returns None and records error exactly once
        overflow_resp = await client.fetch("http://mock.test/overflow")
        assert overflow_resp is None
        assert len(client.recorded_errors) == 1
        assert client.recorded_errors[0]["code"] == "REQUEST_BUDGET_EXHAUSTED"

        # Calling fetch() a second time on exhausted client does not create duplicate errors
        overflow_resp_2 = await client.fetch("http://mock.test/overflow2")
        assert overflow_resp_2 is None
        assert len(client.recorded_errors) == 1

        # Since all 5 succeeded with 200 OK, target is recognized as stable (info finding, not high severity)
        assert any(f["severity"] == "info" for f in findings)
        assert not any(f["severity"] == "high" for f in findings)
    finally:
        await client.aclose()

