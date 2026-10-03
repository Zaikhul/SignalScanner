from __future__ import annotations

import httpx
from typing import Optional
from app.core.web_scan.network_policy import resolve_and_validate_hostname


class PolicyCheckingTransport(httpx.AsyncBaseTransport):
    """
    HTTPX Async Transport that validates the target host against network policy
    before dispatching to the underlying transport, preventing SSRF & DNS rebinding.
    """

    def __init__(
        self,
        wrapped_transport: Optional[httpx.AsyncBaseTransport] = None,
        allow_private: bool = False,
        allow_loopback: bool = False,
    ):
        self.wrapped = wrapped_transport or httpx.AsyncHTTPTransport(http2=True)
        self.allow_private = allow_private
        self.allow_loopback = allow_loopback

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        hostname = request.url.host
        port = request.url.port or (443 if request.url.scheme == "https" else 80)

        # Validate hostname & resolve IPs prior to connection
        await resolve_and_validate_hostname(
            hostname=hostname,
            port=port,
            allow_private=self.allow_private,
            allow_loopback=self.allow_loopback,
        )

        return await self.wrapped.handle_async_request(request)

    async def aclose(self) -> None:
        await self.wrapped.aclose()
