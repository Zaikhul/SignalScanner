import asyncio
from datetime import datetime, timezone
import logging
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional
from bleak import BleakScanner

from collector.app.config import collector_settings
from collector.app.core.adapter_base import (
    AdapterCapabilities,
    ScanConfig,
    SignalAdapter,
    ValidationResult,
)
from collector.app.core.pseudonymizer import pseudonymize_id

logger = logging.getLogger("collector.ble")


class BleakSignalAdapter(SignalAdapter):
    def __init__(self):
        self._running = False
        self._seq = 0
        self._discovered_devices: Dict[str, Dict[str, Any]] = {}
        self._scanner: Optional[BleakScanner] = None

    async def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_id="ble_bleak_native_01",
            mode="bluetooth",
            name="BLE Scanner (Bleak)",
            is_available=True,
            driver_version="Bleak 3.0",
            details={"passive_scan": True, "identity_tracking": "BLEID-01"},
        )

    async def validate(self, config: ScanConfig) -> ValidationResult:
        return ValidationResult(is_valid=True)

    @staticmethod
    def _classify_address_type(address: str) -> tuple[str, float, bool]:
        """
        Classifies BLE MAC address type according to Bluetooth Core Spec Vol 6:
        - Public address
        - Random Static (top 2 bits = 11 -> 0xC0..0xFF)
        - Resolvable Private Address (RPA, top 2 bits = 01 -> 0x40..0x7F)
        - Non-resolvable Private Address (top 2 bits = 00 -> 0x00..0x3F)
        Returns: (address_type, identity_confidence, rotation_suspected)
        """
        parts = address.split(":") if ":" in address else address.split("-")
        if len(parts) >= 1:
            try:
                first_byte = int(parts[0], 16)
                top_2_bits = (first_byte >> 6) & 0x03
                if top_2_bits == 0x03:
                    return "random_static", 0.85, False
                elif top_2_bits == 0x01:
                    return "resolvable_private", 0.45, True
                elif top_2_bits == 0x00:
                    return "non_resolvable_private", 0.30, True
            except ValueError:
                pass
        return "public", 1.0, False

    def _detection_callback(self, device, advertisement_data):
        address = device.address or "unknown_ble"
        name = advertisement_data.local_name or device.name or "BLE Device"
        rssi = advertisement_data.rssi or -80
        mfg_data = advertisement_data.manufacturer_data or {}
        uuids = advertisement_data.service_uuids or []

        addr_type, confidence, rotation = self._classify_address_type(address)
        now_dt = datetime.now(timezone.utc)

        existing = self._discovered_devices.get(address)
        obs_count = (existing["observation_count"] + 1) if existing else 1
        presence = "present" if obs_count >= 2 else "candidate"

        self._discovered_devices[address] = {
            "address": address,
            "name": name,
            "rssi": rssi,
            "address_type": addr_type,
            "identity_confidence": confidence,
            "rotation_suspected": rotation,
            "presence_state": presence,
            "observation_count": obs_count,
            "mfg_data": str(list(mfg_data.keys())) if mfg_data else None,
            "uuids": uuids,
            "last_seen_dt": now_dt,
            "last_seen": now_dt.isoformat(),
        }

    async def start(self, config: ScanConfig) -> AsyncIterator[Dict[str, Any]]:
        self._running = True
        self._seq = config.initial_sequence
        interval = max(0.5, config.sample_interval_ms / 1000.0)

        try:
            self._scanner = BleakScanner(detection_callback=self._detection_callback)
            await self._scanner.start()
        except Exception as e:
            logger.error(f"Failed to start Bleak scanner: {e}")

        while self._running:
            self._seq += 1
            now_dt = datetime.now(timezone.utc)
            now_iso = now_dt.isoformat()
            scan_id = f"scn_ble_{uuid.uuid4().hex[:8]}"
            measurements = []

            # Check presence decay (present -> fading -> lost)
            for addr, dev in list(self._discovered_devices.items()):
                age_sec = (now_dt - dev["last_seen_dt"]).total_seconds()
                if age_sec > 15.0:
                    dev["presence_state"] = "lost"
                elif age_sec > 5.0:
                    dev["presence_state"] = "fading"

                freshness = "fresh" if age_sec <= 3.0 else ("stale" if age_sec <= 10.0 else "expired")

                measurements.append({
                    "schema_version": "2.0",
                    "scan_id": scan_id,
                    "session_id": config.session_id,
                    "collector_id": collector_settings.COLLECTOR_ID,
                    "sequence": self._seq,
                    "captured_at": dev["last_seen"],
                    "mode": "bluetooth",
                    "target_id": pseudonymize_id(dev["address"]),
                    "display_name": dev["name"],
                    "signal": {
                        "value": float(dev["rssi"]),
                        "unit": "dBm",
                        "noise": -96.0,
                    },
                    "radio": None,
                    "quality": {
                        "calibrated": False,
                        "permission_limited": False,
                        "throttled": False,
                        "scan_id": scan_id,
                        "scan_requested_at": now_iso,
                        "scan_completed_at": now_iso,
                        "observed_at": dev["last_seen"],
                        "collector_received_at": now_iso,
                        "age_ms": int(age_sec * 1000),
                        "actual_interval_ms": int(interval * 1000),
                        "source_method": "bleak_ble",
                        "freshness": freshness,
                        "cache_possible": False,
                        "rssi_processing": "os_filtered",
                        "quality_flags": ["passive_scan"],
                        "fields_unavailable": [],
                    },
                    "ble_identity": {
                        "address_type": dev["address_type"],
                        "identity_scope": "session" if dev["rotation_suspected"] else "global",
                        "identity_confidence": dev["identity_confidence"],
                        "name_source": "advertisement_local_name" if dev["name"] != "BLE Device" else "unknown",
                        "rotation_suspected": dev["rotation_suspected"],
                        "presence_state": dev["presence_state"],
                    },
                    "extra_metadata": {
                        "mfg": dev.get("mfg_data"),
                        "service_uuids": dev.get("uuids"),
                        "raw_address_masked": dev["address"][:8] + ":XX:XX:XX" if len(dev["address"]) >= 8 else "XX:XX",
                    }
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

    async def stop(self) -> None:
        self._running = False
        if self._scanner:
            try:
                await self._scanner.stop()
            except Exception:
                pass


ble_adapter = BleakSignalAdapter()
