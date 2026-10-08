from __future__ import annotations

import asyncio
import ipaddress
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("backend.lan_port_scanner")

# Curated standard LAN service names for common ports
PORT_SERVICE_MAP: Dict[int, str] = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    135: "RPC",
    139: "NetBIOS",
    143: "IMAP",
    443: "HTTPS",
    445: "SMB",
    554: "RTSP",
    631: "IPP/Print",
    1883: "MQTT",
    3306: "MySQL",
    3389: "RDP",
    5000: "UPnP",
    5353: "mDNS",
    5432: "PostgreSQL",
    6379: "Redis",
    8000: "HTTP-Alt",
    8001: "Collector-Agent",
    8080: "HTTP-Proxy",
    8443: "HTTPS-Alt",
    8883: "MQTT-TLS",
    9100: "JetDirect",
}

DEFAULT_LAN_PORTS: List[int] = [
    21, 22, 23, 53, 80, 443, 445, 554, 631, 1883,
    3306, 3389, 5000, 5353, 8000, 8080, 8443, 9100,
]

# Disallowed targets for SSRF and safety preservation
METADATA_IP = "169.254.169.254"

RFC1918_NETWORKS = [
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
]


def validate_lan_target(
    ip_str: str,
    attached_prefix: Optional[str] = None,
    allow_loopback: bool = False,
) -> ipaddress.IPv4Address:
    """
    Validates that a target IP is strictly a private RFC 1918 LAN host within the permitted prefix.
    Rejects public internet, cloud metadata, link-local, loopback, multicast, and out-of-scope targets.
    Fails safely if attached_prefix is malformed or missing.
    """
    if not ip_str or not isinstance(ip_str, str):
        raise ValueError("Target IP must be a non-empty string")

    ip_trimmed = ip_str.strip()
    try:
        ip_obj = ipaddress.ip_address(ip_trimmed)
    except ValueError as e:
        raise ValueError(f"Invalid IP address format: '{ip_trimmed}'") from e

    # Confine to IPv4
    if not isinstance(ip_obj, ipaddress.IPv4Address):
        raise ValueError(f"TARGET_INVALID: Only IPv4 addresses are supported, got '{ip_trimmed}'")

    # 1. Reject public internet IPs
    if ip_obj.is_global:
        raise ValueError(
            f"TARGET_OUT_OF_SCOPE: Public internet IP '{ip_trimmed}' cannot be scanned. "
            "Port scanning is strictly confined to authorized private LAN hosts."
        )

    # 2. Reject cloud metadata and link-local addresses
    if str(ip_obj) == METADATA_IP:
        raise ValueError(f"TARGET_FORBIDDEN: Cloud metadata IP '{METADATA_IP}' is blocked.")

    if ip_obj.is_link_local:
        raise ValueError(f"TARGET_LINK_LOCAL_REJECTED: Link-local address '{ip_trimmed}' is not permitted.")

    if ip_obj.is_multicast or ip_obj.is_unspecified or ip_obj.is_reserved:
        raise ValueError(f"TARGET_INVALID: Special address '{ip_trimmed}' is not a scannable host.")

    # 3. Reject loopback unless explicitly allowed in controlled diagnostics
    if ip_obj.is_loopback:
        if not allow_loopback:
            raise ValueError(f"TARGET_LOOPBACK_REJECTED: Loopback address '{ip_trimmed}' is not permitted.")

    # 4. Enforce RFC 1918 private ranges
    if not (allow_loopback and ip_obj.is_loopback):
        is_rfc1918 = any(ip_obj in net for net in RFC1918_NETWORKS)
        if not is_rfc1918:
            raise ValueError(f"TARGET_NOT_RFC1918: IP '{ip_trimmed}' is not an RFC 1918 private LAN address.")

    # 5. If attached_prefix is provided, strictly enforce membership and prefix validity
    if attached_prefix is not None:
        p_str = attached_prefix.strip()
        if not p_str:
            raise ValueError("MISSING_ATTACHED_PREFIX: Attached subnet prefix cannot be empty.")

        try:
            net_obj = ipaddress.ip_network(p_str, strict=False)
        except ValueError as e:
            raise ValueError(f"INVALID_ATTACHED_PREFIX: Malformed attached prefix '{p_str}': {e}") from e

        if net_obj.version != 4:
            raise ValueError(f"INVALID_ATTACHED_PREFIX: Only IPv4 prefixes are supported, got '{p_str}'")

        if not (allow_loopback and net_obj.is_loopback):
            if not any(net_obj.subnet_of(rfc) for rfc in RFC1918_NETWORKS):
                raise ValueError(
                    f"ATTACHED_PREFIX_NOT_RFC1918: Prefix '{p_str}' is not within RFC 1918 private ranges."
                )

        if ip_obj not in net_obj:
            raise ValueError(
                f"TARGET_OUT_OF_SUBNET: Target '{ip_trimmed}' is outside attached prefix '{p_str}'."
            )

        # Reject subnet network address and broadcast address
        if ip_obj == net_obj.network_address or (net_obj.num_addresses > 2 and ip_obj == net_obj.broadcast_address):
            raise ValueError(
                f"TARGET_SUBNET_BOUNDARY: IP '{ip_trimmed}' is a subnet boundary (network or broadcast address)."
            )

    return ip_obj


