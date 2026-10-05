from __future__ import annotations

import logging
import random
from typing import Any, Dict, List
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from app.core.web_scan.html_parser import DiscoveredForm, FormField
from app.core.web_scan.http_client import WebScanHttpClient, WebScanResponse
from app.core.web_scan.payload_catalog import (
    DATABASE_ERROR_SIGNATURES,
    SQL_DIAGNOSTIC_PAYLOADS,
    get_random_mutated_payload,
)

logger = logging.getLogger("signal_scanner.web_scan.parameters")


class ParametersModule:
    """Audits form and query parameters for SQL/NoSQL error reflections, XSS, and timing delays."""

    def __init__(
        self,
        http_client: WebScanHttpClient,
        target_url: str,
        discovered_forms: List[DiscoveredForm],
        seed: int = 310,
        mutation_profile: str = "aggressive",
    ):
        self.http = http_client
        self.target_url = target_url
        self.seed = seed
        self.mutation_profile = mutation_profile
        self.rng = random.Random(seed)
        parts = urlsplit(target_url)
        self.domain = parts.hostname or ""

        # Aggregate discovered forms and query parameters from target URL (F-23)
        self.forms: List[DiscoveredForm] = list(discovered_forms)

        # Extract target URL query parameters
        if parts.query:
            query_pairs = parse_qsl(parts.query, keep_blank_values=True)
            if query_pairs:
                base_action = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
                query_fields = [
                    FormField(name=k, input_type="query", value=v)
                    for k, v in query_pairs
                    if k
                ]
                if query_fields:
                    self.forms.append(
                        DiscoveredForm(
                            action=base_action,
                            method="GET",
                            fields=query_fields,
                        )
                    )

    async def run(self) -> Dict[str, Any]:
        findings = []
        observations = []
        tested_params_count = 0

        for form in self.forms:
            # Baseline data preserving companion fields and initial values (F06)
            base_data = {f.name: (f.value or "") for f in form.fields if f.name}

            # 1. Obtain endpoint-specific baseline request (F07)
            if form.method == "POST":
                base_resp = await self.http.fetch(form.action, method="POST", data=base_data)
            else:
                base_resp = await self.http.fetch(form.action, method="GET", params=base_data)

            base_len = len(base_resp.text) if base_resp else 0
            base_elapsed = base_resp.elapsed_ms if base_resp else 100.0
            base_text_lower = base_resp.text.lower() if base_resp else ""
            baseline_errors = {err for err in DATABASE_ERROR_SIGNATURES if err in base_text_lower}

            for field in form.fields:
                param_name = field.name
                if not param_name or field.input_type == "password":
                    continue

                tested_params_count += 1

                for raw_payload in SQL_DIAGNOSTIC_PAYLOADS:
                    if self.mutation_profile == "none":
                        payload = raw_payload
                    else:
                        payload = get_random_mutated_payload(raw_payload, rng=self.rng)

                    # Preserve companion fields, replacing only the active parameter (F06)
                    req_payload = dict(base_data)
                    req_payload[param_name] = payload

                    # Test GET query or POST form data
                    if form.method == "POST":
                        t_resp = await self.http.fetch(form.action, method="POST", data=req_payload)
                    else:
                        t_resp = await self.http.fetch(form.action, method="GET", params=req_payload)

                    if not t_resp:
                        continue

                    resp_text_lower = t_resp.text.lower()

                    # ── Check 1: SQL/NoSQL Error Signatures with Baseline Subtraction (F05) ──
                    matched_error = next(
                        (err for err in DATABASE_ERROR_SIGNATURES if err in resp_text_lower and err not in baseline_errors),
                        None,
                    )
                    if matched_error:
                        cat = "SQLI" if any(k in matched_error for k in ("sql", "mysql", "ora", "postgres", "sqlite")) else "NOSQL_INJECT"
                        findings.append({
                            "module": "parameters",
                            "check_id": "parameters.sql_error_matching",
                            "category": "injection_vulnerability",
                            "source_category": cat,
                            "severity": "critical",
                            "source_severity": "critical",
                            "severity_reason": f"Database error signature '{matched_error}' reflected in response (not in baseline)",
                            "confidence": "suspected",
                            "title": f"Potential SQL/NoSQL Error Injection in '{param_name}'",
                            "description": f"Target reflected a new database error message '{matched_error}' when parameter was injected with diagnostic input.",
                            "remediation": "Use parameterized queries / prepared statements and disable verbose database error messages.",
                            "evidence": {
                                "url_display": form.action,
                                "method": form.method,
                                "status_code": t_resp.status_code,
                                "excerpts": [{"kind": "text", "value_redacted": f"Matched signature: {matched_error} on payload '{payload[:25]}...'"}],
                                "elapsed_ms": t_resp.elapsed_ms,
                            },
                            "fingerprint": f"params:error:{self.domain}:{form.action}:{param_name}:{matched_error}",
                        })

                    # ── Check 2: XSS Reflection with HTML Escaping Verification (F05) ────────
                    if "ghost_reflection_marker_2026" in t_resp.text:
                        raw_tag = "<svg/onload=ghost_reflection_marker_2026>"
                        escaped_tag = "&lt;svg/onload=ghost_reflection_marker_2026&gt;"
                        # Flag as XSS only if reflection is unescaped or in an executable context
                        is_unescaped = (raw_tag in t_resp.text) or ("<" in t_resp.text and escaped_tag not in t_resp.text and "&quot;" not in t_resp.text)

                        if is_unescaped:
                            findings.append({
                                "module": "parameters",
                                "check_id": "parameters.xss_reflection",
                                "category": "xss_reflection",
                                "source_category": "XSS",
                                "severity": "medium",
                                "source_severity": "medium",
                                "severity_reason": "Diagnostic marker was reflected verbatim in response without HTML entity encoding",
                                "confidence": "suspected",
                                "title": f"Reflected Input in Parameter '{param_name}'",
                                "description": "The diagnostic marker was reflected unencoded in the HTML response, indicating potential XSS.",
                                "remediation": "Contextually encode user input before rendering it into HTML documents.",
                                "evidence": {
                                    "url_display": form.action,
                                    "method": form.method,
                                    "status_code": t_resp.status_code,
                                    "excerpts": [{"kind": "text", "value_redacted": "Diagnostic marker reflected unencoded in body"}],
                                    "elapsed_ms": t_resp.elapsed_ms,
                                },
                                "fingerprint": f"params:xss:{self.domain}:{form.action}:{param_name}",
                            })
                        else:
                            observations.append({
                                "kind": "xss_reflection_encoded",
                                "module": "parameters",
                                "data": {
                                    "parameter_name": param_name,
                                    "catalog_entry_id": "xss_marker_properly_escaped",
                                    "status": "encoded_safe",
                                },
                            })

                    # ── Check 3: Time-based delay detection with endpoint baseline (F07) ─────
                    if t_resp.elapsed_ms > (base_elapsed + 4000.0) and any(kw in raw_payload.lower() for kw in ("sleep", "waitfor")):
                        findings.append({
                            "module": "parameters",
                            "check_id": "parameters.time_based_delay",
                            "category": "injection_vulnerability",
                            "source_category": "SQL_TIME_BASED",
                            "severity": "high",
                            "source_severity": "high",
                            "severity_reason": f"Response took {t_resp.elapsed_ms/1000.0:.2f}s, exceeding endpoint baseline delay ({base_elapsed:.1f}ms by >4.0s)",
                            "confidence": "suspected",
                            "title": f"Time-Based Delay Indication in '{param_name}'",
                            "description": "A time-based diagnostic payload caused a substantial delay compared to the endpoint baseline request.",
                            "remediation": "Ensure parameter queries are fully parameterized and enforce execution timeouts.",
                            "evidence": {
                                "url_display": form.action,
                                "method": form.method,
                                "status_code": t_resp.status_code,
                                "elapsed_ms": t_resp.elapsed_ms,
                                "baseline_elapsed_ms": base_elapsed,
                                "excerpts": [{"kind": "timing", "value_redacted": f"Elapsed {t_resp.elapsed_ms:.1f}ms vs endpoint baseline {base_elapsed:.1f}ms"}],
                            },
                            "fingerprint": f"params:time:{self.domain}:{form.action}:{param_name}",
                        })

                    # ── Check 4: Paired Boolean Comparison (True vs False Probes) (F07) ──────
                    if raw_payload == "' OR 1=1--" and t_resp.status_code == 200:
                        false_raw = "' OR 1=2--"
                        false_payload = false_raw if self.mutation_profile == "none" else get_random_mutated_payload(false_raw, rng=self.rng)
                        false_req_data = dict(base_data)
                        false_req_data[param_name] = false_payload

                        if form.method == "POST":
                            false_resp = await self.http.fetch(form.action, method="POST", data=false_req_data)
                        else:
                            false_resp = await self.http.fetch(form.action, method="GET", params=false_req_data)

                        if false_resp and false_resp.status_code in (200, 404, 500):
                            diff_true_false = abs(len(t_resp.text) - len(false_resp.text))
                            diff_false_base = abs(len(false_resp.text) - base_len)
                            if diff_true_false > 50 and (diff_false_base > 50 or abs(len(t_resp.text) - base_len) < 50):
                                observations.append({
                                    "kind": "comparison",
                                    "module": "parameters",
                                    "data": {
                                        "parameter_name": param_name,
                                        "catalog_entry_id": "boolean_differential_probe",
                                        "baseline_request_ids": [],
                                        "probe_request_ids": [],
                                        "deltas_ms": [t_resp.elapsed_ms - base_elapsed, false_resp.elapsed_ms - base_elapsed],
                                        "body_length_deltas": [diff_true_false],
                                        "rule_id": "parameters.boolean_length_delta",
                                        "conclusion": "suspected",
                                        "reason_code": "differential_response_between_boolean_true_and_false",
                                    },
                                })

        status_str = "completed" if tested_params_count > 0 else "skipped"
        reason_str = None if tested_params_count > 0 else "NO_PARAMETERS_FOUND"
        return {
            "findings": findings,
            "observations": observations,
            "status": status_str,
            "reason": reason_str,
        }
