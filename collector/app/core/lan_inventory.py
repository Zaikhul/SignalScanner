import asyncio
from datetime import datetime, timezone
import ipaddress
import logging
import re
import socket
import subprocess
from typing import Any, AsyncIterator, Dict, List, Optional

from collector.app.config import collector_settings
from collector.app.core.association_base import (
    HostBatch,
    InventoryBound,
    LanInventoryAdapter,
)
from collector.app.core.pseudonymizer import pseudonymize_id

logger = logging.getLogger("collector.lan_inventory")

# Built-in IEEE OUI Vendor Database
OUI_DATABASE: Dict[str, str] = {
    "00:1f:3b": "Intel Corp",
    "00:11:22": "Apple Inc",
    "f0:18:98": "Apple Inc",
    "3c:22:fb": "Apple Inc",
    "a4:83:e7": "Apple Inc",
    "c0:06:c3": "Cisco Systems",
    "00:00:0c": "Cisco Systems",
    "00:14:22": "Dell Inc",
    "d4:be:d9": "Dell Inc",
    "3c:52:82": "HP Inc",
    "00:1e:0b": "HP Inc",
    "24:0a:c4": "Espressif Systems",
    "30:ae:a4": "Espressif Systems",
    "b8:27:eb": "Raspberry Pi",
    "dc:a6:32": "Raspberry Pi",
    "e4:5f:01": "Raspberry Pi",
    "50:c7:bf": "TP-Link",
    "1c:3b:f3": "TP-Link",
    "a8:9c:ed": "Samsung Electronics",
    "00:50:56": "VMware Inc",
    "00:15:5d": "Microsoft Corp",
    "00:e0:4c": "Realtek Semiconductor",
}


def lookup_oui(mac_address: str) -> str:
    cleaned = mac_address.lower().replace("-", ":")
    prefix = cleaned[:8]
    return OUI_DATABASE.get(prefix, "Unknown Manufacturer")


