from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import httpx

from app.config import settings
from app.core.web_scan.network_policy import parse_and_validate_target
from app.core.web_scan.transport import PolicyCheckingTransport

logger = logging.getLogger("signal_scanner.web_scan.http")

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
]


class WebScanResponse:
    """Standardized response object for web scanner checks."""

    def __init__(
        self,
        url: str,
        status_code: int,
        headers: Dict[str, str],
        multi_headers: Optional[List[Tuple[str, str]]] = None,
        text: str = "",
        elapsed_ms: float = 0.0,
        http_version: str = "HTTP/1.1",
        truncated: bool = False,
        body_truncated: Optional[bool] = None,
        set_cookie_headers: Optional[List[str]] = None,
    ):
        self.url = url
        self.status_code = status_code
        self.headers = headers
        self.multi_headers = multi_headers or []
        if set_cookie_headers:
            for sc in set_cookie_headers:
                self.multi_headers.append(("set-cookie", sc))
        self.text = text
        self.elapsed_ms = elapsed_ms
        self.http_version = http_version
        self.truncated = truncated or (body_truncated is True)

    @property
    def body_truncated(self) -> bool:
        return self.truncated

    @property
    def set_cookie_headers(self) -> List[str]:
        return [val for name, val in self.multi_headers if name.lower() == "set-cookie"]


class WebScanHttpClient:
    """Async HTTP client with bounded concurrency, rate limits, and network safety policy."""

    def __init__(
        self,
        target_url: Optional[str] = None,
        config: Optional[Any] = None,
        timeout_seconds: float = 600.0,
        tls_verify: bool = True,
        allow_private: bool = False,
        allow_loopback: bool = False,
        max_concurrency: int = 10000,
        requests_per_second: float = 1000.0,
        user_agent_profile: str = "source_rotation",
        fixed_user_agent: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        mock_transport: Optional[httpx.AsyncBaseTransport] = None,
        cancel_event: Optional[asyncio.Event] = None,
        **kwargs,
    ):
        if config:
            timeout_seconds = getattr(config, "timeout_seconds", timeout_seconds)
            tls_verify = getattr(config, "tls_verify", tls_verify)
            allow_private = getattr(config, "allow_private", allow_private)
            max_concurrency = getattr(config, "max_concurrency", max_concurrency)
            requests_per_second = getattr(config, "requests_per_second", requests_per_second)
            user_agent_profile = getattr(config, "user_agent_profile", user_agent_profile)
            fixed_user_agent = getattr(config, "fixed_user_agent", fixed_user_agent)

        self.target_url = target_url
        self.timeout_seconds = timeout_seconds
        self.tls_verify = tls_verify
        self.allow_private = allow_private
        self.allow_loopback = allow_loopback
        self.user_agent_profile = user_agent_profile
        self.fixed_user_agent = fixed_user_agent
        self.cancel_event = cancel_event

        # Semaphores and rate limit tracking
        self.global_semaphore = asyncio.Semaphore(max_concurrency)
        self.origin_semaphores: Dict[str, asyncio.Semaphore] = {}
        self.origin_last_request: Dict[str, float] = {}
        self.min_interval = 1.0 / max(0.5, requests_per_second)

        # Setup transport
        eff_transport = transport or mock_transport
        if eff_transport is not None:
            self.transport = eff_transport
        else:
            self.transport = PolicyCheckingTransport(
                allow_private=allow_private,
                allow_loopback=allow_loopback,
            )

        self._client = httpx.AsyncClient(
            transport=self.transport,
            verify=tls_verify,
            follow_redirects=True,
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
        )

    def _get_user_agent(self) -> str:
        if self.user_agent_profile == "fixed" and self.fixed_user_agent:
            return self.fixed_user_agent
        return random.choice(USER_AGENTS)

    def _get_origin_key(self, url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"

    async def fetch(
        self,
        url: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Optional[WebScanResponse]:
        """Executes a bounded async HTTP request with rate limiting and response body capping."""
        if self.cancel_event and self.cancel_event.is_set():
            return None

        origin = self._get_origin_key(url)
        if origin not in self.origin_semaphores:
            self.origin_semaphores[origin] = asyncio.Semaphore(settings.WEB_SCAN_PER_ORIGIN_CONCURRENCY)

        origin_sem = self.origin_semaphores[origin]

        # Rate limiting delay
        now = time.monotonic()
        last_req = self.origin_last_request.get(origin, 0.0)
        time_since_last = now - last_req
        if time_since_last < self.min_interval:
            await asyncio.sleep(self.min_interval - time_since_last)

        # Request headers
        req_headers = {
            "User-Agent": self._get_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        if headers:
            req_headers.update(headers)

        req_timeout = timeout if timeout is not None else self.timeout_seconds

        async with self.global_semaphore:
            async with origin_sem:
                self.origin_last_request[origin] = time.monotonic()
                start_time = time.monotonic()
                try:
                    # Stream the response to enforce max body size
                    req = self._client.build_request(
                        method=method,
                        url=url,
                        params=params,
                        data=data,
                        json=json_data,
                        headers=req_headers,
                        timeout=req_timeout,
                    )
                    resp = await self._client.send(req, stream=True)
                    elapsed_ms = (time.monotonic() - start_time) * 1000.0

                    max_bytes = settings.WEB_SCAN_MAX_BODY_BYTES
                    body_chunks = []
                    bytes_read = 0
                    truncated = False

                    async for chunk in resp.aiter_bytes():
                        if bytes_read + len(chunk) > max_bytes:
                            allowed_slice = chunk[: max_bytes - bytes_read]
                            body_chunks.append(allowed_slice)
                            truncated = True
                            break
                        body_chunks.append(chunk)
                        bytes_read += len(chunk)

                    await resp.aclose()
                    raw_body = b"".join(body_chunks)
                    encoding = resp.encoding or "utf-8"
                    try:
                        text = raw_body.decode(encoding, errors="replace")
                    except Exception:
                        text = raw_body.decode("utf-8", errors="replace")

                    # Extract multi-headers
                    multi_headers = [(k, v) for k, v in resp.headers.raw]
                    decoded_multi = [(k.decode("ascii", errors="replace"), v.decode("latin-1", errors="replace")) for k, v in multi_headers]

                    return WebScanResponse(
                        url=str(resp.url),
                        status_code=resp.status_code,
                        headers=dict(resp.headers),
                        multi_headers=decoded_multi,
                        text=text,
                        elapsed_ms=elapsed_ms,
                        http_version=resp.http_version,
                        truncated=truncated,
                    )
                except httpx.TimeoutException:
                    logger.warning(f"Request timeout to {url}")
                    return None
                except Exception as e:
                    logger.debug(f"HTTP request error for {url}: {e}")
                    return None

    async def aclose(self) -> None:
        await self._client.aclose()
