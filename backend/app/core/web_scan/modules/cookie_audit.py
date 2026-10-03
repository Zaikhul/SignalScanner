from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import urlsplit

from app.core.web_scan.http_client import WebScanResponse

SESSION_NAME_PATTERNS = ("sess", "token", "auth", "id", "jwt", "sid", "login", "ticket")


class CookieAuditModule:
    """Audits Set-Cookie headers for HttpOnly, Secure, and SameSite protection flags."""

    def __init__(self, root_response: WebScanResponse, target_url: str):
        self.response = root_response
        self.target_url = target_url
        parts = urlsplit(target_url)
        self.scheme = parts.scheme.lower()
        self.domain = parts.hostname or ""

    def _is_session_cookie(self, name: str) -> bool:
        lower = name.lower()
        return any(p in lower for p in SESSION_NAME_PATTERNS)

    def run(self) -> Dict[str, Any]:
        findings = []
        observations = []

        set_cookies = self.response.set_cookie_headers
        for raw_cookie in set_cookies:
            # Parse attributes using semicolon delimiter
            parts = [p.strip() for p in raw_cookie.split(";")]
            if not parts or "=" not in parts[0]:
                continue

            name_val = parts[0].split("=", 1)
            cookie_name = name_val[0].strip()
            # Security rule: immediately discard cookie_value! Do not store or log
            cookie_val_redacted = "<redacted>"

            # Exact attribute extraction
            is_http_only = False
            is_secure = False
            same_site: Optional[str] = None
            cookie_domain: Optional[str] = None
            cookie_path: Optional[str] = None

            for attr in parts[1:]:
                attr_lower = attr.lower()
                if attr_lower == "httponly":
                    is_http_only = True
                elif attr_lower == "secure":
                    is_secure = True
                elif attr_lower.startswith("samesite"):
                    if "=" in attr:
                        same_site = attr.split("=", 1)[1].strip().lower()
                    else:
                        same_site = "invalid"
                elif attr_lower.startswith("domain="):
                    cookie_domain = attr.split("=", 1)[1].strip()
                elif attr_lower.startswith("path="):
                    cookie_path = attr.split("=", 1)[1].strip()

            is_session = self._is_session_cookie(cookie_name)

            # Record observation
            observations.append({
                "kind": "cookie",
                "module": "cookies",
                "data": {
                    "name": cookie_name,
                    "domain": cookie_domain,
                    "path": cookie_path,
                    "session_name_hint": is_session,
                    "secure": is_secure,
                    "http_only": is_http_only,
                    "same_site": same_site,
                    "duplicate_attributes": [],
                    "parse_error": None,
                },
            })

            # Check 1: HttpOnly
            if not is_http_only:
                sev = "high" if is_session else "medium"
                findings.append({
                    "check_id": "cookies.httponly",
                    "category": "cookie_security",
                    "source_category": "INSECURE_COOKIE",
                    "severity": sev,
                    "source_severity": "high" if is_session else "medium",
                    "severity_reason": f"Cookie '{cookie_name}' lacks HttpOnly flag (Session indicator: {is_session})",
                    "confidence": "confirmed_configuration",
                    "title": f"Cookie Without HttpOnly: {cookie_name}",
                    "description": f"The cookie '{cookie_name}' was issued without the HttpOnly attribute, making it readable by JavaScript via document.cookie.",
                    "remediation": f"Set the 'HttpOnly' flag when creating the '{cookie_name}' cookie.",
                    "evidence": {
                        "url_display": self.response.url,
                        "status_code": self.response.status_code,
                        "header_names": ["set-cookie"],
                        "excerpts": [{"kind": "cookie_attribute", "value_redacted": f"{cookie_name}={cookie_val_redacted}; (HttpOnly missing)"}],
                    },
                    "fingerprint": f"cookies:httponly:missing:{self.domain}:{cookie_name}",
                })

            # Check 2: Secure
            if self.scheme == "https" and not is_secure:
                sev = "high" if is_session else "medium"
                findings.append({
                    "check_id": "cookies.secure",
                    "category": "cookie_security",
                    "source_category": "INSECURE_COOKIE",
                    "severity": sev,
                    "source_severity": "high" if is_session else "medium",
                    "severity_reason": f"Cookie '{cookie_name}' lacks Secure flag on HTTPS connection",
                    "confidence": "confirmed_configuration",
                    "title": f"Cookie Without Secure Flag: {cookie_name}",
                    "description": f"The cookie '{cookie_name}' can be transmitted in cleartext over unencrypted HTTP connections.",
                    "remediation": f"Set the 'Secure' attribute on cookie '{cookie_name}'.",
                    "evidence": {
                        "url_display": self.response.url,
                        "status_code": self.response.status_code,
                        "header_names": ["set-cookie"],
                        "excerpts": [{"kind": "cookie_attribute", "value_redacted": f"{cookie_name}={cookie_val_redacted}; (Secure missing)"}],
                    },
                    "fingerprint": f"cookies:secure:missing:{self.domain}:{cookie_name}",
                })

            # Check 3: SameSite
            if not same_site:
                findings.append({
                    "check_id": "cookies.samesite",
                    "category": "cookie_security",
                    "source_category": "INSECURE_COOKIE",
                    "severity": "medium",
                    "source_severity": "medium",
                    "severity_reason": f"Cookie '{cookie_name}' lacks SameSite attribute",
                    "confidence": "confirmed_configuration",
                    "title": f"Cookie Without SameSite Attribute: {cookie_name}",
                    "description": f"Without SameSite specified, browsers may send '{cookie_name}' on cross-site requests, increasing CSRF risk.",
                    "remediation": "Configure SameSite=Lax or SameSite=Strict.",
                    "evidence": {
                        "url_display": self.response.url,
                        "status_code": self.response.status_code,
                        "header_names": ["set-cookie"],
                        "excerpts": [{"kind": "cookie_attribute", "value_redacted": f"{cookie_name}={cookie_val_redacted}; (SameSite missing)"}],
                    },
                    "fingerprint": f"cookies:samesite:missing:{self.domain}:{cookie_name}",
                })
            elif same_site == "none" and not is_secure:
                findings.append({
                    "check_id": "cookies.samesite",
                    "category": "cookie_security",
                    "source_category": "INSECURE_COOKIE",
                    "severity": "high",
                    "source_severity": "high",
                    "severity_reason": f"Cookie '{cookie_name}' specifies SameSite=None without Secure flag",
                    "confidence": "confirmed_configuration",
                    "title": f"Cookie SameSite=None Without Secure: {cookie_name}",
                    "description": "SameSite=None cookies must include the Secure flag, otherwise modern browsers reject them.",
                    "remediation": "Add the 'Secure' attribute whenever using 'SameSite=None'.",
                    "evidence": {
                        "url_display": self.response.url,
                        "status_code": self.response.status_code,
                        "header_names": ["set-cookie"],
                        "excerpts": [{"kind": "cookie_attribute", "value_redacted": f"{cookie_name}={cookie_val_redacted}; SameSite=None; (Secure missing)"}],
                    },
                    "fingerprint": f"cookies:samesite:none_insecure:{self.domain}:{cookie_name}",
                })

        return {
            "findings": findings,
            "observations": observations,
            "status": "completed",
        }
