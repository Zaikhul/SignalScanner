import asyncio
from datetime import datetime, timezone
import logging
import os
import re
import subprocess
import tempfile
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from collector.app.core.association_base import (
    AssociateRequest,
    AssociationAdapter,
    AssociationEvent,
    LinkState,
)

logger = logging.getLogger("collector.wifi_associate_windows")


class WindowsWiFiAssociationAdapter:
    """
    Windows WiFi Association Adapter (PRD v1.1 - Section 15.2).
    Uses netsh and Native WiFi to connect to Open, WPA2-Personal, or WPA3-SAE networks.
    Ensures zeroized credential buffers and cleanup of temporary OS profiles.
    """

    def __init__(self):
        self._current_profile: Optional[str] = None
        self._current_ssid: Optional[str] = None
        self._is_connected = False
        self._forget_profile_on_exit = True

    async def capabilities(self) -> Dict[str, Any]:
        return {
            "can_associate": True,
            "supported_security": ["open", "wpa2_personal", "wpa3_sae"],
            "supports_temporary_profiles": True,
            "scan_while_associated": False,
        }

    async def associate(
        self, request: AssociateRequest, password: Optional[str] = None
    ) -> AsyncIterator[AssociationEvent]:
        ssid = request.ssid
        if not ssid:
            yield AssociationEvent(
                state="failed",
                error_code="WIFI_HIDDEN_SSID_REQUIRED",
                timestamp=datetime.now(timezone.utc),
            )
            return

        self._current_ssid = ssid
        self._forget_profile_on_exit = not request.save_profile
        profile_name = f"PA_Temp_{uuid.uuid4().hex[:8]}"
        self._current_profile = profile_name

        yield AssociationEvent(
            state="requesting_permission",
            timestamp=datetime.now(timezone.utc),
        )

        # 1. Build and install temporary profile XML
        sec = request.security_type.lower()
        xml_content = self._build_profile_xml(profile_name, ssid, sec, password)

        # Zeroize password variable immediately after XML generation
        password = None

        temp_xml_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
                f.write(xml_content)
                temp_xml_path = f.name

            # Add profile via netsh
            add_proc = await asyncio.create_subprocess_exec(
                "netsh", "wlan", "add", "profile", f"filename={temp_xml_path}", "user=current",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await add_proc.communicate()
            if add_proc.returncode != 0:
                logger.error(f"Failed to add netsh profile: {stderr.decode('cp1252', errors='ignore')}")
                yield AssociationEvent(
                    state="failed",
                    error_code="WIFI_PROFILE_DENIED",
                    timestamp=datetime.now(timezone.utc),
                )
                return
        finally:
            # Overwrite and remove temp XML file from disk immediately
            if temp_xml_path and os.path.exists(temp_xml_path):
                try:
                    with open(temp_xml_path, "wb") as f:
                        f.write(b"\x00" * 1024)
                    os.remove(temp_xml_path)
                except Exception:
                    pass

        # 2. Trigger connection
        yield AssociationEvent(
            state="associating",
            timestamp=datetime.now(timezone.utc),
        )

        conn_proc = await asyncio.create_subprocess_exec(
            "netsh", "wlan", "connect", f"name={profile_name}", f"ssid={ssid}",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        await conn_proc.communicate()

        yield AssociationEvent(
            state="authenticating",
            timestamp=datetime.now(timezone.utc),
        )

        # 3. Poll connection status up to timeout_seconds
        timeout = request.timeout_seconds
        start_time = asyncio.get_event_loop().time()
        connected = False

        while asyncio.get_event_loop().time() - start_time < timeout:
            await asyncio.sleep(1.5)
            link_state = await self.current_link()

            if link_state.is_connected and link_state.ssid == ssid:
                connected = True
                break

        if not connected:
            yield AssociationEvent(
                state="failed",
                error_code="WIFI_ASSOC_TIMEOUT",
                timestamp=datetime.now(timezone.utc),
            )
            await self.disconnect(forget_profile=self._forget_profile_on_exit)
            return

        yield AssociationEvent(
            state="obtaining_address",
            timestamp=datetime.now(timezone.utc),
        )

        # 4. Wait for IP address acquisition (DHCP / SLAAC)
        addr_info = await self._wait_for_ip_address(timeout=15)
        if not addr_info.get("ipv4") and not addr_info.get("ipv6"):
            yield AssociationEvent(
                state="failed",
                error_code="WIFI_DHCP_TIMEOUT",
                timestamp=datetime.now(timezone.utc),
            )
            await self.disconnect(forget_profile=self._forget_profile_on_exit)
            return

        self._is_connected = True
        yield AssociationEvent(
            state="connected",
            ipv4=addr_info.get("ipv4"),
            ipv6=addr_info.get("ipv6"),
            prefix=addr_info.get("prefix"),
            gateway=addr_info.get("gateway"),
            dns=addr_info.get("dns", []),
            dhcp_server=addr_info.get("dhcp_server"),
            captive_state=addr_info.get("captive_state", "unknown"),
            timestamp=datetime.now(timezone.utc),
        )

    async def disconnect(self, forget_profile: bool = True) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "netsh", "wlan", "disconnect",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            await proc.communicate()
        except Exception as e:
            logger.debug(f"Disconnect error: {e}")

        if forget_profile and self._current_profile:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "netsh", "wlan", "delete", "profile", f"name={self._current_profile}",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                await proc.communicate()
                logger.info(f"Deleted temporary profile: {self._current_profile}")
            except Exception as e:
                logger.debug(f"Delete profile error: {e}")

        self._current_profile = None
        self._current_ssid = None
        self._is_connected = False

    async def current_link(self) -> LinkState:
        try:
            proc = await asyncio.create_subprocess_exec(
                "netsh", "wlan", "show", "interfaces",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            text = stdout.decode("cp1252", errors="ignore")

            is_connected = False
            ssid = None
            bssid = None
            speed = None
            quality = None

            for line in text.splitlines():
                line = line.strip()
                # Match State / Status
                if re.match(r"^(?:State|Status|Keadaan)\s*:\s*(.*)$", line, re.IGNORECASE):
                    val = line.split(":", 1)[1].strip().lower()
                    if "connected" in val or "terhubung" in val:
                        is_connected = True
                # Match SSID
                elif re.match(r"^SSID\s*:\s*(.*)$", line, re.IGNORECASE):
                    ssid = line.split(":", 1)[1].strip()
                # Match BSSID
                elif re.match(r"^BSSID\s*:\s*([0-9a-fA-F:-]{17})$", line, re.IGNORECASE):
                    bssid = line.split(":", 1)[1].strip().lower()
                # Match Signal %
                elif re.match(r"^(?:Signal|Sinyal)\s*:\s*(\d+)%", line, re.IGNORECASE):
                    m = re.search(r"(\d+)%", line)
                    if m:
                        quality = int(m.group(1))
                # Match Receive rate / Transmit rate
                elif re.match(r"^(?:Receive rate|Transmit rate)\s*\(Mbps\)\s*:\s*(\d+)", line, re.IGNORECASE):
                    m = re.search(r":\s*(\d+)", line)
                    if m:
                        speed = int(m.group(1))

            return LinkState(
                is_connected=is_connected,
                ssid=ssid,
                bssid=bssid,
                link_speed_mbps=speed,
                signal_quality_pct=quality,
            )
        except Exception:
            return LinkState(is_connected=False)

    async def _get_active_interface_meta(self) -> Dict[str, Optional[str]]:
        """Queries netsh wlan show interfaces to retrieve the active Wi-Fi adapter name and MAC."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "netsh", "wlan", "show", "interfaces",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            text = stdout.decode("cp1252", errors="ignore")
            name = None
            mac = None
            desc = None
            for line in text.splitlines():
                m_name = re.match(r"^\s*Name\s*:\s*(.*)$", line, re.IGNORECASE)
                if m_name:
                    name = m_name.group(1).strip()
                m_desc = re.match(r"^\s*Description\s*:\s*(.*)$", line, re.IGNORECASE)
                if m_desc:
                    desc = m_desc.group(1).strip()
                m_mac = re.match(r"^\s*Physical address\s*:\s*(.*)$", line, re.IGNORECASE)
                if m_mac:
                    mac = m_mac.group(1).strip()
            return {"name": name, "mac": mac, "desc": desc}
        except Exception as e:
            logger.debug(f"Failed to query active wlan interface meta: {e}")
            return {"name": None, "mac": None, "desc": None}

    async def _wait_for_ip_address(
        self, timeout: int = 15, target_name: Optional[str] = None, target_mac: Optional[str] = None
    ) -> Dict[str, Any]:
        """Polls ipconfig /all to detect acquired IPv4, gateway, and subnet mask for the active Wi-Fi adapter."""
        if not target_name and not target_mac:
            meta = await self._get_active_interface_meta()
            target_name = meta.get("name")
            target_mac = meta.get("mac")

        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            await asyncio.sleep(1.0)
            addr = await self._parse_ipconfig(target_name=target_name, target_mac=target_mac)
            if addr.get("ipv4") and not addr.get("ipv4").startswith("169.254."):
                return addr
        return {}

    async def _parse_ipconfig(
        self, target_name: Optional[str] = None, target_mac: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ipconfig", "/all",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            text = stdout.decode("cp1252", errors="ignore")
            return self._parse_ipconfig_text(text, target_name=target_name, target_mac=target_mac)
        except Exception as e:
            logger.debug(f"Failed to parse ipconfig: {e}")
            return {}

    @staticmethod
    def _parse_ipconfig_text(
        text: str, target_name: Optional[str] = None, target_mac: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parses ipconfig /all output by sections.
        Prioritizes the active Wi-Fi adapter matching target_mac / target_name,
        and excludes virtual adapters (VMware, VirtualBox, Wintun, Hyper-V, Wi-Fi Direct virtual adapters).
        """
        import ipaddress

        sections = re.split(r'\n(?=[^\s\r\n].*adapter\s+.*:)', text, flags=re.IGNORECASE)
        target_mac_clean = re.sub(r'[:-]', '', target_mac).lower() if target_mac else None
        target_name_clean = target_name.strip().lower() if target_name else None

        VIRTUAL_DENYLIST = [
            "vmware",
            "virtualbox",
            "vethernet",
            "wintun",
            "tap-windows",
            "wireguard",
            "tailscale",
            "hyper-v",
            "direct virtual adapter",
            "local area connection*",
            "bluetooth",
            "loopback",
        ]

        candidates = []
        for s in sections:
            lines = s.strip().splitlines()
            if not lines:
                continue
            header = lines[0].lower()
            if "adapter" not in header:
                continue

            s_lower = s.lower()
            # Exclude known virtual adapters
            if any(v in s_lower or v in header for v in VIRTUAL_DENYLIST):
                continue

            is_wireless = any(w in header for w in ["wireless", "wi-fi", "wlan"])

            # Extract MAC from section
            mac_m = re.search(r"physical address[.\s]+:\s*([0-9a-fA-F:-]+)", s_lower)
            s_mac = re.sub(r'[:-]', '', mac_m.group(1)).lower() if mac_m else None

            score = 0
            if target_mac_clean and s_mac == target_mac_clean:
                score += 100
            elif target_name_clean and target_name_clean in header:
                score += 80
            elif is_wireless:
                score += 50
            else:
                score += 10

            # Favor adapters with active IPv4 non-link-local
            ipv4_m = re.search(r"ipv4 address[.\s]+:\s*(\d{1,3}(?:\.\d{1,3}){3})", s_lower)
            if ipv4_m and not ipv4_m.group(1).startswith("169.254."):
                score += 20

            # Favor adapters with a default gateway
            if "default gateway" in s_lower:
                score += 10

            candidates.append((score, s))

        if not candidates:
            return {}

        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_section = candidates[0]
        if best_score < 30:
            return {}

        lines = best_section.splitlines()
        ipv4 = None
        mask = None
        gateway = None
        dhcp_server = None
        dns_list = []

        in_gateway = False
        in_dns = False

        for line in lines:
            # Match IPv4 Address
            if "IPv4" in line and ":" in line:
                m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
                if m:
                    ipv4 = m.group(1)
            # Match Subnet Mask
            elif "Subnet Mask" in line and ":" in line:
                m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
                if m:
                    mask = m.group(1)
            # Match DHCP Server
            elif "DHCP Server" in line and ":" in line:
                m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
                if m:
                    dhcp_server = m.group(1)

            # Match Default Gateway (handles multi-line where IPv6 is first, IPv4 is indented below)
            if "Default Gateway" in line and ":" in line:
                in_gateway = True
                m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
                if m:
                    gateway = m.group(1)
                    in_gateway = False
            elif in_gateway:
                if re.match(r"^\s+(\d{1,3}(?:\.\d{1,3}){3})", line):
                    m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
                    if m:
                        gateway = m.group(1)
                    in_gateway = False
                elif ":" in line and not line.strip().startswith(("fe80:", "2001:", "fd")):
                    in_gateway = False

            # Match DNS Servers (handles multi-line indented DNS entries)
            if "DNS Servers" in line and ":" in line:
                in_dns = True
                m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
                if m:
                    dns_list.append(m.group(1))
            elif in_dns:
                m = re.search(r"^\s+(\d{1,3}(?:\.\d{1,3}){3})", line)
                if m:
                    dns_list.append(m.group(1))
                elif ":" in line and not line.strip().startswith(("fe80:", "2001:", "fd")):
                    in_dns = False

        prefix = None
        if ipv4 and mask:
            try:
                net = ipaddress.IPv4Network(f"{ipv4}/{mask}", strict=False)
                prefix = str(net)
            except Exception:
                prefix = f"{ipv4}/24"

        return {
            "ipv4": ipv4,
            "prefix": prefix,
            "gateway": gateway,
            "dns": dns_list,
            "dhcp_server": dhcp_server,
            "captive_state": "internet" if gateway else "unknown",
        }

    @staticmethod
    def _build_profile_xml(profile_name: str, ssid: str, sec: str, password: Optional[str]) -> str:
        if sec in ("open", "none"):
            return f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{profile_name}</name>
    <SSIDConfig>
        <SSID>
            <name>{ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>open</authentication>
                <encryption>none</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
        </security>
    </MSM>
</WLANProfile>"""

        elif "wpa3" in sec or "sae" in sec:
            pwd = password or ""
            return f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{profile_name}</name>
    <SSIDConfig>
        <SSID>
            <name>{ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA3SAE</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{pwd}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>"""

        else:
            # Default to WPA2-Personal (WPA2PSK)
            pwd = password or ""
            return f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{profile_name}</name>
    <SSIDConfig>
        <SSID>
            <name>{ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{pwd}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>"""
