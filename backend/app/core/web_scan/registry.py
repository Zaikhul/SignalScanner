from __future__ import annotations

from typing import Dict, List
from app.config import settings
from app.schemas.web_scan import (
    Capabilities,
    CheckCapabilityDescriptor,
    ModuleId,
    ProfileDescriptor,
    ProfileId,
    ScanConfiguration,
    Severity,
    SourceCommits,
)

# Registry of check capabilities across Ghost Web Scanner and legacy variants
CHECK_CAPABILITIES: List[CheckCapabilityDescriptor] = [
    # Recon Checks (C-11, C-12, C-13, C-14, C-15, C-16)
    CheckCapabilityDescriptor(
        check_id="recon.server_banner",
        module=ModuleId.RECON,
        c_id="C-12",
        title="Server Banner & Backend Discovery",
        description="Inspect Server header, X-Powered-By, and PHP session indicators",
        default_severity=Severity.INFO,
        applicability="all_targets",
    ),
    CheckCapabilityDescriptor(
        check_id="recon.waf_detection",
        module=ModuleId.RECON,
        c_id="C-13",
        title="Web Application Firewall Detection",
        description="Match signatures for Cloudflare, ModSecurity, Sucuri, Akamai, Imperva, AWS WAF",
        default_severity=Severity.INFO,
        applicability="all_targets",
    ),
    CheckCapabilityDescriptor(
        check_id="recon.cms_detection",
        module=ModuleId.RECON,
        c_id="C-14",
        title="Content Management System Detection",
        description="Fingerprint WordPress, Joomla, Drupal, Shopify, Wix from response body signatures",
        default_severity=Severity.INFO,
        applicability="html_responses",
    ),
    CheckCapabilityDescriptor(
        check_id="recon.subdomain_enumeration",
        module=ModuleId.RECON,
        c_id="C-15",
        title="Subdomain Enumeration",
        description="Brute-force common subdomains using profile wordlists (v2/v47/v75)",
        default_severity=Severity.LOW,
        applicability="dns_names_only",
    ),
    CheckCapabilityDescriptor(
        check_id="recon.path_enumeration",
        module=ModuleId.RECON,
        c_id="C-16",
        title="Directory and Path Enumeration",
        description="Probe sensitive endpoints, backup files, configuration leaks, and admin panels",
        default_severity=Severity.MEDIUM,
        applicability="all_targets",
    ),
    CheckCapabilityDescriptor(
        check_id="recon.geolocation",
        module=ModuleId.RECON,
        c_id="C-11",
        title="IP Geolocation and ASN Lookup",
        description="Optional provider query for city, country, and ASN details",
        default_severity=Severity.INFO,
        applicability="public_ip_only",
        default_enabled=False,
    ),

    # Security Headers Checks (C-29, C-30, C-31, C-32, C-33, C-34)
    CheckCapabilityDescriptor(
        check_id="headers.csp",
        module=ModuleId.HEADERS,
        c_id="C-29",
        title="Content-Security-Policy (CSP) Audit",
        description="Detect missing CSP or usage of unsafe directives (unsafe-inline, unsafe-eval)",
        default_severity=Severity.HIGH,
        applicability="html_responses",
    ),
    CheckCapabilityDescriptor(
        check_id="headers.hsts",
        module=ModuleId.HEADERS,
        c_id="C-30",
        title="HTTP Strict Transport Security (HSTS) Audit",
        description="Audit HSTS presence, minimum max-age (31536000s), and includeSubDomains on HTTPS",
        default_severity=Severity.HIGH,
        applicability="https_only",
    ),
    CheckCapabilityDescriptor(
        check_id="headers.x_frame_options",
        module=ModuleId.HEADERS,
        c_id="C-31",
        title="X-Frame-Options Clickjacking Protection",
        description="Ensure X-Frame-Options is set to DENY or SAMEORIGIN (or CSP frame-ancestors present)",
        default_severity=Severity.MEDIUM,
        applicability="html_responses",
    ),
    CheckCapabilityDescriptor(
        check_id="headers.x_content_type_options",
        module=ModuleId.HEADERS,
        c_id="C-32",
        title="X-Content-Type-Options MIME Sniffing Audit",
        description="Ensure X-Content-Type-Options is exactly set to 'nosniff'",
        default_severity=Severity.MEDIUM,
        applicability="all_responses",
    ),
    CheckCapabilityDescriptor(
        check_id="headers.permissions_policy",
        module=ModuleId.HEADERS,
        c_id="C-33",
        title="Permissions-Policy and Feature-Policy Audit",
        description="Audit presence of modern browser Permissions-Policy or legacy Feature-Policy",
        default_severity=Severity.LOW,
        applicability="all_responses",
    ),
    CheckCapabilityDescriptor(
        check_id="headers.referrer_policy",
        module=ModuleId.HEADERS,
        c_id="C-34",
        title="Referrer-Policy Information Leakage Audit",
        description="Verify presence of strict Referrer-Policy to prevent URL leakage",
        default_severity=Severity.LOW,
        applicability="all_responses",
    ),

    # Cookie Security Checks (C-35, C-36, C-37)
    CheckCapabilityDescriptor(
        check_id="cookies.httponly",
        module=ModuleId.COOKIES,
        c_id="C-36",
        title="Cookie HttpOnly Flag Audit",
        description="Verify HttpOnly flag on cookies to prevent access by malicious JavaScript",
        default_severity=Severity.HIGH,
        applicability="set_cookie_headers",
    ),
    CheckCapabilityDescriptor(
        check_id="cookies.secure",
        module=ModuleId.COOKIES,
        c_id="C-36",
        title="Cookie Secure Flag Audit",
        description="Verify Secure flag on cookies transported over HTTPS",
        default_severity=Severity.HIGH,
        applicability="https_only",
    ),
    CheckCapabilityDescriptor(
        check_id="cookies.samesite",
        module=ModuleId.COOKIES,
        c_id="C-37",
        title="Cookie SameSite Attribute Audit",
        description="Audit SameSite setting (Lax, Strict, or None with Secure) to mitigate CSRF",
        default_severity=Severity.MEDIUM,
        applicability="set_cookie_headers",
    ),

    # Form Checks (C-17, C-18)
    CheckCapabilityDescriptor(
        check_id="forms.weak_login_get",
        module=ModuleId.FORMS,
        c_id="C-17",
        title="Weak Form: Credential Submission via GET",
        description="Detect login/password forms using GET method instead of POST",
        default_severity=Severity.HIGH,
        applicability="html_forms",
    ),
    CheckCapabilityDescriptor(
        check_id="forms.missing_csrf_token",
        module=ModuleId.FORMS,
        c_id="C-18",
        title="Missing CSRF Token in Form POST",
        description="Heuristic detection of state-changing POST forms without anti-CSRF token",
        default_severity=Severity.LOW,
        applicability="html_forms",
    ),

    # Parameter Injection & Reflection Checks (C-19, C-20, C-21, C-22, C-23, C-24, C-25, C-26)
    CheckCapabilityDescriptor(
        check_id="parameters.sql_error_matching",
        module=ModuleId.PARAMETERS,
        c_id="C-21",
        title="SQL / NoSQL Database Error Reflection",
        description="Inject benign diagnostic quote and match database vendor error strings",
        default_severity=Severity.CRITICAL,
        applicability="forms_and_queries",
    ),
    CheckCapabilityDescriptor(
        check_id="parameters.xss_reflection",
        module=ModuleId.PARAMETERS,
        c_id="C-20",
        title="Reflected XSS Indicator Audit",
        description="Detect unencoded reflection of benign marker strings in response body",
        default_severity=Severity.MEDIUM,
        applicability="forms_and_queries",
    ),
    CheckCapabilityDescriptor(
        check_id="parameters.time_based_delay",
        module=ModuleId.PARAMETERS,
        c_id="C-23",
        title="Time-Based Latency Difference Check",
        description="Evaluate statistically significant response delay compared to baseline",
        default_severity=Severity.HIGH,
        applicability="forms_and_queries",
    ),
    CheckCapabilityDescriptor(
        check_id="parameters.boolean_length_delta",
        module=ModuleId.PARAMETERS,
        c_id="C-24",
        title="Boolean Comparison Response Difference",
        description="Detect response body length delta between true/false diagnostic conditions",
        default_severity=Severity.LOW,
        applicability="forms_and_queries",
    ),
    CheckCapabilityDescriptor(
        check_id="parameters.lfi_auth_bypass_indicator",
        module=ModuleId.PARAMETERS,
        c_id="C-25",
        title="Traversal & Auth Bypass Heuristic Marker",
        description="Catalog reference for traversal stimuli; predicate gap preserved honestly",
        default_severity=Severity.INFO,
        applicability="forms_and_queries",
        coverage_gap="Source lacked dedicated automated predicate; tracked as inconclusive signal",
    ),

    # Header Probes (C-27, C-28)
    CheckCapabilityDescriptor(
        check_id="header_probes.time_based_sql",
        module=ModuleId.HEADER_PROBES,
        c_id="C-28",
        title="Header Injection Time-Based Audit",
        description="Probe User-Agent and XFF with non-destructive timing diagnostic on internal links",
        default_severity=Severity.HIGH,
        applicability="discovered_links_max_10",
    ),

    # Load Resilience (C-38, C-39, C-41)
    CheckCapabilityDescriptor(
        check_id="stress.bounded_load_test",
        module=ModuleId.STRESS,
        c_id="C-38",
        title="Bounded Load Resilience Assessment",
        description="Send controlled concurrent GET/POST workload to measure RPS and HTTP failure rates",
        default_severity=Severity.LOW,
        applicability="authorized_load_targets_only",
        default_enabled=False,
    ),
]

