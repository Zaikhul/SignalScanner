from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

from app.config import settings

# Blocked network ranges for SSRF prevention
BLOCKED_IPV4_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),          # Current network
    ipaddress.ip_network("10.0.0.0/8"),         # Private RFC1918
    ipaddress.ip_network("100.64.0.0/10"),      # Shared Address Space
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local / Cloud Metadata
    ipaddress.ip_network("172.16.0.0/12"),      # Private RFC1918
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),     # Private RFC1918
    ipaddress.ip_network("198.18.0.0/15"),      # Network benchmark tests
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast
]

BLOCKED_IPV6_NETWORKS = [
    ipaddress.ip_network("::1/128"),            # Loopback
    ipaddress.ip_network("::/128"),             # Unspecified
    ipaddress.ip_network("::ffff:0:0/96"),      # IPv4-mapped
    ipaddress.ip_network("64:ff9b::/96"),       # IPv4/IPv6 translation
    ipaddress.ip_network("100::/64"),           # Discard prefix
    ipaddress.ip_network("2001:db8::/32"),      # Documentation
    ipaddress.ip_network("fc00::/7"),           # Unique local
    ipaddress.ip_network("fe80::/10"),          # Link-local
    ipaddress.ip_network("ff00::/8"),           # Multicast
]


class NormalizedTarget:
    def __init__(
        self,
        raw_url: str,
        canonical_url: str,
        scheme: str,
        hostname: str,
        port: int,
        path: str,
        query: str,
        display_url: str,
    ):
        self.raw_url = raw_url
        self.canonical_url = canonical_url
        self.scheme = scheme
        self.hostname = hostname
        self.port = port
        self.path = path
        self.query = query
        self.display_url = display_url

    def __repr__(self) -> str:
        return f"<NormalizedTarget {self.canonical_url}>"


def parse_and_validate_target(raw_target: str) -> NormalizedTarget:
    """Parses and normalizes target URL, rejecting malformed formats and embedded credentials."""
    trimmed = raw_target.strip()
    if not trimmed:
        raise ValueError("Target URL cannot be empty")

    # If scheme is completely missing, default to http
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", trimmed):
        parsed_attempt = urlsplit("http://" + trimmed)
        if parsed_attempt.netloc:
            trimmed = "http://" + trimmed
        else:
            raise ValueError("Invalid target format")

    parts = urlsplit(trimmed)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Unsupported scheme '{scheme}'. Only HTTP and HTTPS are allowed.")

    if not parts.netloc:
        raise ValueError("Target URL must have a valid host")

    # Reject userinfo (e.g. http://user:pass@host)
    if "@" in parts.netloc:
        raise ValueError("Target URL must not contain embedded userinfo or credentials")

    # Extract hostname and port
    try:
        hostname = parts.hostname
        if not hostname:
            raise ValueError("Target hostname missing")
        # Encode via IDNA to normalize international domain names
        hostname = hostname.encode("idna").decode("ascii").lower()
    except Exception as e:
        raise ValueError(f"Invalid domain name encoding: {e}")

    # Determine port
    port = parts.port
    if port is None:
        port = 443 if scheme == "https" else 80
    elif port < 1 or port > 65535:
        raise ValueError(f"Port {port} is out of valid range (1-65535)")

    # Normalize path
    path = parts.path or "/"
    if not path.startswith("/"):
        path = "/" + path

    query = parts.query or ""

    # Build canonical URL (re-assemble without fragment, standard ports omitted)
    netloc_str = hostname
    if (scheme == "http" and port != 80) or (scheme == "https" and port != 443):
        netloc_str = f"{hostname}:{port}"

    canonical_url = urlunsplit((scheme, netloc_str, path, query, ""))
    display_url = sanitize_target_for_display(canonical_url)

    return NormalizedTarget(
        raw_url=raw_target,
        canonical_url=canonical_url,
        scheme=scheme,
        hostname=hostname,
        port=port,
        path=path,
        query=query,
        display_url=display_url,
    )


def sanitize_target_for_display(url: str) -> str:
    """Redacts query parameter values in URL to prevent leaking tokens/secrets in logs/UI."""
    try:
        parts = urlsplit(url)
        if not parts.query:
            return url
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        redacted_pairs = [(k, "<redacted>") for k, _ in pairs]
        redacted_query = urlencode(redacted_pairs)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, redacted_query, ""))
    except Exception:
        return url


