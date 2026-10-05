from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from app.schemas.web_scan import (
    Confidence,
    CoverageEntry,
    Evidence,
    LegacyIndices,
    LoadMetrics,
    ModuleId,
    RequestMetrics,
    ScanFinding,
    ScanObservation,
    ScanResult,
    Severity,
)

# V75 legacy risk weights
_V75_WEIGHTS: Dict[str, int] = {
    "CRITICAL_VULN": 45,
    "SQLI": 40,
    "CRITICAL_BLIND_SQLI": 45,
    "BLIND_SQLI": 45,
    "SQL_TIME_BASED": 48,
    "SQL_BOOLEAN": 42,
    "NOSQL_INJECT": 40,
    "AUTH_BYPASS": 50,
    "LFI": 35,
    "DIREKTORI_SENSITIF": 20,
    "DIRECTORY": 15,
    "SUBDOMAIN": 10,
    "XSS": 25,
    "INFO": 5,
}

# V2 risk weights from local ghost_scanner/reports/json_report.py
_V2_WEIGHTS: Dict[str, int] = {
    "SQLI": 40,
    "NOSQL_INJECT": 40,
    "SQL_TIME_BASED": 48,
    "SQL_BOOLEAN": 42,
    "AUTH_BYPASS": 50,
    "BLIND_SQLI_HEADER": 45,
    "XSS": 25,
    "LFI": 35,
    "MISSING_HEADER": 15,
    "INSECURE_COOKIE": 20,
    "SENSITIVE_DIR": 20,
    "DIRECTORY": 10,
    "SUBDOMAIN": 5,
    "TECH_INFO": 3,
    "INFO": 3,
}


def compute_fingerprint(check_id: str, title: str, domain: str, extra: str = "") -> str:
    """Computes stable SHA256 fingerprint for finding deduplication."""
    raw = f"{check_id}|{title}|{domain}|{extra}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _resolve_finding_module(item: Dict[str, Any]) -> ModuleId:
    """Accurately identifies finding module provenance based on item field or check_id prefix (F-14)."""
    raw_mod = item.get("module")
    if raw_mod:
        try:
            return ModuleId(raw_mod)
        except ValueError:
            pass

    check_id = item.get("check_id", "")
    prefix = check_id.split(".")[0].lower() if "." in check_id else ""
    prefix_map = {
        "headers": ModuleId.HEADERS,
        "cookies": ModuleId.COOKIES,
        "forms": ModuleId.FORMS,
        "parameters": ModuleId.PARAMETERS,
        "header_probes": ModuleId.HEADER_PROBES,
        "stress": ModuleId.STRESS,
        "recon": ModuleId.RECON,
    }
    if prefix in prefix_map:
        return prefix_map[prefix]
    return ModuleId.RECON


def deduplicate_findings(raw_findings: List[Dict[str, Any]], scan_id: str) -> List[ScanFinding]:
    """Deduplicates raw findings by fingerprint and aggregates occurrence counts."""
    deduped: Dict[str, ScanFinding] = {}
    now = datetime.now(timezone.utc)

    for item in raw_findings:
        fp = item.get("fingerprint") or compute_fingerprint(
            item["check_id"], item["title"], item.get("domain", "")
        )

        if fp in deduped:
            deduped[fp].occurrence_count += 1
            deduped[fp].last_seen_at = now
        else:
            evidence_data = item.get("evidence", {})
            evidence_obj = Evidence(
                request_id=evidence_data.get("request_id"),
                observation_ids=evidence_data.get("observation_ids", []),
                url_display=evidence_data.get("url_display", ""),
                method=evidence_data.get("method"),
                status_code=evidence_data.get("status_code"),
                header_names=evidence_data.get("header_names", []),
                excerpts=evidence_data.get("excerpts", []),
                baseline_request_id=evidence_data.get("baseline_request_id"),
                control_request_ids=evidence_data.get("control_request_ids", []),
                elapsed_ms=evidence_data.get("elapsed_ms"),
                baseline_elapsed_ms=evidence_data.get("baseline_elapsed_ms"),
                body_length=evidence_data.get("body_length"),
                baseline_body_length=evidence_data.get("baseline_body_length"),
                body_truncated=evidence_data.get("body_truncated", False),
                catalog_entry_id=evidence_data.get("catalog_entry_id"),
            )

            mod_id = _resolve_finding_module(item)

            finding = ScanFinding(
                id=hashlib.md5(f"{scan_id}:{fp}".encode("utf-8")).hexdigest(),
                scan_id=scan_id,
                module=mod_id,
                check_id=item["check_id"],
                category=item.get("category", "general"),
                source_category=item.get("source_category"),
                severity=Severity(item.get("severity", "info").lower()),
                source_severity=Severity(item["source_severity"].lower()) if item.get("source_severity") else None,
                severity_reason=item.get("severity_reason", ""),
                confidence=Confidence(item.get("confidence", "confirmed_configuration")),
                title=item["title"],
                description=item.get("description", ""),
                remediation=item.get("remediation", ""),
                evidence=evidence_obj,
                fingerprint=fp,
                occurrence_count=1,
                first_seen_at=now,
                last_seen_at=now,
            )
            deduped[fp] = finding

    return list(deduped.values())