PROFILES: List[ProfileDescriptor] = [
    ProfileDescriptor(
        profile_id=ProfileId.V2,
        name="Ghost v2.0 Standard Profile",
        description="Reconnaissance, 6 Security Header families, and Cookie audit (non-invasive)",
        modules=[ModuleId.RECON, ModuleId.HEADERS, ModuleId.COOKIES],
        default_checks=[
            "recon.server_banner", "recon.waf_detection", "recon.cms_detection",
            "recon.subdomain_enumeration", "recon.path_enumeration",
            "headers.csp", "headers.hsts", "headers.x_frame_options",
            "headers.x_content_type_options", "headers.permissions_policy", "headers.referrer_policy",
            "cookies.httponly", "cookies.secure", "cookies.samesite",
        ],
    ),
    ProfileDescriptor(
        profile_id=ProfileId.LEGACY_V47,
        name="Ghost v47 Legacy Force & Brute",
        description="Subdomain brute, directory brute, form discovery, and parameter error matching",
        modules=[ModuleId.RECON, ModuleId.FORMS, ModuleId.PARAMETERS],
        default_checks=[
            "recon.subdomain_enumeration", "recon.path_enumeration",
            "forms.weak_login_get", "forms.missing_csrf_token",
            "parameters.sql_error_matching", "parameters.xss_reflection",
        ],
    ),
    ProfileDescriptor(
        profile_id=ProfileId.LEGACY_V75,
        name="Ghost v75 Omni-Suite God-Mode",
        description="Recon, full form & parameter heuristics, header injection, and optional stress test",
        modules=[ModuleId.RECON, ModuleId.FORMS, ModuleId.PARAMETERS, ModuleId.HEADER_PROBES, ModuleId.STRESS],
        default_checks=[
            "recon.server_banner", "recon.waf_detection", "recon.cms_detection",
            "recon.subdomain_enumeration", "recon.path_enumeration",
            "forms.weak_login_get", "forms.missing_csrf_token",
            "parameters.sql_error_matching", "parameters.xss_reflection",
            "parameters.time_based_delay", "parameters.boolean_length_delta",
            "header_probes.time_based_sql",
        ],
    ),
    ProfileDescriptor(
        profile_id=ProfileId.COMPREHENSIVE,
        name="Comprehensive All-Modules Profile",
        description="All 7 modules: Recon, Headers, Cookies, Forms, Parameters, Header Probes, Stress",
        modules=[
            ModuleId.RECON, ModuleId.HEADERS, ModuleId.COOKIES,
            ModuleId.FORMS, ModuleId.PARAMETERS, ModuleId.HEADER_PROBES, ModuleId.STRESS,
        ],
        default_checks=[c.check_id for c in CHECK_CAPABILITIES],
    ),
]


def get_capabilities() -> Capabilities:
    """Returns the full capabilities catalog of the Web Scanner."""
    return Capabilities(
        schema_version="web_scan.v1",
        source_commits=SourceCommits(),
        engine_version="1.0.0",
        profiles=PROFILES,
        checks=CHECK_CAPABILITIES,
        defaults=ScanConfiguration(),
        hard_caps={
            "max_concurrency_ceiling": settings.WEB_SCAN_GLOBAL_MAX_CONCURRENCY,
            "per_origin_concurrency_ceiling": settings.WEB_SCAN_PER_ORIGIN_CONCURRENCY,
            "max_body_bytes": settings.WEB_SCAN_MAX_BODY_BYTES,
            "max_requests_ceiling": 5000,
            "job_timeout_seconds_ceiling": 3600,
            "discovered_links_ceiling": 10,
        },
        readiness={
            "enabled": settings.WEB_SCANNER_ENABLED,
            "database_ready": True,
            "http2_ready": True,
            "network_policy_active": True,
        },
    )


CAPABILITIES_CATALOG = get_capabilities()

