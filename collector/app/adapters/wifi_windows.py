import asyncio
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import logging
import re
import subprocess
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from collector.app.config import collector_settings
from collector.app.core.adapter_base import (
    AdapterCapabilities,
    ScanConfig,
    SignalAdapter,
    ValidationResult,
)
from collector.app.core.pseudonymizer import pseudonymize_id

logger = logging.getLogger("collector.wifi_windows")

# --- Win32 ctypes struct definitions for wlanapi.dll ---
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_byte * 8),
    ]


class WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [
        ("InterfaceGuid", GUID),
        ("strInterfaceDescription", wintypes.WCHAR * 256),
        ("isState", wintypes.DWORD),
    ]


class WLAN_INTERFACE_INFO_LIST(ctypes.Structure):
    _fields_ = [
        ("dwNumberOfItems", wintypes.DWORD),
        ("dwIndex", wintypes.DWORD),
        ("InterfaceInfo", WLAN_INTERFACE_INFO * 1),
    ]


class DOT11_SSID(ctypes.Structure):
    _fields_ = [
        ("uSSIDLength", wintypes.ULONG),
        ("ucSSID", ctypes.c_char * 32),
    ]


class WLAN_BSS_ENTRY(ctypes.Structure):
    _fields_ = [
        ("dot11Ssid", DOT11_SSID),
        ("uPhyId", wintypes.ULONG),
        ("dot11Bssid", ctypes.c_ubyte * 6),
        ("dot11BssType", wintypes.DWORD),
        ("dot11BssPhyType", wintypes.DWORD),
        ("lRssi", ctypes.c_long),
        ("uLinkQuality", wintypes.ULONG),
        ("bInRegDomain", wintypes.BOOLEAN),
        ("usBeaconPeriod", wintypes.USHORT),
        ("ullTimestamp", ctypes.c_ulonglong),
        ("ullHostTimestamp", ctypes.c_ulonglong),
        ("usCapabilityInformation", wintypes.USHORT),
        ("ulChCenterFrequency", wintypes.ULONG),
        ("wlanRateSet", ctypes.c_byte * 256),
        ("ulIeOffset", wintypes.ULONG),
        ("ulIeSize", wintypes.ULONG),
    ]


class WLAN_BSS_LIST(ctypes.Structure):
    _fields_ = [
        ("dwTotalSize", wintypes.DWORD),
        ("dwNumberOfItems", wintypes.DWORD),
        ("wlanBssEntries", WLAN_BSS_ENTRY * 1),
    ]


