from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import urlsplit

from app.core.web_scan.http_client import WebScanResponse
from app.core.web_scan.network_policy import redact_url_query_params


class SecurityHeadersModule:
    """Audits response headers against the 6 standard security header families."""

    def __init__(self, root_response: WebScanResponse, target_url: str):
        self.response = root_response
        self.target_url = target_url
        parts = urlsplit(target_url)
        self.scheme = parts.scheme.lower()
        self.domain = parts.hostname or ""

    def run(self) -> Dict[str, Any]:
        findings = []
        observations = []
        headers = {k.lower(): v for k, v in self.response.headers.items()}
        url_display = redact_url_query_params(self.response.url)

        # ── 1. Content-Security-Policy (CSP) ──────────────────────────────
        csp = headers.get("content-security-policy")
        if not csp:
            findings.append({
                "check_id": "headers.csp",
                "category": "security_headers",
                "source_category": "MISSING_HEADER",
                "severity": "high",
                "source_severity": "high",
                "severity_reason": "Content-Security-Policy header is absent",
                "confidence": "confirmed_configuration",
                "title": "Missing Content-Security-Policy Header",
                "description": "CSP restricts resource loading and significantly mitigates Cross-Site Scripting (XSS) attacks.",
                "remediation": "Configure a restrictive Content-Security-Policy (e.g., default-src 'self').",
                "evidence": {
                    "url_display": url_display,
                    "status_code": self.response.status_code,
                    "header_names": list(self.response.headers.keys()),
                    "excerpts": [{"kind": "header", "value_redacted": "Content-Security-Policy: <missing>"}],
                },
                "fingerprint": f"headers:csp:missing:{self.domain}",
            })
        else:
            if "unsafe-inline" in csp.lower() or "unsafe-eval" in csp.lower():
                findings.append({
                    "check_id": "headers.csp",
                    "category": "security_headers",
                    "source_category": "INSECURE_HEADER",
                    "severity": "medium",
                    "source_severity": "medium",
                    "severity_reason": "CSP includes 'unsafe-inline' or 'unsafe-eval' directives",
                    "confidence": "confirmed_configuration",
                    "title": "Insecure Content-Security-Policy Directives",
                    "description": "Allowing unsafe-inline or unsafe-eval weakens XSS mitigations.",
                    "remediation": "Use nonces or hashes instead of 'unsafe-inline' and eliminate 'unsafe-eval'.",
                    "evidence": {
                        "url_display": url_display,
                        "status_code": self.response.status_code,
                        "header_names": list(self.response.headers.keys()),
                        "excerpts": [{"kind": "header", "value_redacted": f"Content-Security-Policy: {csp}"}],
                    },
                    "fingerprint": f"headers:csp:unsafe:{self.domain}",
                })

        # ── 2. HTTP Strict Transport Security (HSTS) ──────────────────────
        if self.scheme == "https":
            hsts = headers.get("strict-transport-security")
            if not hsts:
                findings.append({
                    "check_id": "headers.hsts",
                    "category": "security_headers",
                    "source_category": "MISSING_HEADER",
                    "severity": "high",
                    "source_severity": "high",
                    "severity_reason": "Strict-Transport-Security header is absent on HTTPS target",
                    "confidence": "confirmed_configuration",
                    "title": "Missing Strict-Transport-Security Header",
                    "description": "HSTS instructs browsers to only connect over secure HTTPS, protecting against SSL stripping.",
                    "remediation": "Add 'Strict-Transport-Security: max-age=31536000; includeSubDomains'.",
                    "evidence": {
                        "url_display": url_display,
                        "status_code": self.response.status_code,
                        "header_names": list(self.response.headers.keys()),
                        "excerpts": [{"kind": "header", "value_redacted": "Strict-Transport-Security: <missing>"}],
                    },
                    "fingerprint": f"headers:hsts:missing:{self.domain}",
                })
            else:
                m = re.search(r"max-age\s*=\s*(\d+)", hsts, re.IGNORECASE)
                if not m:
                    # Malformed max-age
                    findings.append({
                        "check_id": "headers.hsts",
                        "category": "security_headers",
                        "source_category": "INSECURE_HEADER",
                        "severity": "medium",
                        "source_severity": "medium",
                        "severity_reason": "HSTS header max-age is malformed or invalid integer",
                        "confidence": "confirmed_configuration",
                        "title": "Malformed HSTS max-age Directive",
                        "description": f"HSTS header '{hsts}' does not specify a valid numeric max-age.",
                        "remediation": "Specify a valid numeric max-age (e.g., max-age=31536000).",
                        "evidence": {
                            "url_display": url_display,
                            "status_code": self.response.status_code,
                            "header_names": list(self.response.headers.keys()),
                            "excerpts": [{"kind": "header", "value_redacted": f"Strict-Transport-Security: {hsts}"}],
                        },
                        "fingerprint": f"headers:hsts:malformed:{self.domain}",
                    })
                else:
                    max_age = int(m.group(1))
                    if max_age < 31536000:
                        findings.append({
                            "check_id": "headers.hsts",
                            "category": "security_headers",
                            "source_category": "INSECURE_HEADER",
                            "severity": "low",
                            "source_severity": "low",
                            "severity_reason": f"HSTS max-age ({max_age}s) is less than recommended 1 year (31536000s)",
                            "confidence": "confirmed_configuration",
                            "title": "HSTS max-age Duration Too Short",
                            "description": "HSTS duration should be at least 31536000 seconds (1 year) for optimal protection.",
                            "remediation": "Increase max-age to 31536000 or greater.",
                            "evidence": {
                                "url_display": url_display,
                                "status_code": self.response.status_code,
                                "header_names": list(self.response.headers.keys()),
                                "excerpts": [{"kind": "header", "value_redacted": f"Strict-Transport-Security: {hsts}"}],
                            },
                            "fingerprint": f"headers:hsts:short_duration:{self.domain}",
                        })
                    if "includesubdomains" not in hsts.lower():
                        findings.append({
                            "check_id": "headers.hsts",
                            "category": "security_headers",
                            "source_category": "INSECURE_HEADER",
                            "severity": "low",
                            "source_severity": "low",
                            "severity_reason": "HSTS header does not include 'includeSubDomains' directive",
                            "confidence": "confirmed_configuration",
                            "title": "HSTS Missing includeSubDomains",
                            "description": "Without includeSubDomains, subdomains remain vulnerable to SSL stripping attacks.",
                            "remediation": "Add 'includeSubDomains' to the Strict-Transport-Security header.",
                            "evidence": {
                                "url_display": url_display,
                                "status_code": self.response.status_code,
                                "header_names": list(self.response.headers.keys()),
                                "excerpts": [{"kind": "header", "value_redacted": f"Strict-Transport-Security: {hsts}"}],
                            },
                            "fingerprint": f"headers:hsts:missing_subdomains:{self.domain}",
                        })

        # ── 3. X-Frame-Options (XFO) ──────────────────────────────────────
        xfo = headers.get("x-frame-options")
        has_frame_ancestors = csp and "frame-ancestors" in csp.lower()
        if not xfo and not has_frame_ancestors:
            findings.append({
                "check_id": "headers.x_frame_options",
                "category": "security_headers",
                "source_category": "MISSING_HEADER",
                "severity": "medium",
                "source_severity": "medium",
                "severity_reason": "X-Frame-Options is absent and CSP frame-ancestors is not configured",
                "confidence": "confirmed_configuration",
                "title": "Missing X-Frame-Options Header",
                "description": "X-Frame-Options prevents the website from being embedded in an iframe, mitigating clickjacking.",
                "remediation": "Set 'X-Frame-Options: DENY' or 'X-Frame-Options: SAMEORIGIN'.",
                "evidence": {
                    "url_display": url_display,
                    "status_code": self.response.status_code,
                    "header_names": list(self.response.headers.keys()),
                    "excerpts": [{"kind": "header", "value_redacted": "X-Frame-Options: <missing>"}],
                },
                "fingerprint": f"headers:xfo:missing:{self.domain}",
            })
        elif xfo and xfo.strip().upper() not in ("DENY", "SAMEORIGIN"):
            findings.append({
                "check_id": "headers.x_frame_options",
                "category": "security_headers",
                "source_category": "INSECURE_HEADER",
                "severity": "low",
                "source_severity": "low",
                "severity_reason": f"Non-standard X-Frame-Options value: '{xfo}'",
                "confidence": "confirmed_configuration",
                "title": "Non-Standard X-Frame-Options Header Value",
                "description": "Deprecated or non-standard values like ALLOW-FROM are not supported in modern browsers.",
                "remediation": "Change X-Frame-Options value to DENY or SAMEORIGIN.",
                "evidence": {
                    "url_display": url_display,
                    "status_code": self.response.status_code,
                    "header_names": list(self.response.headers.keys()),
                    "excerpts": [{"kind": "header", "value_redacted": f"X-Frame-Options: {xfo}"}],
                },
                "fingerprint": f"headers:xfo:nonstandard:{self.domain}",
            })

        # ── 4. X-Content-Type-Options (XCTO) ──────────────────────────────
        xcto = headers.get("x-content-type-options")
        if not xcto:
            findings.append({
                "check_id": "headers.x_content_type_options",
                "category": "security_headers",
                "source_category": "MISSING_HEADER",
                "severity": "medium",
                "source_severity": "medium",
                "severity_reason": "X-Content-Type-Options header is absent",
                "confidence": "confirmed_configuration",
                "title": "Missing X-Content-Type-Options Header",
                "description": "Prevents browsers from MIME-sniffing a response away from the declared content-type.",
                "remediation": "Set 'X-Content-Type-Options: nosniff'.",
                "evidence": {
                    "url_display": url_display,
                    "status_code": self.response.status_code,
                    "header_names": list(self.response.headers.keys()),
                    "excerpts": [{"kind": "header", "value_redacted": "X-Content-Type-Options: <missing>"}],
                },
                "fingerprint": f"headers:xcto:missing:{self.domain}",
            })
        elif xcto.strip().lower() != "nosniff":
            findings.append({
                "check_id": "headers.x_content_type_options",
                "category": "security_headers",
                "source_category": "INSECURE_HEADER",
                "severity": "low",
                "source_severity": "low",
                "severity_reason": f"X-Content-Type-Options is '{xcto}' instead of exact 'nosniff'",
                "confidence": "confirmed_configuration",
                "title": "Invalid X-Content-Type-Options Value",
                "description": "Only 'nosniff' is a valid recognized value for X-Content-Type-Options.",
                "remediation": "Set 'X-Content-Type-Options: nosniff'.",
                "evidence": {
                    "url_display": url_display,
                    "status_code": self.response.status_code,
                    "header_names": list(self.response.headers.keys()),
                    "excerpts": [{"kind": "header", "value_redacted": f"X-Content-Type-Options: {xcto}"}],
                },
                "fingerprint": f"headers:xcto:invalid:{self.domain}",
            })

        # ── 5. Permissions-Policy / Feature-Policy ────────────────────────
        perm_pol = headers.get("permissions-policy") or headers.get("feature-policy")
        if not perm_pol:
            findings.append({
                "check_id": "headers.permissions_policy",
                "category": "security_headers",
                "source_category": "MISSING_HEADER",
                "severity": "low",
                "source_severity": "low",
                "severity_reason": "Neither Permissions-Policy nor Feature-Policy header is configured",
                "confidence": "confirmed_configuration",
                "title": "Missing Permissions-Policy Header",
                "description": "Permissions-Policy restricts access to browser features (camera, microphone, geolocation).",
                "remediation": "Configure Permissions-Policy (e.g., 'geolocation=(), camera=(), microphone=()').",
                "evidence": {
                    "url_display": url_display,
                    "status_code": self.response.status_code,
                    "header_names": list(self.response.headers.keys()),
                    "excerpts": [{"kind": "header", "value_redacted": "Permissions-Policy: <missing>"}],
                },
                "fingerprint": f"headers:permissions_policy:missing:{self.domain}",
            })

        # ── 6. Referrer-Policy ────────────────────────────────────────────
        ref_pol = headers.get("referrer-policy")
        if not ref_pol:
            findings.append({
                "check_id": "headers.referrer_policy",
                "category": "security_headers",
                "source_category": "MISSING_HEADER",
                "severity": "low",
                "source_severity": "low",
                "severity_reason": "Referrer-Policy header is absent",
                "confidence": "confirmed_configuration",
                "title": "Missing Referrer-Policy Header",
                "description": "Referrer-Policy governs how much referrer information is sent along with requests.",
                "remediation": "Set 'Referrer-Policy: strict-origin-when-cross-origin' or 'no-referrer'.",
                "evidence": {
                    "url_display": url_display,
                    "status_code": self.response.status_code,
                    "header_names": list(self.response.headers.keys()),
                    "excerpts": [{"kind": "header", "value_redacted": "Referrer-Policy: <missing>"}],
                },
                "fingerprint": f"headers:referrer_policy:missing:{self.domain}",
            })

        return {
            "findings": findings,
            "observations": observations,
            "status": "completed",
        }
