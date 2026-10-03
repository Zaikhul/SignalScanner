from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from app.core.web_scan.http_client import WebScanHttpClient
from app.schemas.web_scan import LoadConfiguration

logger = logging.getLogger("signal_scanner.web_scan.load_resilience")


class LoadResilienceModule:
    """Executes a bounded load resilience workload to evaluate target responsiveness under load."""

    def __init__(
        self,
        http_client: WebScanHttpClient,
        target_url: str,
        load_config: Optional[LoadConfiguration] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ):
        self.http = http_client
        self.target_url = target_url
        self.load_config = load_config or LoadConfiguration()
        self.cancel_event = cancel_event or asyncio.Event()

    async def run(self) -> Dict[str, Any]:
        findings = []
        observations = []

        cfg = self.load_config
        concurrency = min(cfg.concurrency, 10000)
        duration_sec = min(cfg.duration_seconds, 600)
        delay_sec = max(cfg.delay_seconds, 0.01)
        method = cfg.method

        payload_data = None
        if method == "POST" and cfg.body_template == "benign_5k":
            payload_data = {"test_payload": "X" * 5000}

        attempted = 0
        http_2xx_3xx = 0
        http_4xx = 0
        http_5xx = 0
        http_other = 0
        network_failed = 0
        legacy_success_lt_500 = 0
        legacy_failure = 0
        rate_limited = 0

        start_time = time.monotonic()
        end_deadline = start_time + duration_sec
        budget_exhausted = False
        budget_event = asyncio.Event()

        async def worker():
            nonlocal attempted, http_2xx_3xx, http_4xx, http_5xx, http_other
            nonlocal network_failed, legacy_success_lt_500, legacy_failure, rate_limited
            nonlocal budget_exhausted

            while time.monotonic() < end_deadline and not self.cancel_event.is_set() and not budget_event.is_set():
                if getattr(self.http, "is_budget_exhausted", False):
                    budget_exhausted = True
                    budget_event.set()
                    break

                attempted += 1
                resp = await self.http.fetch(
                    self.target_url,
                    method=method,
                    data=payload_data,
                    timeout=5.0,
                )

                if resp is None:
                    if getattr(self.http, "is_budget_exhausted", False):
                        budget_exhausted = True
                        budget_event.set()
                        attempted = max(0, attempted - 1)
                        break
                    network_failed += 1
                    legacy_failure += 1
                else:
                    sc = resp.status_code
                    if 200 <= sc < 400:
                        http_2xx_3xx += 1
                        legacy_success_lt_500 += 1
                    elif 400 <= sc < 500:
                        http_4xx += 1
                        legacy_success_lt_500 += 1
                        if sc == 429:
                            rate_limited += 1
                    elif 500 <= sc < 600:
                        http_5xx += 1
                        legacy_failure += 1
                    else:
                        http_other += 1
                        legacy_failure += 1

                if delay_sec > 0:
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(
                                self.cancel_event.wait(),
                                budget_event.wait(),
                                return_exceptions=True,
                            ),
                            timeout=delay_sec,
                        )
                        break
                    except asyncio.TimeoutError:
                        pass

        tasks = [asyncio.create_task(worker()) for _ in range(concurrency)]
        await asyncio.gather(*tasks, return_exceptions=True)

        if budget_exhausted:
            logger.info(
                "Load resilience workload stopped cleanly: scan request budget limit reached (%d requests)",
                getattr(getattr(self.http, "ledger", None), "max_requests", attempted),
            )

        elapsed_total_ms = (time.monotonic() - start_time) * 1000.0
        dur_s = max(0.001, elapsed_total_ms / 1000.0)
        avg_rps = attempted / dur_s

        load_data = {
            "method": method,
            "attempted": attempted,
            "elapsed_ms": elapsed_total_ms,
            "http_2xx_3xx": http_2xx_3xx,
            "http_4xx": http_4xx,
            "http_5xx": http_5xx,
            "http_other": http_other,
            "network_failed": network_failed,
            "aborted": 1 if self.cancel_event.is_set() else 0,
            "budget_exhausted": 1 if budget_exhausted else 0,
            "rate_limited": rate_limited,
            "legacy_success_lt_500": legacy_success_lt_500,
            "legacy_failure": legacy_failure,
            "average_rps": round(avg_rps, 2),
        }

        observations.append({
            "kind": "load",
            "module": "stress",
            "data": load_data,
        })

        # Calculate legacy stress severity per Ghost formula: failure rate > 50% = high, > 20% = medium
        legacy_evaluated = legacy_success_lt_500 + legacy_failure
        legacy_fail_pct = (legacy_failure / legacy_evaluated * 100.0) if legacy_evaluated > 0 else 0.0

        if legacy_fail_pct > 50.0:
            findings.append({
                "module": "stress",
                "check_id": "stress.bounded_load_test",
                "category": "service_resilience",
                "source_category": "STRESS_TEST",
                "severity": "high",
                "source_severity": "high",
                "severity_reason": f"Target experienced {legacy_fail_pct:.1f}% failure rate under concurrent load",
                "confidence": "confirmed_configuration",
                "title": "High Failure Rate Under Concurrent Load",
                "description": f"Target failed or returned 5xx responses for {legacy_fail_pct:.1f}% of requests during the resilience test.",
                "remediation": "Investigate web server resource limits, application threadpool sizing, and upstream timeouts.",
                "evidence": {
                    "url_display": self.target_url,
                    "method": method,
                    "excerpts": [{"kind": "text", "value_redacted": f"Failure rate: {legacy_fail_pct:.1f}% ({legacy_failure}/{legacy_evaluated})"}],
                    "elapsed_ms": elapsed_total_ms,
                },
                "fingerprint": f"stress:failure_rate_high:{self.target_url}",
            })
        elif legacy_fail_pct > 20.0:
            findings.append({
                "module": "stress",
                "check_id": "stress.bounded_load_test",
                "category": "service_resilience",
                "source_category": "STRESS_TEST",
                "severity": "medium",
                "source_severity": "medium",
                "severity_reason": f"Target experienced {legacy_fail_pct:.1f}% failure rate under concurrent load",
                "confidence": "confirmed_configuration",
                "title": "Moderate Failure Rate Under Concurrent Load",
                "description": f"Target failed for {legacy_fail_pct:.1f}% of requests during the resilience test.",
                "remediation": "Review web application server capacity and rate limiting policies.",
                "evidence": {
                    "url_display": self.target_url,
                    "method": method,
                    "excerpts": [{"kind": "text", "value_redacted": f"Failure rate: {legacy_fail_pct:.1f}% ({legacy_failure}/{legacy_evaluated})"}],
                    "elapsed_ms": elapsed_total_ms,
                },
                "fingerprint": f"stress:failure_rate_medium:{self.target_url}",
            })
        elif attempted > 0:
            findings.append({
                "module": "stress",
                "check_id": "stress.bounded_load_test",
                "category": "service_resilience",
                "source_category": "STRESS_TEST",
                "severity": "info",
                "source_severity": "info",
                "severity_reason": f"Target sustained bounded load with acceptable resilience ({legacy_fail_pct:.1f}% failure rate across {attempted} requests at {avg_rps:.1f} avg req/s)",
                "confidence": "confirmed_configuration",
                "title": "Bounded Load Resilience Benchmark: Target Stable",
                "description": f"Target successfully sustained {attempted} requests ({http_2xx_3xx} 2xx/3xx, {http_4xx} 4xx) with {legacy_fail_pct:.1f}% failure rate at an average of {avg_rps:.1f} requests/sec.",
                "remediation": "No remediation required. The target demonstrated acceptable resilience within the tested bounds.",
                "evidence": {
                    "url_display": self.target_url,
                    "method": method,
                    "excerpts": [{"kind": "text", "value_redacted": f"Failure rate: {legacy_fail_pct:.1f}%, Attempted: {attempted}, Avg RPS: {round(avg_rps, 1)}"}],
                    "elapsed_ms": elapsed_total_ms,
                },
                "fingerprint": f"stress:resilience_stable:{self.target_url}",
            })

        return {
            "findings": findings,
            "observations": observations,
            "metrics": load_data,
            "load_metrics": load_data,
            "status": "completed",
        }
