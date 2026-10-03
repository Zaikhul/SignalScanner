from __future__ import annotations

import logging
from typing import Any, Dict, List
from urllib.parse import urlsplit

from app.core.web_scan.http_client import WebScanHttpClient
from app.core.web_scan.payload_catalog import HEADER_DIAGNOSTIC_PROBES

logger = logging.getLogger("signal_scanner.web_scan.header_probes")


class HeaderProbesModule:
    """Probes internal pages with non-destructive header diagnostics to evaluate blind time-based injections."""

    def __init__(self, http_client: WebScanHttpClient, target_url: str, discovered_links: List[str]):
        self.http = http_client
        self.target_url = target_url
        self.links = discovered_links[:10]  # Max 10 links per PRD C-27 and C-28
        parts = urlsplit(target_url)
        self.domain = parts.hostname or ""

    async def run(self) -> Dict[str, Any]:
        findings = []
        observations = []

        # If no links discovered, audit the target URL itself
        urls_to_test = self.links if self.links else [self.target_url]

        for link in urls_to_test:
            # First obtain link baseline
            base_resp = await self.http.fetch(link, timeout=5.0)
            base_elapsed = base_resp.elapsed_ms if base_resp else 100.0

            # Test headers with safe diagnostic probes
            h_resp = await self.http.fetch(
                link,
                headers=HEADER_DIAGNOSTIC_PROBES,
                timeout=12.0,  # 12s timeout for header timing check as in V1.0.py
            )
            if not h_resp:
                continue

            # If delayed by >= 5.0s compared to baseline (and total elapsed >= 5000ms)
            if h_resp.elapsed_ms >= 5000.0 and (h_resp.elapsed_ms - base_elapsed) >= 4000.0:
                findings.append({
                    "check_id": "header_probes.time_based_sql",
                    "category": "injection_vulnerability",
                    "source_category": "BLIND_SQLI_HEADER",
                    "severity": "high",
                    "source_severity": "high",
                    "severity_reason": f"Header diagnostic caused delay of {h_resp.elapsed_ms/1000.0:.2f}s (baseline {base_elapsed/1000.0:.2f}s)",
                    "confidence": "suspected",
                    "title": f"Potential Blind SQL Injection in HTTP Request Headers ({link})",
                    "description": "Diagnostic timing stimulus injected into User-Agent/XFF produced a significant response latency increase.",
                    "remediation": "Sanitize and parameterize all HTTP header inputs before passing them into SQL queries or logging systems.",
                    "evidence": {
                        "url_display": link,
                        "method": "GET",
                        "status_code": h_resp.status_code,
                        "elapsed_ms": h_resp.elapsed_ms,
                        "baseline_elapsed_ms": base_elapsed,
                        "excerpts": [{"kind": "timing", "value_redacted": f"Elapsed {h_resp.elapsed_ms:.1f}ms on header probe"}],
                    },
                    "fingerprint": f"headers:probe:time:{self.domain}:{link}",
                })

        return {
            "findings": findings,
            "observations": observations,
            "status": "completed",
        }