def is_ip_allowed(
    ip_obj: Union[ipaddress.IPv4Address, ipaddress.IPv6Address],
    allow_private: bool = False,
    allow_loopback: bool = False,
) -> Tuple[bool, Optional[str]]:
    """Checks whether an IP address is permitted according to safety rules."""
    # Check loopback
    if ip_obj.is_loopback:
        if allow_loopback:
            return True, None
        return False, "Loopback addresses are restricted"

    # Check IPv4 blocked
    if isinstance(ip_obj, ipaddress.IPv4Address):
        for net in BLOCKED_IPV4_NETWORKS:
            if ip_obj in net:
                if net in (
                    ipaddress.ip_network("10.0.0.0/8"),
                    ipaddress.ip_network("172.16.0.0/12"),
                    ipaddress.ip_network("192.168.0.0/16"),
                ) and allow_private:
                    return True, None
                return False, f"Destination IP {ip_obj} is in restricted range {net}"

    # Check IPv6 blocked
    elif isinstance(ip_obj, ipaddress.IPv6Address):
        for net in BLOCKED_IPV6_NETWORKS:
            if ip_obj in net:
                if net == ipaddress.ip_network("fc00::/7") and allow_private:
                    return True, None
                return False, f"Destination IPv6 {ip_obj} is in restricted range {net}"

    # Disallow multicast, reserved, link-local
    if ip_obj.is_multicast or ip_obj.is_reserved or ip_obj.is_link_local:
        return False, f"Destination IP {ip_obj} is special/reserved"

    return True, None


async def resolve_and_validate_hostname(
    hostname: str,
    port: int = 80,
    allow_private: bool = False,
    allow_loopback: bool = False,
) -> List[str]:
    """Resolves hostname to IP addresses and enforces SSRF restrictions on all resolved IPs."""
    # First check if hostname is directly an IP literal
    try:
        direct_ip = ipaddress.ip_address(hostname)
        allowed, reason = is_ip_allowed(direct_ip, allow_private=allow_private, allow_loopback=allow_loopback)
        if not allowed:
            raise ValueError(f"Target IP {hostname} is blocked: {reason}")
        return [str(direct_ip)]
    except ValueError as ve:
        if "is blocked:" in str(ve):
            raise
        # Not an IP literal, proceed to DNS resolution

    loop = asyncio.get_running_loop()
    try:
        # socket.getaddrinfo is run in executor to keep async loop responsive
        addrinfo = await loop.run_in_executor(
            None,
            socket.getaddrinfo,
            hostname,
            port,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed for hostname '{hostname}': {e}")

    approved_ips: List[str] = []
    seen = set()

    for item in addrinfo:
        sockaddr = item[4]
        ip_str = sockaddr[0]
        if ip_str in seen:
            continue
        seen.add(ip_str)

        ip_obj = ipaddress.ip_address(ip_str)
        allowed, reason = is_ip_allowed(ip_obj, allow_private=allow_private, allow_loopback=allow_loopback)
        if not allowed:
            raise ValueError(f"Resolved address {ip_str} for host '{hostname}' is not permitted: {reason}")

        approved_ips.append(ip_str)

    if not approved_ips:
        raise ValueError(f"No usable IP addresses resolved for hostname '{hostname}'")

    return approved_ips


def validate_and_normalize_target(
    raw_target: str,
    allow_private: bool = False,
    allow_loopback: bool = False,
) -> Tuple[str, str]:
    """Validates raw URL and returns (canonical_url, display_url)."""
    norm = parse_and_validate_target(raw_target)
    return norm.canonical_url, norm.display_url


def validate_target_against_scope(
    target_url: str,
    rules: List[Dict[str, Any]],
) -> Tuple[bool, Optional[str]]:
    """Checks whether the target URL conforms to scope grant rules."""
    try:
        norm = parse_and_validate_target(target_url)
    except Exception as exc:
        return False, f"Invalid target URL: {exc}"

    if not rules:
        return False, "No rules defined in scope grant"

    for rule in rules:
        host_pat = rule.get("host", "").lower().strip()
        if host_pat.startswith("*."):
            suffix = host_pat[2:]
            if not (norm.hostname == suffix or norm.hostname.endswith("." + suffix)):
                continue
        elif host_pat and host_pat != norm.hostname:
            continue

        # Check ports
        ports = rule.get("ports")
        if ports and norm.port not in ports:
            continue

        # Check path prefixes
        prefixes = rule.get("path_prefixes", ["/"])
        if prefixes and not any(norm.path.startswith(p) for p in prefixes):
            continue

        return True, None

    return False, "Target does not match any authorized host, port, or path rule"

