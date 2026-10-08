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


def validate_lan_target(ip_str: str, attached_prefix: Optional[str] = None) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """
    Validates that a target IP is strictly a private LAN host within the permitted prefix.
    Rejects public internet, cloud metadata, multicast, and out-of-scope targets.
    """
    if not ip_str or not isinstance(ip_str, str):
        raise ValueError("Target IP must be a non-empty string")

    ip_trimmed = ip_str.strip()
    try:
        ip_obj = ipaddress.ip_address(ip_trimmed)
    except ValueError as e:
        raise ValueError(f"Invalid IP address format: '{ip_trimmed}'") from e

    # 1. Reject public internet IPs
    if ip_obj.is_global:
        raise ValueError(
            f"TARGET_OUT_OF_SCOPE: Public internet IP '{ip_trimmed}' cannot be scanned. "
            "Port scanning is strictly confined to authorized private LAN hosts."
        )

    # 2. Reject cloud metadata and link-local multicast
    if str(ip_obj) == METADATA_IP:
        raise ValueError(f"TARGET_FORBIDDEN: Cloud metadata IP '{METADATA_IP}' is blocked.")

    if ip_obj.is_multicast or ip_obj.is_unspecified or ip_obj.is_reserved:
        raise ValueError(f"TARGET_INVALID: Special address '{ip_trimmed}' is not a scannable host.")

    # 3. Must be private or loopback (for local testing/diagnostics)
    if not (ip_obj.is_private or ip_obj.is_loopback):
        raise ValueError(f"TARGET_NOT_PRIVATE: IP '{ip_trimmed}' is not an RFC 1918 private address.")

    # 4. If attached_prefix is provided, target must be inside attached_prefix
    if attached_prefix:
        net_obj = None
        try:
            net_obj = ipaddress.ip_network(attached_prefix, strict=False)
        except ValueError as e:
            logger.warning(f"Malformed attached prefix '{attached_prefix}': {e}")

        if net_obj is not None:
            if ip_obj not in net_obj and not ip_obj.is_loopback:
                raise ValueError(
                    f"TARGET_OUT_OF_SUBNET: Target '{ip_trimmed}' is outside attached prefix '{attached_prefix}'."
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
    ) -> List[Dict[str, Any]]:
        """
        Executes bounded port scan on validated LAN target.
        """
        # Strict validation gate
        validate_lan_target(ip, attached_prefix=attached_prefix)

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