class LanPortScanner:
    """
    Safe, bounded asynchronous TCP port scanner.
    Non-blocking, strictly rate-limited, with timeouts and zero raw-socket exploitation.
    """

    def __init__(self, default_timeout: float = 0.5, max_concurrency: int = 5):
        self.default_timeout = default_timeout
        self.max_concurrency = max_concurrency

    async def probe_port(
        self,
        ip: str,
        port: int,
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Attempts a safe TCP 3-way handshake on target IP:port within timeout.
        Immediately and cleanly closes connection once established.
        """
        t = timeout or self.default_timeout
        try:
            conn = asyncio.open_connection(ip, port)
            reader, writer = await asyncio.wait_for(conn, timeout=t)
            
            banner: Optional[str] = None
            try:
                # Brief non-blocking read for banner if immediately sent by service
                data = await asyncio.wait_for(reader.read(128), timeout=0.15)
                if data:
                    banner = data.decode("utf-8", errors="replace").strip().replace("\r", "").replace("\n", " ")
                    if len(banner) > 64:
                        banner = banner[:61] + "..."
            except Exception:
                pass

            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

            return {
                "port": port,
                "service": PORT_SERVICE_MAP.get(port, "unknown"),
                "state": "open",
                "protocol": "tcp",
                "banner": banner,
            }
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return None
        except Exception as e:
            logger.debug(f"Unexpected probe error on {ip}:{port}: {e}")
            return None

    async def scan_host_ports(
        self,
        ip: str,
        ports: Optional[List[int]] = None,
        timeout: Optional[float] = None,
        concurrency: Optional[int] = None,
        attached_prefix: Optional[str] = None,
        allow_loopback: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Executes bounded port scan on validated LAN target.
        """
        # Strict validation gate
        validate_lan_target(ip, attached_prefix=attached_prefix, allow_loopback=allow_loopback)

        ports_to_scan = sorted(list(set(ports))) if ports else DEFAULT_LAN_PORTS
        # Clamp ports list to a maximum of 50 ports per request
        if len(ports_to_scan) > 50:
            ports_to_scan = ports_to_scan[:50]

        t = timeout or self.default_timeout
        # Clamp timeout between 0.1s and 2.0s
        t = max(0.1, min(2.0, t))

        sem = asyncio.Semaphore(concurrency or self.max_concurrency)

        async def _bounded_probe(p: int) -> Optional[Dict[str, Any]]:
            async with sem:
                return await self.probe_port(ip, p, timeout=t)

        tasks = [_bounded_probe(p) for p in ports_to_scan]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        open_ports: List[Dict[str, Any]] = []
        for r in results:
            if isinstance(r, dict) and r.get("state") == "open":
                open_ports.append(r)

        open_ports.sort(key=lambda x: x["port"])
        return open_ports


lan_port_scanner = LanPortScanner()
