from app.core.web_scan.result_processor import (
    build_scan_result,
    calculate_risk_indices,
    compute_fingerprint,
    deduplicate_findings,
)
from app.schemas.web_scan import Severity


def test_fingerprint_and_deduplication():
    fp1 = compute_fingerprint("headers.csp", "Missing CSP", "example.com")
    fp2 = compute_fingerprint("headers.csp", "Missing CSP", "example.com")
    assert fp1 == fp2

    raw_items = [
        {
            "check_id": "headers.csp",
            "title": "Missing Content-Security-Policy",
            "domain": "example.com",
            "severity": "high",
            "fingerprint": fp1,
        },
        {
            "check_id": "headers.csp",
            "title": "Missing Content-Security-Policy",
            "domain": "example.com",
            "severity": "high",
            "fingerprint": fp1,
        },
    ]

    deduped = deduplicate_findings(raw_items, "scan_1")
    assert len(deduped) == 1
    assert deduped[0].occurrence_count == 2


def test_risk_formula_calculations():
    raw_findings = [
        {
            "check_id": "parameters.sqli",
            "title": "SQL Injection Detected",
            "source_category": "SQLI",
            "severity": "critical",
            "domain": "target.local",
        },
        {
            "check_id": "headers.csp",
            "title": "Missing CSP",
            "source_category": "MISSING_HEADER",
            "severity": "high",
            "domain": "target.local",
        },
    ]
    findings = deduplicate_findings(raw_findings, "scan_2")

    indices = calculate_risk_indices(findings)

    # V47: min(2 * 20, 100) = 40
    assert indices.v47["value"] == 40
    assert indices.v47["formula_version"] == "v47_count20"

    # V75 weights: SQLI (40) + MISSING_HEADER (15) = 55
    assert indices.v75["value"] == 55

    # V2 weights: SQLI (40) + MISSING_HEADER (15) = 55
    assert indices.v2["value"] == 55


def test_build_scan_result():
    raw_findings = [
        {"check_id": "c1", "title": "T1", "severity": "high", "domain": "a.com"},
        {"check_id": "c2", "title": "T2", "severity": "low", "domain": "a.com"},
    ]
    findings = deduplicate_findings(raw_findings, "scan_3")
    observations = [
        {"kind": "http_response", "data": {"status_code": 200}},
        {"kind": "http_response", "data": {"status_code": 404}},
    ]

    res = build_scan_result(findings, observations, errors_count=0)
    assert res.findings_total == 2
    assert res.counts_by_severity[Severity.HIGH.value] == 1
    assert res.counts_by_severity[Severity.LOW.value] == 1
    assert res.requests.completed == 2
    assert res.requests.http_2xx_3xx == 1
    assert res.requests.http_4xx == 1
