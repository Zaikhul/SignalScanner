from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlsplit

from app.core.web_scan.http_client import WebScanHttpClient, WebScanResponse

logger = logging.getLogger("signal_scanner.web_scan.recon")

# Comprehensive union of subdomains across v2, v47, and v75
SUBDOMAIN_UNION: List[str] = [
    "www", "mail", "dev", "staging", "admin", "api", "test",
    "webmail", "blog", "vpn", "cloud", "cpanel", "portal",
    "db", "ftp", "ns1", "ns2", "cdn", "app", "shop", "user", "secure"
]

# Comprehensive union of sensitive paths across v2, v47, and v75
DIRECTORY_UNION: List[str] = [
    "admin", "login", ".env", ".git/config", "config.php.bak",
    "backup.zip", "phpinfo.php", "server-status", "robots.txt",
    "wp-admin", "wp-login.php", ".htaccess", "web.config",
    "sitemap.xml", "api", "v1/api", "swagger", "graphql",
    ".well-known/security.txt", "debug", "backup", "db_backup.sql",
    "api/v1/user", "login.php", "config"
]


class ReconModule:
    """Executes passive fingerprinting and active endpoint enumeration."""

    def __init__(self, http_client: WebScanHttpClient, target_url: str):
        self.http = http_client
        self.target_url = target_url
        parts = urlsplit(target_url)
        self.domain = parts.hostname or ""

    async def run(self) -> Dict[str, Any]:
        findings = []
        observations = []

        # 1. Fetch root page for baseline & passive fingerprinting
        root_resp = await self.http.fetch(self.target_url)
        if not root_resp:
            return {
                "findings": findings,
                "observations": observations,
                "status": "failed",
                "reason": "Root target unreachable",
            }

        headers_lower = {k.lower(): v for k, v in root_resp.headers.items()}
        h_str = " ".join(f"{k}: {v}" for k, v in headers_lower.items()).lower()
        body_lower = root_resp.text.lower()

        # Record HTTP Response observation
        observations.append({
            "kind": "http_response",
            "module": "recon",
            "data": {
                "url_display": root_resp.url,
                "method": "GET",
                "status_code": root_resp.status_code,
                "http_version": root_resp.http_version,
                "elapsed_ms": root_resp.elapsed_ms,
                "header_names": list(root_resp.headers.keys()),
                "decompressed_bytes": len(root_resp.text.encode("utf-8")),
                "body_truncated": root_resp.truncated,
            },
        })

        # --- A. WAF Fingerprinting ---
        waf_detected = None
        if "cf-ray" in headers_lower or "cloudflare" in headers_lower.get("server", "").lower():
            waf_detected = "Cloudflare WAF"
        elif "mod_security" in h_str or "modsecurity" in h_str:
            waf_detected = "ModSecurity"
        elif "sucuri" in headers_lower.get("server", "").lower() or "x-sucuri-id" in headers_lower:
            waf_detected = "Sucuri CloudProxy"
        elif "akamai" in headers_lower.get("server", "").lower():
            waf_detected = "Akamai Edge WAF"
        elif "x-iinfo" in headers_lower or "incap_ses" in h_str:
            waf_detected = "Imperva Incapsula"
        elif "awselb" in h_str or "x-amzn-waf" in headers_lower:
            waf_detected = "AWS WAF"

        if waf_detected:
            observations.append({
                "kind": "technology",
                "module": "recon",
                "data": {
                    "family": "waf",
                    "name": waf_detected,
                    "rule_id": "recon.waf",
                    "basis_redacted": "Matched vendor response headers",
                    "heuristic": True,
                },
            })
            findings.append({
                "check_id": "recon.waf_detection",
                "category": "recon",
                "source_category": "TECH_INFO",
                "severity": "info",
                "source_severity": "info",
                "severity_reason": f"WAF detected: {waf_detected}",
                "confidence": "confirmed_configuration",
                "title": f"Web Application Firewall Active ({waf_detected})",
                "description": "Target is protected by a Web Application Firewall.",
                "remediation": "Maintain updated rulesets on WAF deployment.",
                "evidence": {
                    "url_display": root_resp.url,
                    "status_code": root_resp.status_code,
                    "excerpts": [{"kind": "header", "value_redacted": f"WAF: {waf_detected}"}],
                },
                "fingerprint": f"recon:waf:{self.domain}:{waf_detected}",
            })

        # --- B. Server & Tech Fingerprinting ---
        server_val = root_resp.headers.get("Server") or root_resp.headers.get("server")
        if server_val:
            observations.append({
                "kind": "technology",
                "module": "recon",
                "data": {
                    "family": "server",
                    "name": server_val,
                    "rule_id": "recon.server",
                    "basis_redacted": f"Server: {server_val}",
                    "heuristic": False,
                },
            })
            findings.append({
                "check_id": "recon.server_banner",
                "category": "recon",
                "source_category": "TECH_INFO",
                "severity": "info",
                "source_severity": "info",
                "severity_reason": f"Web server banner exposed: {server_val}",
                "confidence": "confirmed_configuration",
                "title": f"Web Server Banner Disclosed ({server_val})",
                "description": "Exposing the web server version aids reconnaissance by potential attackers.",
                "remediation": "Disable detailed server tokens in server configuration.",
                "evidence": {
                    "url_display": root_resp.url,
                    "status_code": root_resp.status_code,
                    "excerpts": [{"kind": "header", "value_redacted": f"Server: {server_val}"}],
                },
                "fingerprint": f"recon:server:{self.domain}:{server_val}",
            })

        x_powered = root_resp.headers.get("X-Powered-By") or root_resp.headers.get("x-powered-by")
        if x_powered:
            observations.append({
                "kind": "technology",
                "module": "recon",
                "data": {
                    "family": "powered_by",
                    "name": x_powered,
                    "rule_id": "recon.powered_by",
                    "basis_redacted": f"X-Powered-By: {x_powered}",
                    "heuristic": False,
                },
            })

        if "phpsessid" in h_str or "php" in (x_powered or "").lower():
            observations.append({
                "kind": "technology",
                "module": "recon",
                "data": {
                    "family": "php_hint",
                    "name": "PHP Runtime",
                    "rule_id": "recon.php",
                    "basis_redacted": "PHP session or powered-by detected",
                    "heuristic": True,
                },
            })

        # --- C. CMS Fingerprinting ---
        cms_detected = None
        if "wp-content" in body_lower or "wp-includes" in body_lower:
            cms_detected = "WordPress"
        elif "joomla" in body_lower or "media/system/js" in body_lower:
            cms_detected = "Joomla"
        elif "drupal" in body_lower or "sites/default/files" in body_lower:
            cms_detected = "Drupal"
        elif "cdn.shopify.com" in body_lower:
            cms_detected = "Shopify"
        elif "wix.com" in body_lower or "wixsite" in body_lower:
            cms_detected = "Wix"

        if cms_detected:
            observations.append({
                "kind": "technology",
                "module": "recon",
                "data": {
                    "family": "cms",
                    "name": cms_detected,
                    "rule_id": "recon.cms",
                    "basis_redacted": f"Detected {cms_detected} markers in HTML body",
                    "heuristic": True,
                },
            })
            findings.append({
                "check_id": "recon.cms_detection",
                "category": "recon",
                "source_category": "TECH_INFO",
                "severity": "info",
                "source_severity": "info",
                "severity_reason": f"Content Management System identified: {cms_detected}",
                "confidence": "confirmed_configuration",
                "title": f"CMS Platform Detected ({cms_detected})",
                "description": f"Target was identified as running {cms_detected}.",
                "remediation": "Keep all CMS core files and plugins patched to latest security revisions.",
                "evidence": {
                    "url_display": root_resp.url,
                    "status_code": root_resp.status_code,
                    "excerpts": [{"kind": "text", "value_redacted": f"CMS: {cms_detected}"}],
                },
                "fingerprint": f"recon:cms:{self.domain}:{cms_detected}",
            })

        # --- D. Soft-404 Baseline Probe ---
        baseline_404_url = urljoin(self.target_url, f"/ghost_nonexistent_{int(root_resp.elapsed_ms)}_test_404")
        soft_404_resp = await self.http.fetch(baseline_404_url)
        baseline_404_code = soft_404_resp.status_code if soft_404_resp else 404
        baseline_404_len = len(soft_404_resp.text) if soft_404_resp else 0

        # --- E. Path Enumeration ---
        for path_entry in DIRECTORY_UNION:
            test_url = urljoin(self.target_url.rstrip("/") + "/", path_entry)
            p_resp = await self.http.fetch(test_url)
            if not p_resp:
                continue

            # Soft 404 check: if returns 200 but matches 404 baseline length closely
            is_soft_404 = (
                p_resp.status_code == 200
                and baseline_404_code == 200
                and abs(len(p_resp.text) - baseline_404_len) < 50
            )

            if p_resp.status_code in (200, 403, 405) and not is_soft_404:
                cat = "SENSITIVE_DIR" if p_resp.status_code == 200 else "DIRECTORY"
                sev = "high" if (p_resp.status_code == 200 and any(s in path_entry for s in (".env", ".git", "backup", "config", "sql"))) else ("medium" if p_resp.status_code == 200 else "low")

                findings.append({
                    "check_id": "recon.path_enumeration",
                    "category": "directory_exposure",
                    "source_category": cat,
                    "severity": sev,
                    "source_severity": "high" if p_resp.status_code == 200 else "low",
                    "severity_reason": f"Discovered endpoint '{path_entry}' with HTTP status {p_resp.status_code}",
                    "confidence": "confirmed_configuration",
                    "title": f"Exposed Endpoint: /{path_entry}",
                    "description": f"The path '/{path_entry}' responded with HTTP {p_resp.status_code}. Sensitive files or admin interfaces may be exposed.",
                    "remediation": "Restrict access to sensitive files, admin panels, and configuration backups using web server access rules.",
                    "evidence": {
                        "url_display": test_url,
                        "method": "GET",
                        "status_code": p_resp.status_code,
                        "header_names": list(p_resp.headers.keys()),
                        "excerpts": [{"kind": "text", "value_redacted": f"HTTP {p_resp.status_code} ({len(p_resp.text)} bytes)"}],
                        "elapsed_ms": p_resp.elapsed_ms,
                    },
                    "fingerprint": f"recon:path:{self.domain}:{path_entry}:{p_resp.status_code}",
                })

                observations.append({
                    "kind": "path",
                    "module": "recon",
                    "data": {
                        "url_display": test_url,
                        "status_code": p_resp.status_code,
                        "soft_404": is_soft_404,
                        "classification": cat,
                        "wordlist_profile": "union",
                    },
                })

        return {
            "findings": findings,
            "observations": observations,
            "status": "completed",
            "root_response": root_resp,
        }
