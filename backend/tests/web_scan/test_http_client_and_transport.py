import asyncio
import httpx
import pytest
from app.core.web_scan.http_client import WebScanHttpClient, WebScanResponse
from app.schemas.web_scan import ScanConfiguration


@pytest.mark.asyncio
async def test_http_client_mock_fetch_and_body_capping():
    # Mock transport returning normal response and oversized body
    def handler(request: httpx.Request):
        if "large" in str(request.url):
            # Return 2MB payload
            return httpx.Response(200, content=b"A" * (2 * 1024 * 1024), request=request)
        return httpx.Response(
            200,
            text="<html><head><title>Test App</title></head><body>Hello World</body></html>",
            headers={"Server": "nginx/1.24", "Set-Cookie": "session_id=secret123; HttpOnly; Secure"},
            request=request,
        )

    mock_transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(
        target_url="http://mock-target.local",
        transport=mock_transport,
    )

    try:
        resp = await client.fetch("http://mock-target.local")
        assert resp is not None
        assert resp.status_code == 200
        assert "Hello World" in resp.text
        assert resp.headers["server"] == "nginx/1.24"
        assert len(resp.set_cookie_headers) == 1

        # Test body capping at 1 MiB (1048576 bytes)
        large_resp = await client.fetch("http://mock-target.local/large")
        assert large_resp is not None
        assert large_resp.body_truncated is True
        assert len(large_resp.text.encode("utf-8")) <= 1048576
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_http_client_cancel_event():
    cancel_event = asyncio.Event()

    def handler(request: httpx.Request):
        return httpx.Response(200, text="OK", request=request)

    mock_transport = httpx.MockTransport(handler)
    client = WebScanHttpClient(
        target_url="http://mock-target.local",
        transport=mock_transport,
        cancel_event=cancel_event,
    )

    try:
        # Pre-set cancel event
        cancel_event.set()
        resp = await client.fetch("http://mock-target.local")
        # Should return None when cancelled
        assert resp is None
    finally:
        await client.aclose()
