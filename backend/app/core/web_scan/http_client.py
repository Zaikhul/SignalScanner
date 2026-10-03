from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit

import httpx

from app.config import settings
from app.core.web_scan.network_policy import (
    parse_and_validate_target,
    redact_url_query_params,
    validate_target_against_scope,
)
from app.core.web_scan.transport import PolicyCheckingTransport

logger = logging.getLogger("signal_scanner.web_scan.http")

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
]


class RequestBudgetLedger:
    """Authoritative execution ledger tracking all HTTP attempts, outcomes, and budget constraints."""

    def __init__(self, max_requests: int = 10000):
        self.max_requests = max(1, max_requests)
        self.total_attempted: int = 0
        self.total_succeeded: int = 0
        self.total_failed: int = 0
        self.status_2xx: int = 0
        self.status_3xx: int = 0
        self.status_4xx: int = 0
        self.status_5xx: int = 0
        self.total_timeouts: int = 0
        self.total_network_errors: int = 0
        self.total_aborted: int = 0
        self._lock = asyncio.Lock()

    @property
    def is_exhausted(self) -> bool:
        return self.total_attempted >= self.max_requests

    async def acquire_permit(self) -> bool:
        async with self._lock:
            if self.total_attempted >= self.max_requests:
                return False
            self.total_attempted += 1
            return True

    def record_success(self, status_code: int) -> None:
        self.total_succeeded += 1
        if 200 <= status_code < 300:
            self.status_2xx += 1
        elif 300 <= status_code < 400:
            self.status_3xx += 1
        elif 400 <= status_code < 500:
            self.status_4xx += 1
        elif status_code >= 500:
            self.status_5xx += 1

    def record_failure(self, error_type: str) -> None:
        self.total_failed += 1
        if error_type == "timeout":
            self.total_timeouts += 1
        elif error_type == "aborted":
            self.total_aborted += 1
        else:
            self.total_network_errors += 1

    @property
    def attempt_count(self) -> int:
        return self.total_attempted

    @property
    def success_count(self) -> int:
        return self.total_succeeded

    def to_metrics_dict(self) -> Dict[str, Any]:
        return {
            "requests_total": self.total_attempted,
            "requests_attempted": self.total_attempted,
            "requests_succeeded": self.total_succeeded,
            "requests_failed": self.total_failed,
            "status_2xx": self.status_2xx,
            "status_3xx": self.status_3xx,
            "status_4xx": self.status_4xx,
            "status_5xx": self.status_5xx,
            "timeouts": self.total_timeouts,
            "network_errors": self.total_network_errors,
            "aborted": self.total_aborted,
        }

    def to_metrics(self) -> Any:
        from app.schemas.web_scan import RequestMetrics
        return RequestMetrics(
            attempted=self.total_attempted,
            completed=self.total_succeeded,
            network_failed=self.total_network_errors + self.total_timeouts,
            http_2xx_3xx=self.status_2xx + self.status_3xx,
            http_4xx=self.status_4xx,
            http_5xx=self.status_5xx,
            http_other=0,
            rate_limited=0,
            bytes_received=0,
        )


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
    """Async HTTP client with atomic rate limiting, budget enforcement, DNS pinning, and scope validation."""

    def __init__(
        self,
        target_url: Optional[str] = None,
        config: Optional[Any] = None,
        timeout_seconds: float = 600.0,
        tls_verify: bool = True,
        allow_private: bool = False,
        allow_loopback: bool = False,
        max_concurrency: int = 10000,
        per_origin_concurrency: int = 5000,
        requests_per_second: float = 1000.0,
        max_requests: int = 10000,
        job_timeout_seconds: int = 600,
        scope_rules: Optional[List[Dict[str, Any]]] = None,
        user_agent_profile: str = "source_rotation",
        fixed_user_agent: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        mock_transport: Optional[httpx.AsyncBaseTransport] = None,
        cancel_event: Optional[asyncio.Event] = None,
        ledger: Optional[RequestBudgetLedger] = None,
        global_semaphore: Optional[asyncio.Semaphore] = None,
        **kwargs,
    ):
        if config:
            timeout_seconds = getattr(config, "timeout_seconds", timeout_seconds)
            tls_verify = getattr(config, "tls_verify", tls_verify)
            allow_private = getattr(config, "allow_private", allow_private)
            allow_loopback = getattr(config, "allow_loopback", allow_loopback)
            max_concurrency = getattr(config, "max_concurrency", max_concurrency)
            per_origin_concurrency = getattr(config, "per_origin_concurrency", per_origin_concurrency)
            requests_per_second = getattr(config, "requests_per_second", requests_per_second)
            max_requests = getattr(config, "max_requests", max_requests)
            job_timeout_seconds = getattr(config, "job_timeout_seconds", job_timeout_seconds)
            user_agent_profile = getattr(config, "user_agent_profile", user_agent_profile)
            fixed_user_agent = getattr(config, "fixed_user_agent", fixed_user_agent)

        self.target_url = target_url
        self.timeout_seconds = timeout_seconds
        self.tls_verify = tls_verify
        self.allow_private = allow_private
        self.allow_loopback = allow_loopback
        self.max_concurrency = max_concurrency
        self.per_origin_concurrency = per_origin_concurrency
        self.scope_rules = scope_rules
        self.user_agent_profile = user_agent_profile
        self.fixed_user_agent = fixed_user_agent
        self.cancel_event = cancel_event
        self.job_deadline = time.monotonic() + job_timeout_seconds if job_timeout_seconds > 0 else None

        # Ledger & Recorded errors
        self.ledger = ledger or RequestBudgetLedger(max_requests=max_requests)
        self.recorded_errors: List[Dict[str, Any]] = []
        self._budget_exhausted_logged: bool = False

        # Semaphores and atomic rate limiter state
        self.global_semaphore = global_semaphore or asyncio.Semaphore(max_concurrency)
        self.origin_semaphores: Dict[str, asyncio.Semaphore] = {}
        self.min_interval = 1.0 / max(0.5, requests_per_second)
        self._rate_lock = asyncio.Lock()
        self._origin_next_slot: Dict[str, float] = {}

        # Active tasks tracking for immediate cancellation
        self._in_flight_tasks: Set[asyncio.Task] = set()

        # Setup transport with verify pass-through
        eff_transport = transport or mock_transport
        if eff_transport is not None:
            self.transport = eff_transport
        else:
            self.transport = PolicyCheckingTransport(
                allow_private=allow_private,
                allow_loopback=allow_loopback,
                verify=tls_verify,
            )

        # Disable auto-redirect on client so we manually validate each hop
        self._client = httpx.AsyncClient(
            transport=self.transport,
            verify=tls_verify,
            follow_redirects=False,
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
        )

    @property
    def is_budget_exhausted(self) -> bool:
        return self.ledger.is_exhausted

    def _get_user_agent(self) -> str:
        if self.user_agent_profile == "fixed" and self.fixed_user_agent:
            return self.fixed_user_agent
        return random.choice(USER_AGENTS)

    def _get_origin_key(self, url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"

    async def _schedule_rate_slot(self, origin: str) -> bool:
        """Atomically schedules next permitted dispatch slot and sleeps without burst."""
        if self.cancel_event and self.cancel_event.is_set():
            return False

        async with self._rate_lock:
            now = time.monotonic()
            next_allowed = self._origin_next_slot.get(origin, now)
            if next_allowed < now:
                next_allowed = now
            self._origin_next_slot[origin] = next_allowed + self.min_interval
            wait_time = next_allowed - now

        if wait_time > 0:
            if self.cancel_event:
                try:
                    await asyncio.wait_for(self.cancel_event.wait(), timeout=wait_time)
                    return False
                except asyncio.TimeoutError:
                    pass
            else:
                await asyncio.sleep(wait_time)

        return not (self.cancel_event and self.cancel_event.is_set())

    def abort_in_flight(self) -> None:
        """Cancels all in-flight HTTP request tasks immediately."""
        for task in list(self._in_flight_tasks):
            if not task.done():
                task.cancel()

    async def fetch(
        self,
        url: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        max_redirects: int = 5,
    ) -> Optional[WebScanResponse]:
        """Executes a bounded async HTTP request with atomic throttling, budget checking, and redirect scope enforcement."""
        current_task = asyncio.current_task()
        if current_task:
            self._in_flight_tasks.add(current_task)

        try:
            return await self._fetch_internal(
                url=url,
                method=method,
                params=params,
                data=data,
                json_data=json_data,
                headers=headers,
                timeout=timeout,
                max_redirects=max_redirects,
            )
        finally:
            if current_task:
                self._in_flight_tasks.discard(current_task)

    async def _fetch_internal(
        self,
        url: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        max_redirects: int = 5,
    ) -> Optional[WebScanResponse]:
        current_url = url
        current_method = method
        redirect_count = 0

        while True:
            # 1. Deadline check
            if self.job_deadline and time.monotonic() >= self.job_deadline:
                safe_url = redact_url_query_params(current_url)
                logger.warning("Job deadline reached before dispatching request to %s", safe_url)
                self.recorded_errors.append({
                    "stage": "request",
                    "code": "JOB_DEADLINE_EXCEEDED",
                    "message": f"Job deadline reached for {safe_url}",
                })
                self.ledger.record_failure("timeout")
                return None

            # 2. Cancellation check
            if self.cancel_event and self.cancel_event.is_set():
                self.ledger.record_failure("aborted")
                return None

            # 3. Budget permit check
            has_permit = await self.ledger.acquire_permit()
            if not has_permit:
                if not self._budget_exhausted_logged:
                    self._budget_exhausted_logged = True
                    safe_url = redact_url_query_params(current_url)
                    logger.warning(
                        "Request budget exhausted (%d requests reached). Subsequent requests suppressed for %s",
                        self.ledger.max_requests,
                        safe_url,
                    )
                    self.recorded_errors.append({
                        "stage": "request",
                        "code": "REQUEST_BUDGET_EXHAUSTED",
                        "message": f"Budget limit of {self.ledger.max_requests} requests reached",
                    })
                return None

            # 4. Scope verification for URL & method
            if self.scope_rules:
                is_valid, reason = validate_target_against_scope(
                    current_url,
                    self.scope_rules,
                    method=current_method,
                )
                if not is_valid:
                    safe_url = redact_url_query_params(current_url)
                    logger.warning("Target URL %s rejected by scope rules: %s", safe_url, reason)
                    self.recorded_errors.append({
                        "stage": "request",
                        "code": "SCOPE_VIOLATION",
                        "message": f"URL {safe_url} outside scope: {reason}",
                    })
                    self.ledger.record_failure("scope_violation")
                    return None

            # 5. Origin rate limiting
            origin = self._get_origin_key(current_url)
            if not await self._schedule_rate_slot(origin):
                self.ledger.record_failure("aborted")
                return None

            if origin not in self.origin_semaphores:
                self.origin_semaphores[origin] = asyncio.Semaphore(self.per_origin_concurrency)

            origin_sem = self.origin_semaphores[origin]

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
                    if self.cancel_event and self.cancel_event.is_set():
                        self.ledger.record_failure("aborted")
                        return None

                    start_time = time.monotonic()
                    try:
                        req = self._client.build_request(
                            method=current_method,
                            url=current_url,
                            params=params if redirect_count == 0 else None,
                            data=data if redirect_count == 0 else None,
                            json=json_data if redirect_count == 0 else None,
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

                        multi_headers = [(k, v) for k, v in resp.headers.raw]
                        decoded_multi = [
                            (k.decode("ascii", errors="replace"), v.decode("latin-1", errors="replace"))
                            for k, v in multi_headers
                        ]

                        self.ledger.record_success(resp.status_code)

                        # Handle redirect hop manually
                        if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                            if redirect_count < max_redirects:
                                loc = resp.headers["location"]
                                next_url = str(resp.url.join(loc))
                                redirect_count += 1
                                current_url = next_url
                                if resp.status_code == 303:
                                    current_method = "GET"
                                continue

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

                    except httpx.ConnectTimeout:
                        safe_url = redact_url_query_params(current_url)
                        logger.warning("Connection timeout to %s", safe_url)
                        self.recorded_errors.append({
                            "stage": "connect",
                            "code": "CONNECT_TIMEOUT",
                            "message": f"Connection timed out for {safe_url}",
                        })
                        self.ledger.record_failure("timeout")
                        return None

                    except httpx.ReadTimeout:
                        safe_url = redact_url_query_params(current_url)
                        logger.warning("Read timeout to %s", safe_url)
                        self.recorded_errors.append({
                            "stage": "response",
                            "code": "READ_TIMEOUT",
                            "message": f"Read timed out for {safe_url}",
                        })
                        self.ledger.record_failure("timeout")
                        return None

                    except httpx.ConnectError as ce:
                        safe_url = redact_url_query_params(current_url)
                        logger.warning("Connection error to %s: %s", safe_url, ce)
                        self.recorded_errors.append({
                            "stage": "connect",
                            "code": "CONNECT_ERROR",
                            "message": f"Cannot connect to {safe_url}: {ce}",
                        })
                        self.ledger.record_failure("connect_error")
                        return None

                    except Exception as e:
                        safe_url = redact_url_query_params(current_url)
                        err_str = str(e)
                        code = "TLS_ERROR" if "ssl" in err_str.lower() or "certificate" in err_str.lower() else "HTTP_REQUEST_ERROR"
                        stage = "tls" if code == "TLS_ERROR" else "request"
                        logger.debug("HTTP request error for %s (%s): %s", safe_url, code, e)
                        self.recorded_errors.append({
                            "stage": stage,
                            "code": code,
                            "message": f"{code} for {safe_url}: {e}",
                        })
                        self.ledger.record_failure("network_error")
                        return None

    async def aclose(self) -> None:
        self.abort_in_flight()
        await self._client.aclose()
