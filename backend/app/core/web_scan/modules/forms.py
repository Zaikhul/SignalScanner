from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import urlsplit

from app.core.web_scan.html_parser import DiscoveredForm, parse_page_html
from app.core.web_scan.http_client import WebScanResponse


class FormsModule:
    """Discovers HTML forms and audits for weak login methods and missing CSRF tokens."""

    def __init__(self, root_response: WebScanResponse, target_url: str):
        self.response = root_response
        self.target_url = target_url
        parts = urlsplit(target_url)
        self.domain = parts.hostname or ""

    def run(self) -> Dict[str, Any]:
        findings = []
        observations = []

        forms, links = parse_page_html(self.target_url, self.response.text)

        for i, form in enumerate(forms, start=1):
            form_id = f"form_{i}_{form.method.lower()}"
            has_pw = form.has_password_field
            has_csrf = form.has_csrf_token

            observations.append({
                "kind": "form",
                "module": "forms",
                "data": {
                    "form_id": form_id,
                    "action_display": form.action,
                    "method": form.method,
                    "allowed": True,
                    "fields": [f.to_dict() for f in form.fields],
                    "token_name_detected": has_csrf,
                    "fields_truncated": False,
                },
            })

            # Check 1: Weak Form (Password submitted over GET)
            if has_pw and form.method == "GET":
                findings.append({
                    "check_id": "forms.weak_login_get",
                    "category": "form_vulnerability",
                    "source_category": "WEAK_FORM",
                    "severity": "high",
                    "source_severity": "high",
                    "severity_reason": "Form contains password field but uses HTTP GET method",
                    "confidence": "confirmed_configuration",
                    "title": f"Sensitive Credentials Transmitted via GET ({form.action})",
                    "description": "Submitting password inputs using HTTP GET exposes credentials in browser history, server logs, and Referer headers.",
                    "remediation": "Change the form method to POST and ensure transmission occurs over HTTPS.",
                    "evidence": {
                        "url_display": form.action,
                        "method": "GET",
                        "status_code": self.response.status_code,
                        "excerpts": [{"kind": "text", "value_redacted": f"Form #{i} action={form.action} method=GET with password input"}],
                    },
                    "fingerprint": f"forms:weak_login_get:{self.domain}:{form.action}",
                })

            # Check 2: Missing CSRF Token in POST Form
            if form.method == "POST" and not has_csrf:
                findings.append({
                    "check_id": "forms.missing_csrf_token",
                    "category": "csrf_protection",
                    "source_category": "FORM_WARNING",
                    "severity": "low",
                    "source_severity": "low",
                    "severity_reason": "State-changing POST form does not contain anti-CSRF token name",
                    "confidence": "suspected",
                    "title": f"Possible Missing CSRF Token ({form.action})",
                    "description": "Form uses POST method without a detectable anti-CSRF token (e.g. csrf_token, xsrf_token, _token).",
                    "remediation": "Implement anti-CSRF tokens for all state-changing HTML forms.",
                    "evidence": {
                        "url_display": form.action,
                        "method": "POST",
                        "status_code": self.response.status_code,
                        "excerpts": [{"kind": "text", "value_redacted": f"Form #{i} action={form.action} method=POST without CSRF field"}],
                    },
                    "fingerprint": f"forms:missing_csrf:{self.domain}:{form.action}:{i}",
                })

        return {
            "findings": findings,
            "observations": observations,
            "discovered_forms": forms,
            "discovered_links": links,
            "status": "completed",
        }
