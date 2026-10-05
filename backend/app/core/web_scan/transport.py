from __future__ import annotations

from typing import Any, List, Optional
import httpcore
from httpcore._backends.auto import AutoBackend
import httpx
from app.core.web_scan.network_policy import resolve_and_validate_hostname


class PinnedDNSNetworkBackend(AutoBackend):
    """Network backend that connects directly to pre-validated IP address, preventing SSRF & DNS rebinding."""

    def __init__(self, allow_private: bool = False, allow_loopback: bool = False):
        super().__init__()
        self.allow_private = allow_private
        self.allow_loopback = allow_loopback
        self.last_connected_ip: Optional[str] = None

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: Optional[Any] = None,
    ) -> httpcore.AsyncNetworkStream:
        approved_ips = await resolve_and_validate_hostname(
            hostname=host,
            port=port,
            allow_private=self.allow_private,
            allow_loopback=self.allow_loopback,
        )
        pinned_ip = approved_ips[0]
        self.last_connected_ip = pinned_ip

        # Connect directly to the validated IP address
        return await super().connect_tcp(
            host=pinned_ip,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class PolicyCheckingTransport(httpx.AsyncBaseTransport):
    """
    HTTPX Async Transport that validates the target host against network policy
    and binds the connection directly to validated IPs (DNS pinning), preventing SSRF & DNS rebinding.
    """

    def __init__(
        self,
        wrapped_transport: Optional[httpx.AsyncBaseTransport] = None,
        allow_private: bool = False,
        allow_loopback: bool = False,
        verify: bool = True,
    ):
        self.allow_private = allow_private
        self.allow_loopback = allow_loopback
        self.verify = verify
        self.pinned_backend = PinnedDNSNetworkBackend(
            allow_private=allow_private,
            allow_loopback=allow_loopback,
        )

        if wrapped_transport is not None:
            self.wrapped = wrapped_transport
        else:
            base_transport = httpx.AsyncHTTPTransport(verify=verify, http2=False)
            base_transport._pool = httpcore.AsyncConnectionPool(
                ssl_context=base_transport._pool._ssl_context,
                network_backend=self.pinned_backend,
            )
            self.wrapped = base_transport

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        hostname = request.url.host or ""
        port = request.url.port or (443 if request.url.scheme == "https" else 80)

        # Validate hostname & resolve IPs prior to connection
        approved_ips = await resolve_and_validate_hostname(
            hostname=hostname,
            port=port,
            allow_private=self.allow_private,
            allow_loopback=self.allow_loopback,
        )
        resp = await self.wrapped.handle_async_request(request)
        resp.extensions["pinned_ip"] = approved_ips[0]
        resp.extensions["approved_ips"] = approved_ips
        return resp

    async def aclose(self) -> None:
        await self.wrapped.aclose()