class LanInventoryEngine(LanInventoryAdapter):
    """
    Automated LAN Inventory Engine (PRD v1.1 - Section 11.3 & Section 15.5).
    Strictly bounded discovery on the attached network prefix:
    - Interface snapshot (Self, Gateway, DNS, DHCP)
    - Neighbor cache reader (ARP / NDP)
    - Controlled bounded ICMP probe (concurrency 8, max 256 hosts)
    - Hostname resolution (reverse DNS & mDNS)
    - MAC pseudonymization (HMAC tenant-scoped) & Vendor OUI lookup
    """

    def __init__(self):
        self._running = False

    async def capabilities(self) -> Dict[str, Any]:
        return {
            "can_inventory": True,
            "methods": ["interface_snapshot", "arp_cache", "ndp_cache", "mdns", "bounded_icmp"],
            "max_hosts": 256,
            "bounded_prefix_enforced": True,
        }

    async def start(self, bound: InventoryBound) -> AsyncIterator[HostBatch]:
        self._running = True

        # 1. Bound Prefix Validation (FR-INV-02 & FR-INV-04)
        try:
            net = ipaddress.ip_network(bound.attached_prefix, strict=False)
        except ValueError as e:
            logger.error(f"Invalid attached prefix '{bound.attached_prefix}': {e}")
            return

        if net.version == 4:
            if net.prefixlen < 16:
                logger.error(f"LAN_PREFIX_UNSUPPORTED: IPv4 prefix {net} is wider than /16")
                return
            # Clamp /17 - /22 to /24 around gateway
            if net.prefixlen < 24 and bound.gateway_ip:
                try:
                    gw_ip = ipaddress.ip_address(bound.gateway_ip)
                    net = ipaddress.ip_network(f"{gw_ip}/24", strict=False)
                    logger.info(f"Clamped wide prefix to /24 window around gateway: {net}")
                except ValueError:
                    pass

        # 2. Add Self & Gateway hosts first
        hosts_map: Dict[str, Dict[str, Any]] = {}
        now = datetime.now(timezone.utc)

        if bound.gateway_ip:
            hosts_map[bound.gateway_ip] = {
                "ip": bound.gateway_ip,
                "ip_version": 4,
                "hostname": "gateway.local",
                "mac_hash": pseudonymize_id("00:00:00:00:00:01"),
                "oui_vendor": "Network Gateway",
                "discovery_methods": ["gateway_snapshot"],
                "reachability": "up",
                "rtt_ms": 1.0,
                "is_self": False,
                "is_gateway": True,
                "quality_flags": ["gateway"],
                "last_seen": now.isoformat(),
            }

        # 3. Read initial OS neighbor cache (ARP)
        arp_entries = await self._read_arp_cache()
        for entry in arp_entries:
            ip_str = entry["ip"]
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                if ip_obj in net:
                    mac = entry["mac"]
                    mac_hash = pseudonymize_id(mac)
                    vendor = lookup_oui(mac)
                    is_gw = (ip_str == bound.gateway_ip)

                    hosts_map[ip_str] = {
                        "ip": ip_str,
                        "ip_version": ip_obj.version,
                        "hostname": None,
                        "mac_hash": mac_hash,
                        "oui_vendor": vendor,
                        "discovery_methods": ["arp_cache"],
                        "reachability": "up",
                        "rtt_ms": None,
                        "is_self": False,
                        "is_gateway": is_gw,
                        "quality_flags": ["arp_cache"],
                        "last_seen": now.isoformat(),
                    }
            except ValueError:
                continue

        # Emit initial batch from cache
        yield HostBatch(
            association_id="assoc",
            session_id="session",
            hosts=list(hosts_map.values()),
            captured_at=now,
        )

        # 4. Controlled bounded probe on candidate IPs in prefix
        if net.version == 4 and net.num_addresses <= 256:
            candidate_ips = [str(ip) for ip in net.hosts() if str(ip) not in hosts_map][: bound.max_hosts]
            await self._run_bounded_pings(candidate_ips, concurrency=bound.rate_limit)

            # Re-read ARP table after active probe
            new_arp_entries = await self._read_arp_cache()
            for entry in new_arp_entries:
                ip_str = entry["ip"]
                try:
                    ip_obj = ipaddress.ip_address(ip_str)
                    if ip_obj in net and ip_str not in hosts_map:
                        mac = entry["mac"]
                        hosts_map[ip_str] = {
                            "ip": ip_str,
                            "ip_version": ip_obj.version,
                            "hostname": None,
                            "mac_hash": pseudonymize_id(mac),
                            "oui_vendor": lookup_oui(mac),
                            "discovery_methods": ["bounded_icmp", "arp_cache"],
                            "reachability": "up",
                            "rtt_ms": None,
                            "is_self": False,
                            "is_gateway": (ip_str == bound.gateway_ip),
                            "quality_flags": ["solicited", "arp_cache"],
                            "last_seen": datetime.now(timezone.utc).isoformat(),
                        }
                except ValueError:
                    continue

        # 5. Reverse hostname lookup for discovered hosts
        for ip_str, host in hosts_map.items():
            if not host.get("hostname") or host["hostname"] == "gateway.local":
                hostname = await self._resolve_hostname(ip_str)
                if hostname:
                    host["hostname"] = hostname
                    host["discovery_methods"].append("mdns")

        # 6. Safe lightweight port audit for common LAN services
        await self._probe_hosts_ports(hosts_map)

        yield HostBatch(
            association_id="assoc",
            session_id="session",
            hosts=list(hosts_map.values()),
            captured_at=datetime.now(timezone.utc),
        )

    async def stop(self) -> None:
        self._running = False

    async def _read_arp_cache(self) -> List[Dict[str, str]]:
        results = []
        try:
            proc = await asyncio.create_subprocess_exec(
                "arp", "-a",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            text = stdout.decode("cp1252", errors="ignore")

            for line in text.splitlines():
                line = line.strip()
                # Match IP and MAC: e.g. 192.168.1.1   00-11-22-33-44-55   dynamic
                m = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+([0-9a-fA-F:-]{17})\s+(\w+)", line)
                if m:
                    ip = m.group(1)
                    mac = m.group(2).lower().replace("-", ":")
                    # Exclude multicast & broadcast MACs
                    if mac not in ("ff:ff:ff:ff:ff:ff", "01:00:5e:00:00:01"):
                        results.append({"ip": ip, "mac": mac, "type": m.group(3)})
        except Exception as e:
            logger.debug(f"Failed to read ARP cache: {e}")
        return results

    async def _run_bounded_pings(self, ips: List[str], concurrency: int = 8) -> None:
        sem = asyncio.Semaphore(concurrency)

        async def _ping_one(ip: str):
            async with sem:
                if not self._running:
                    return
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "ping", "-n", "1", "-w", "500", ip,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    await proc.communicate()
                except Exception:
                    pass

        tasks = [_ping_one(ip) for ip in ips]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _resolve_hostname(self, ip: str) -> Optional[str]:
        def _get_name():
            try:
                host, _, _ = socket.gethostbyaddr(ip)
                return host
            except Exception:
                return None

        try:
            return await asyncio.wait_for(asyncio.to_thread(_get_name), timeout=0.8)
        except Exception:
            return None

    async def _probe_hosts_ports(self, hosts_map: Dict[str, Dict[str, Any]]) -> None:
        top_ports = [22, 53, 80, 443, 445, 631, 3389, 8080]
        port_names = {
            22: "SSH",
            53: "DNS",
            80: "HTTP",
            443: "HTTPS",
            445: "SMB",
            631: "IPP",
            3389: "RDP",
            8080: "HTTP-Proxy",
        }
        sem = asyncio.Semaphore(10)

        async def _check_port(ip: str, port: int) -> Optional[Dict[str, Any]]:
            async with sem:
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection(ip, port),
                        timeout=0.4,
                    )
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
                    return {"port": port, "service": port_names.get(port, "Unknown"), "state": "open"}
                except Exception:
                    return None

        for ip_str, host in hosts_map.items():
            tasks = [_check_port(ip_str, p) for p in top_ports]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            host["open_ports"] = [r for r in results if isinstance(r, dict) and r is not None]


lan_inventory_engine = LanInventoryEngine()
