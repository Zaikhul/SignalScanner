import pytest
from app.core.web_scan.network_policy import (
    is_ip_allowed,
    parse_and_validate_target,
    sanitize_target_for_display,
    validate_and_normalize_target,
    validate_target_against_scope,
)
import ipaddress


def test_parse_valid_target_normalizes_properly():
    target = parse_and_validate_target("example.com")
    assert target.scheme == "http"
    assert target.hostname == "example.com"
    assert target.port == 80
    assert target.canonical_url == "http://example.com/"

    target_https = parse_and_validate_target("https://api.test.org:8443/v1/users?token=secret#fragment")
    assert target_https.scheme == "https"
    assert target_https.hostname == "api.test.org"
    assert target_https.port == 8443
    assert target_https.canonical_url == "https://api.test.org:8443/v1/users?token=secret"
    # Display URL must have query params redacted
    assert "token=%3Credacted%3E" in target_https.display_url
    assert "secret" not in target_https.display_url


def test_parse_rejects_credentials_and_invalid_schemes():
    with pytest.raises(ValueError, match="embedded userinfo or credentials"):
        parse_and_validate_target("http://admin:password@evil.com")

    with pytest.raises(ValueError, match="Unsupported scheme"):
        parse_and_validate_target("ftp://files.example.com")

    with pytest.raises(ValueError, match="Target URL cannot be empty"):
        parse_and_validate_target("   ")


def test_ssrf_ip_filtering():
    # Loopback blocked by default
    loopback_ip = ipaddress.ip_address("127.0.0.1")
    allowed, reason = is_ip_allowed(loopback_ip)
    assert not allowed
    assert "Loopback" in (reason or "")

    # Loopback allowed with flag
    allowed_lb, _ = is_ip_allowed(loopback_ip, allow_loopback=True)
    assert allowed_lb

    # Private RFC 1918 blocked by default
    priv_ip = ipaddress.ip_address("192.168.1.100")
    allowed_priv, _ = is_ip_allowed(priv_ip)
    assert not allowed_priv

    # Private allowed when permitted by scope
    allowed_priv_grant, _ = is_ip_allowed(priv_ip, allow_private=True)
    assert allowed_priv_grant

    # Cloud metadata (169.254.169.254) strictly blocked even if allow_private=True
    meta_ip = ipaddress.ip_address("169.254.169.254")
    allowed_meta, _ = is_ip_allowed(meta_ip, allow_private=True)
    assert not allowed_meta

    # Public IP allowed
    public_ip = ipaddress.ip_address("93.184.216.34")
    allowed_pub, _ = is_ip_allowed(public_ip)
    assert allowed_pub


def test_scope_rule_matching():
    rules = [
        {"host": "example.com", "ports": [80, 443], "path_prefixes": ["/api/"]},
        {"host": "*.internal.corp", "ports": [8080], "path_prefixes": ["/"]},
    ]

    # Matching rule 1
    ok, _ = validate_target_against_scope("http://example.com/api/v1/health", rules)
    assert ok

    # Reject different path
    ok_path, _ = validate_target_against_scope("http://example.com/admin", rules)
    assert not ok_path

    # Matching wildcard rule 2
    ok_sub, _ = validate_target_against_scope("http://service.internal.corp:8080/dashboard", rules)
    assert ok_sub

    # Reject wildcard wrong port
    ok_sub_port, _ = validate_target_against_scope("http://service.internal.corp:80/dashboard", rules)
    assert not ok_sub_port