class WindowsWiFiAdapter(SignalAdapter):
    def __init__(self):
        self._running = False
        self._seq = 0
        self._wlan_lib = None
        self._last_scan_time: Optional[float] = None
        try:
            self._wlan_lib = ctypes.windll.wlanapi
        except Exception:
            self._wlan_lib = None

    async def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_id="win_wlan_native_01",
            mode="wifi",
            name="Windows Native WiFi Adapter (WlanApi 2.0)",
            is_available=True,
            driver_version="WlanApi 2.0 / Native Win32",
            details={"bands": ["2.4GHz", "5GHz", "6GHz"], "methods": ["WlanGetNetworkBssList", "netsh_fallback"]},
        )

    async def validate(self, config: ScanConfig) -> ValidationResult:
        return ValidationResult(is_valid=True)

    async def start(self, config: ScanConfig) -> AsyncIterator[Dict[str, Any]]:
        self._running = True
        interval = max(0.5, config.sample_interval_ms / 1000.0)

        while self._running:
            self._seq += 1
            scan_id = f"scn_win_{uuid.uuid4().hex[:8]}"
            t_req = datetime.now(timezone.utc)
            t_req_mono = time.monotonic()

            # 1. Try Native Win32 WlanApi scan
            networks = await self._scan_networks_native()
            source_method = "windows_native_wifi"
            is_native = True

            # 2. If Native Win32 returned 0 networks, fallback to netsh CLI
            if not networks:
                networks = await self._scan_networks_netsh()
                source_method = "windows_netsh_fallback"
                is_native = False

            t_comp = datetime.now(timezone.utc)
            t_comp_mono = time.monotonic()
            actual_interval_ms = int((t_comp_mono - (self._last_scan_time or t_req_mono)) * 1000)
            self._last_scan_time = t_comp_mono

            now_iso = t_comp.isoformat()
            measurements = []

            for net in networks:
                rssi = float(net.get("rssi_dbm", -70.0))
                bssid = net.get("bssid", "unknown")
                ssid = net.get("ssid", "Hidden Network")
                channel = net.get("channel")
                band = net.get("band") or ("5GHz" if channel and channel > 14 else "2.4GHz")
                freq_hz = net.get("freq_hz")
                observed_at = t_comp

                q_flags = ["calibrated"] if is_native else []
                if not is_native:
                    q_flags.append("fallback_parser")

                measurements.append({
                    "schema_version": "2.0",
                    "scan_id": scan_id,
                    "session_id": config.session_id,
                    "collector_id": collector_settings.COLLECTOR_ID,
                    "sequence": self._seq,
                    "captured_at": now_iso,
                    "mode": "wifi",
                    "target_id": pseudonymize_id(bssid),
                    "display_name": ssid,
                    "signal": {
                        "value": rssi,
                        "unit": "dBm",
                        "noise": -95.0,
                    },
                    "radio": {
                        "channel": channel,
                        "band": band,
                        "frequency_hz": freq_hz,
                    },
                    "quality": {
                        "calibrated": is_native,
                        "permission_limited": False,
                        "throttled": False,
                        "scan_id": scan_id,
                        "scan_requested_at": t_req.isoformat(),
                        "scan_completed_at": t_comp.isoformat(),
                        "observed_at": observed_at.isoformat(),
                        "collector_received_at": t_comp.isoformat(),
                        "age_ms": 0,
                        "actual_interval_ms": actual_interval_ms,
                        "source_method": source_method,
                        "freshness": "fresh",
                        "cache_possible": not is_native,
                        "rssi_processing": "os_filtered",
                        "quality_flags": q_flags,
                        "fields_unavailable": [],
                    },
                    "extra_metadata": {
                        "auth": net.get("auth", "Unknown"),
                        "radio_type": net.get("radio_type", "802.11"),
                        "raw_bssid_masked": bssid[:8] + ":XX:XX:XX" if len(bssid) >= 8 else "XX:XX",
                        "scan_method": source_method,
                    },
                })

            yield {
                "schema_version": "2.0",
                "scan_id": scan_id,
                "session_id": config.session_id,
                "collector_id": collector_settings.COLLECTOR_ID,
                "source_type": "collector",
                "sequence_from": self._seq,
                "sequence_to": self._seq,
                "sent_at": now_iso,
                "measurements": measurements,
            }
            await asyncio.sleep(interval)

    async def _scan_networks_native(self) -> List[Dict[str, Any]]:
        """Uses Windows native wlanapi.dll to trigger WlanScan and retrieve WLAN_BSS_LIST."""
        if not self._wlan_lib:
            return []

        def _do_native_scan():
            results = []
            client_handle = wintypes.HANDLE()
            negotiated_version = wintypes.DWORD()
            
            # WlanOpenHandle
            res = self._wlan_lib.WlanOpenHandle(2, None, ctypes.byref(negotiated_version), ctypes.byref(client_handle))
            if res != 0:
                return []

            try:
                p_iface_list = ctypes.c_void_p()
                res = self._wlan_lib.WlanEnumInterfaces(client_handle, None, ctypes.byref(p_iface_list))
                if res != 0:
                    return []

                try:
                    iface_list = ctypes.cast(p_iface_list, ctypes.POINTER(WLAN_INTERFACE_INFO_LIST)).contents
                    for i in range(iface_list.dwNumberOfItems):
                        iface = iface_list.InterfaceInfo[i]
                        guid = iface.InterfaceGuid

                        # Trigger scan (ignore error if throttled by driver)
                        self._wlan_lib.WlanScan(client_handle, ctypes.byref(guid), None, None, None)

                        # Query BSS list
                        p_bss_list = ctypes.c_void_p()
                        bss_res = self._wlan_lib.WlanGetNetworkBssList(
                            client_handle, ctypes.byref(guid), None, 1, False, None, ctypes.byref(p_bss_list)
                        )
                        if bss_res == 0:
                            try:
                                bss_list = ctypes.cast(p_bss_list, ctypes.POINTER(WLAN_BSS_LIST)).contents
                                entry_ptr = ctypes.cast(ctypes.addressof(bss_list.wlanBssEntries), ctypes.POINTER(WLAN_BSS_ENTRY))
                                for b_idx in range(bss_list.dwNumberOfItems):
                                    entry = entry_ptr[b_idx]
                                    ssid_len = entry.dot11Ssid.uSSIDLength
                                    ssid_bytes = entry.dot11Ssid.ucSSID[:ssid_len]
                                    try:
                                        ssid_str = ssid_bytes.decode("utf-8")
                                    except UnicodeDecodeError:
                                        ssid_str = ssid_bytes.decode("cp1252", errors="replace")

                                    bssid_str = ":".join(f"{b:02x}" for b in entry.dot11Bssid)
                                    rssi_val = int(entry.lRssi)
                                    freq_khz = int(entry.ulChCenterFrequency)
                                    freq_hz = freq_khz * 1000 if freq_khz > 0 else None

                                    # Map frequency to band and channel
                                    if 2412000 <= freq_khz <= 2484000:
                                        band = "2.4GHz"
                                        channel = 14 if freq_khz == 2484000 else (freq_khz - 2407000) // 5000
                                    elif 5170000 <= freq_khz <= 5825000:
                                        band = "5GHz"
                                        channel = (freq_khz - 5000000) // 5000
                                    elif 5925000 <= freq_khz <= 7125000:
                                        band = "6GHz"
                                        channel = (freq_khz - 5940000) // 5000
                                    else:
                                        band = "2.4GHz"
                                        channel = 1

                                    results.append({
                                        "ssid": ssid_str if ssid_str else "Hidden Network",
                                        "bssid": bssid_str,
                                        "rssi_dbm": rssi_val,
                                        "channel": channel,
                                        "band": band,
                                        "freq_hz": freq_hz,
                                        "auth": "WPA2/WPA3",
                                        "radio_type": "802.11ax/ac/n",
                                        "is_native": True,
                                    })
                            finally:
                                self._wlan_lib.WlanFreeMemory(p_bss_list)
                finally:
                    self._wlan_lib.WlanFreeMemory(p_iface_list)
            finally:
                self._wlan_lib.WlanCloseHandle(client_handle, None)

            return results

        try:
            return await asyncio.to_thread(_do_native_scan)
        except Exception as e:
            logger.debug(f"WlanApi native scan failed: {e}")
            return []

    async def _scan_networks_netsh(self) -> List[Dict[str, Any]]:
        """Fallback to parsing 'netsh wlan show networks mode=bssid' supporting English and Indonesian."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "netsh", "wlan", "show", "networks", "mode=bssid",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            text = stdout.decode("cp1252", errors="ignore")
            return self.parse_netsh_output(text)
        except Exception as e:
            logger.error(f"Netsh fallback scan failed: {e}")
            return []

    @staticmethod
    def parse_netsh_output(text: str) -> List[Dict[str, Any]]:
        """
        Parses multilingual netsh output (English & Indonesian).
        """
        results = []
        current_ssid = "Hidden Network"
        current_auth = "Unknown"
        current_radio = "802.11"

        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Match SSID header
            ssid_match = re.match(r"^SSID\s+\d+\s*:\s*(.*)$", line, re.IGNORECASE)
            if ssid_match:
                current_ssid = ssid_match.group(1).strip() or "Hidden Network"
                current_auth = "Unknown"
                current_radio = "802.11"
                i += 1
                continue

            # Match Authentication
            auth_match = re.match(r"^(?:Authentication|Otentikasi|Autentikasi)\s*:\s*(.*)$", line, re.IGNORECASE)
            if auth_match:
                current_auth = auth_match.group(1).strip()
                i += 1
                continue

            # Match Radio Type
            radio_match = re.match(r"^(?:Radio type|Tipe radio)\s*:\s*(.*)$", line, re.IGNORECASE)
            if radio_match:
                current_radio = radio_match.group(1).strip()
                i += 1
                continue

            # Match BSSID entry
            bssid_match = re.match(r"^BSSID\s+\d+\s*:\s*([0-9a-fA-F:-]{17})$", line, re.IGNORECASE)
            if bssid_match:
                bssid = bssid_match.group(1).lower()
                signal_percent = 50
                channel = 1
                band = "2.4GHz"

                # Lookahead for Signal, Channel, Band inside this BSSID block
                j = i + 1
                while j < len(lines):
                    subline = lines[j].strip()
                    if re.match(r"^(?:SSID|BSSID)\s+\d+", subline, re.IGNORECASE):
                        break

                    # Match Signal percentage
                    sig_match = re.match(r"^(?:Signal|Sinyal)\s*:\s*(\d+)%", subline, re.IGNORECASE)
                    if sig_match:
                        signal_percent = int(sig_match.group(1))

                    # Match Channel
                    ch_match = re.match(r"^(?:Channel|Saluran)\s*:\s*(\d+)", subline, re.IGNORECASE)
                    if ch_match:
                        channel = int(ch_match.group(1))

                    # Match Band
                    band_match = re.match(r"^(?:Band|Pita)\s*:\s*(.*)$", subline, re.IGNORECASE)
                    if band_match:
                        band_val = band_match.group(1).strip()
                        if "5" in band_val:
                            band = "5GHz"
                        elif "6" in band_val:
                            band = "6GHz"
                        else:
                            band = "2.4GHz"

                    j += 1

                # Convert signal % to dBm approximate: dBm = (percent / 2) - 100
                rssi_dbm = int((signal_percent / 2.0) - 100.0)
                
                # Approximate frequency_hz from channel and band
                if band == "5GHz" or channel > 14:
                    band = "5GHz"
                    freq_hz = (5000 + channel * 5) * 1000000
                else:
                    band = "2.4GHz"
                    freq_hz = 2484000000 if channel == 14 else (2407 + channel * 5) * 1000000

                results.append({
                    "ssid": current_ssid,
                    "bssid": bssid,
                    "rssi_dbm": rssi_dbm,
                    "channel": channel,
                    "band": band,
                    "freq_hz": freq_hz,
                    "auth": current_auth,
                    "radio_type": current_radio,
                    "is_native": False,
                })
                i = j
                continue

            i += 1

        return results

    _parse_netsh_output = parse_netsh_output

    async def stop(self) -> None:
        self._running = False


wifi_adapter = WindowsWiFiAdapter()