def score_to_risk_band(score: float) -> str:
    """Consistent, authoritative mapping from numerical risk score to risk band (F-21)."""
    if score >= 70:
        return "critical"
    elif score >= 50:
        return "high"
    elif score >= 30:
        return "medium"
    return "low"


def calculate_risk_indices(findings: List[ScanFinding]) -> LegacyIndices:
    """Calculates V47, V75, and V2 risk scores using exact formulas and consistent risk bands (F-21)."""
    # V47 formula: min(count * 20, 100)
    v47_count = len([f for f in findings if f.severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM)])
    v47_score = min(v47_count * 20, 100)
    v47_band = score_to_risk_band(v47_score)

    # V75 formula: sum of exact weights, capped at 100
    v75_points = 0
    for f in findings:
        if f.severity == Severity.INFO or f.confidence == Confidence.INCONCLUSIVE:
            continue
        cat = (f.source_category or f.category or "").upper()
        if cat in ("STRESS_TEST", "RESILIENCE_INFO", "TECH_INFO"):
            continue
        v75_points += _V75_WEIGHTS.get(cat, 15)
    v75_score = min(v75_points, 100)
    v75_band = score_to_risk_band(v75_score)

    # V2 formula: from local json_report.py ScanReport.calculate_risk()
    v2_points = 0
    for f in findings:
        if f.severity == Severity.INFO or f.confidence == Confidence.INCONCLUSIVE:
            continue
        cat = (f.source_category or f.category or "").upper()
        if cat in ("STRESS_TEST", "RESILIENCE_INFO", "TECH_INFO"):
            continue
        v2_points += _V2_WEIGHTS.get(cat, 10)
    v2_score = min(v2_points, 100)
    v2_band = score_to_risk_band(v2_score)

    return LegacyIndices(
        v47={
            "value": v47_score,
            "formula_version": "v47_count20",
            "source_band": v47_band,
        },
        v75={
            "value": v75_score,
            "formula_version": "v75_weights",
            "source_band": v75_band,
        },
        v2={
            "value": v2_score,
            "formula_version": "v2_json_report_weights",
            "source_band": v2_band,
        },
    )


def build_scan_result(
    findings: List[ScanFinding],
    observations: List[Dict[str, Any]],
    errors_count: int = 0,
    load_metrics_data: Optional[Dict[str, Any]] = None,
    coverage: Optional[List[CoverageEntry]] = None,
    request_metrics: Optional[RequestMetrics] = None,
) -> ScanResult:
    """Aggregates findings, observations, and authoritative request ledger metrics into a standardized ScanResult (F-16)."""
    counts: Dict[str, int] = {s.value: 0 for s in Severity}
    for f in findings:
        counts[f.severity.value] = counts.get(f.severity.value, 0) + 1

    legacy_indices = calculate_risk_indices(findings)

    # Use authoritative request ledger metrics if provided, else compile from observations (F-16)
    if request_metrics:
        req_metrics = request_metrics
    else:
        req_metrics = RequestMetrics()
        for obs in observations:
            if obs.get("kind") == "http_response":
                req_metrics.attempted += 1
                req_metrics.completed += 1
                sc = obs.get("data", {}).get("status_code", 200)
                if 200 <= sc < 400:
                    req_metrics.http_2xx_3xx += 1
                elif 400 <= sc < 500:
                    req_metrics.http_4xx += 1
                elif 500 <= sc < 600:
                    req_metrics.http_5xx += 1
                else:
                    req_metrics.http_other += 1

    load_metrics = None
    if load_metrics_data:
        load_metrics = LoadMetrics(
            attempted=load_metrics_data.get("attempted", 0),
            duration_ms=load_metrics_data.get("elapsed_ms", 0.0),
            average_rps=load_metrics_data.get("average_rps"),
            legacy_success_lt_500=load_metrics_data.get("legacy_success_lt_500", 0),
            legacy_failure=load_metrics_data.get("legacy_failure", 0),
            legacy_evaluated=load_metrics_data.get("legacy_success_lt_500", 0) + load_metrics_data.get("legacy_failure", 0),
            legacy_average_rps=load_metrics_data.get("average_rps"),
        )

    return ScanResult(
        counts_by_severity=counts,
        findings_total=len(findings),
        observations_total=len(observations),
        errors_total=errors_count,
        requests=req_metrics,
        load_metrics=load_metrics,
        legacy_indices=legacy_indices,
        coverage=coverage or [],
    )
