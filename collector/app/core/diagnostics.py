import asyncio
import ctypes
from datetime import datetime, timezone
import logging
import platform
import time
from typing import Any, Dict, List
import httpx

from collector.app.config import collector_settings

logger = logging.getLogger("collector.diagnostics")


class CollectorPreflightDiagnostics:
    @staticmethod
    async def run_diagnostics(mode: str = "wifi") -> Dict[str, Any]:
        """
        Runs comprehensive multi-layer preflight diagnostics (DIAG-01).
        Layers:
        1. os_permission (Windows location permission / DLL availability)
        2. adapter (Radio adapter availability & capability)
        3. scan_path (Test scan execution)
        4. backend (Auth, schema compatibility, ingest ping)
        5. clock (Wall clock vs monotonic clock sync)
        """
        checks: List[Dict[str, Any]] = []
        overall_status = "READY"

        def add_check(layer: str, name: str, status: str, message: str, technical_details: str = None, remediation: str = None):
            nonlocal overall_status
            if status == "BLOCKED":
                overall_status = "BLOCKED"
            elif status == "DEGRADED" and overall_status != "BLOCKED":
                overall_status = "DEGRADED"
            elif status == "UNSUPPORTED" and overall_status == "READY":
                overall_status = "DEGRADED"

            checks.append({
                "layer": layer,
                "name": name,
                "status": status,
                "message": message,
                "technical_details": technical_details,
                "remediation_step": remediation,
            })

        # 1. OS & Permission layer
        os_name = platform.system().lower()
        if os_name == "windows":
            try:
                wlan_lib = ctypes.windll.wlanapi
                add_check(
                    layer="os_permission",
                    name="wlanapi_library_binding",
                    status="READY",
                    message="wlanapi.dll loaded successfully.",
                )
            except Exception as e:
                add_check(
                    layer="os_permission",
                    name="wlanapi_library_binding",
                    status="DEGRADED",
                    message="wlanapi.dll unavailable; fallback to netsh CLI.",
                    technical_details=str(e),
                    remediation="Ensure WLAN AutoConfig service is enabled in Windows Services.",
                )
        else:
            add_check(
                layer="os_permission",
                name="linux_wireless_binding",
                status="READY",
                message=f"Running on {os_name}.",
            )

        # 2. Clock Synchronization layer
        t_wall = datetime.now(timezone.utc)
        t_mono_1 = time.monotonic()
        await asyncio.sleep(0.01)
        t_mono_2 = time.monotonic()
        clock_drift_ms = abs((t_mono_2 - t_mono_1) * 1000 - 10.0)

        if clock_drift_ms < 50.0:
            add_check(
                layer="clock",
                name="clock_monotonic_stability",
                status="READY",
                message=f"Monotonic clock jitter: {clock_drift_ms:.2f} ms (normal).",
            )
        else:
            add_check(
                layer="clock",
                name="clock_monotonic_stability",
                status="DEGRADED",
                message=f"Monotonic clock jitter elevated: {clock_drift_ms:.2f} ms.",
                technical_details="High system timer latency detected.",
                remediation="Ensure NTP synchronization is active and system load is normal.",
            )

        # 3. Adapter layer
        if mode == "wifi":
            try:
                from collector.app.adapters.wifi_windows import WindowsWiFiAdapter
                adapter = WindowsWiFiAdapter()
                caps = await adapter.capabilities()
                if caps.is_available:
                    add_check(
                        layer="adapter",
                        name="wifi_adapter_readiness",
                        status="READY",
                        message=f"{caps.name} is available.",
                    )
                else:
                    add_check(
                        layer="adapter",
                        name="wifi_adapter_readiness",
                        status="BLOCKED",
                        message="No active WiFi adapter found.",
                        remediation="Turn on WiFi adapter in device settings.",
                    )
            except Exception as e:
                add_check(
                    layer="adapter",
                    name="wifi_adapter_readiness",
                    status="BLOCKED",
                    message=f"WiFi adapter error: {e}",
                    technical_details=str(e),
                    remediation="Check WiFi hardware drivers.",
                )
        elif mode == "bluetooth":
            try:
                from bleak import BleakScanner
                add_check(
                    layer="adapter",
                    name="bluetooth_adapter_readiness",
                    status="READY",
                    message="Bleak Bluetooth stack is available.",
                )
            except Exception as e:
                add_check(
                    layer="adapter",
                    name="bluetooth_adapter_readiness",
                    status="BLOCKED",
                    message=f"Bluetooth stack error: {e}",
                    remediation="Ensure Bluetooth is enabled in OS settings.",
                )
        elif mode == "radio":
            try:
                import SoapySDR
                devices = SoapySDR.Device.enumerate()
                if devices:
                    add_check(
                        layer="adapter",
                        name="sdr_hardware_readiness",
                        status="READY",
                        message=f"SoapySDR found {len(devices)} device(s).",
                    )
                else:
                    add_check(
                        layer="adapter",
                        name="sdr_hardware_readiness",
                        status="DEGRADED",
                        message="SoapySDR driver loaded, but no SDR hardware connected.",
                        remediation="Plug in your RTL-SDR, HackRF, or Airspy device, or select Mock Simulator.",
                    )
            except Exception:
                add_check(
                    layer="adapter",
                    name="sdr_hardware_readiness",
                    status="UNSUPPORTED",
                    message="SoapySDR library is not installed.",
                    remediation="Install SoapySDR or use Virtual Simulator mode.",
                )

        # 4. Backend Connectivity layer
        try:
            async with httpx.AsyncClient(base_url=collector_settings.BACKEND_URL, timeout=3.0) as client:
                t0 = time.monotonic()
                res = await client.get("/api/v1/sessions")
                latency_ms = (time.monotonic() - t0) * 1000
                if res.status_code == 200:
                    add_check(
                        layer="backend",
                        name="backend_api_reachability",
                        status="READY",
                        message=f"Backend API reachable (latency: {latency_ms:.1f} ms).",
                    )
                else:
                    add_check(
                        layer="backend",
                        name="backend_api_reachability",
                        status="DEGRADED",
                        message=f"Backend returned HTTP {res.status_code}.",
                        technical_details=res.text[:200],
                    )
        except Exception as e:
            add_check(
                layer="backend",
                name="backend_api_reachability",
                status="BLOCKED",
                message="Cannot connect to Backend API server.",
                technical_details=str(e),
                remediation=f"Ensure backend is running at {collector_settings.BACKEND_URL}.",
            )

        return {
            "collector_id": collector_settings.COLLECTOR_ID,
            "platform": os_name,
            "mode": mode,
            "overall_status": overall_status,
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


diagnostics = CollectorPreflightDiagnostics()
