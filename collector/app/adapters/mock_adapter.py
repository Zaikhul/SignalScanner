import asyncio
from datetime import datetime, timezone
import math
import random
from typing import Any, AsyncIterator, Dict, List
import numpy as np

from collector.app.config import collector_settings
from collector.app.core.adapter_base import (
    AdapterCapabilities,
    ScanConfig,
    SignalAdapter,
    ValidationResult,
)
from collector.app.core.pseudonymizer import pseudonymize_id


class MockSignalAdapter(SignalAdapter):
    """
    High-fidelity virtual signal adapter for WiFi, BLE, and SDR simulation.
    Generates physically consistent RF models with noise and attenuation drift.
    """
    def __init__(self, mode: str = "wifi"):
        self.mode = mode.lower()
        self._running = False
        self._seq = 0
        self._init_targets()

    def _init_targets(self):
        # Predefined simulated targets
        if self.mode == "wifi":
            self.sim_targets = [
                {"ssid": "Office_HQ_5G", "mac": "00:1A:2B:3C:4D:01", "channel": 36, "band": "5GHz", "freq": 5180000000, "base_rssi": -52.0},
                {"ssid": "Office_HQ_2.4G", "mac": "00:1A:2B:3C:4D:02", "channel": 6, "band": "2.4GHz", "freq": 2437000000, "base_rssi": -48.0},
                {"ssid": "Guest_Portal", "mac": "00:1A:2B:3C:4D:03", "channel": 1, "band": "2.4GHz", "freq": 2412000000, "base_rssi": -65.0},
                {"ssid": "IoT_Sensor_Net", "mac": "00:1A:2B:3C:4D:04", "channel": 11, "band": "2.4GHz", "freq": 2462000000, "base_rssi": -72.0},
                {"ssid": "Warehouse_AP_North", "mac": "00:1A:2B:3C:4D:05", "channel": 40, "band": "5GHz", "freq": 5200000000, "base_rssi": -60.0},
                {"ssid": "Warehouse_AP_South", "mac": "00:1A:2B:3C:4D:06", "channel": 44, "band": "5GHz", "freq": 5220000000, "base_rssi": -81.0},
                {"ssid": "Lab_AX_WiFi6", "mac": "00:1A:2B:3C:4D:07", "channel": 149, "band": "5GHz", "freq": 5745000000, "base_rssi": -55.0},
            ]
        elif self.mode == "bluetooth":
            self.sim_targets = [
                {"name": "Nordic_Smart_Beacon", "mac": "C0:EE:40:11:22:01", "base_rssi": -58.0, "mfg": "Nordic Semiconductor", "uuid": "0000feaa-0000-1000-8000-00805f9b34fb"},
                {"name": "SensorTag_HT", "mac": "C0:EE:40:11:22:02", "base_rssi": -68.0, "mfg": "Texas Instruments", "uuid": "0000aa10-0000-1000-8000-00805f9b34fb"},
                {"name": "iBeacon_Proximity", "mac": "C0:EE:40:11:22:03", "base_rssi": -49.0, "mfg": "Apple Inc.", "uuid": "0000fd5a-0000-1000-8000-00805f9b34fb"},
                {"name": "ESP32_Telemetry_01", "mac": "C0:EE:40:11:22:04", "base_rssi": -77.0, "mfg": "Espressif", "uuid": "0000ffff-0000-1000-8000-00805f9b34fb"},
                {"name": "BLE_Wearable_HR", "mac": "C0:EE:40:11:22:05", "base_rssi": -63.0, "mfg": "Garmin/Polar", "uuid": "0000180d-0000-1000-8000-00805f9b34fb"},
                {"name": "Asset_Tag_Pallet_9", "mac": "C0:EE:40:11:22:06", "base_rssi": -84.0, "mfg": "U-Blox", "uuid": "0000181a-0000-1000-8000-00805f9b34fb"},
            ]
        else:
            self.sim_targets = []

    async def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_id=f"mock_{self.mode}_01",
            mode=self.mode,
            name=f"Virtual {self.mode.upper()} Simulator",
            is_available=True,
            driver_version="Virtual 2.0",
            details={"is_mock": True, "bands": ["2.4GHz", "5GHz", "6GHz", "Sub-GHz RF"]},
        )

    async def validate(self, config: ScanConfig) -> ValidationResult:
        return ValidationResult(is_valid=True)

    async def start(self, config: ScanConfig) -> AsyncIterator[Dict[str, Any]]:
        self._running = True
        self._seq = config.initial_sequence
        interval = max(0.2, config.sample_interval_ms / 1000.0)
        start_time = asyncio.get_event_loop().time()

        while self._running:
            if config.duration_seconds is not None and (asyncio.get_event_loop().time() - start_time) >= config.duration_seconds:
                break
            self._seq += 1
            batch = self._generate_batch(config)
            yield batch
            await asyncio.sleep(interval)

    def _generate_batch(self, config: ScanConfig) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        measurements: List[Dict[str, Any]] = []

        if self.mode == "wifi":
            for ap in self.sim_targets:
                # Add random noise and slow sinusoidal drift
                drift = 4.0 * math.sin(self._seq * 0.15 + hash(ap["ssid"]) % 10)
                noise = random.gauss(0, 1.5)
                rssi = round(ap["base_rssi"] + drift + noise, 1)
                rssi = max(-95.0, min(-30.0, rssi))

                measurements.append({
                    "schema_version": "1.0",
                    "session_id": config.session_id,
                    "collector_id": collector_settings.COLLECTOR_ID,
                    "sequence": self._seq,
                    "captured_at": now_iso,
                    "mode": "wifi",
                    "target_id": pseudonymize_id(ap["mac"]),
                    "display_name": ap["ssid"],
                    "signal": {
                        "value": rssi,
                        "unit": "dBm",
                        "noise": -94.0 + random.gauss(0, 0.5),
                    },
                    "radio": {
                        "frequency_hz": ap["freq"],
                        "channel": ap["channel"],
                        "band": ap["band"],
                    },
                    "quality": {
                        "calibrated": False,
                        "permission_limited": False,
                        "throttled": False,
                        "freshness": "simulated",
                        "source_method": "virtual_simulator",
                        "rssi_processing": "synthetic",
                    },
                    "extra_metadata": {
                        "security": "WPA3-Personal" if "WiFi6" in ap["ssid"] else "WPA2-Enterprise",
                    }
                })

        elif self.mode == "bluetooth":
            for ble in self.sim_targets:
                drift = 5.0 * math.sin(self._seq * 0.2 + hash(ble["name"]) % 7)
                noise = random.gauss(0, 2.0)
                rssi = round(ble["base_rssi"] + drift + noise, 1)
                rssi = max(-98.0, min(-35.0, rssi))

                measurements.append({
                    "schema_version": "1.0",
                    "session_id": config.session_id,
                    "collector_id": collector_settings.COLLECTOR_ID,
                    "sequence": self._seq,
                    "captured_at": now_iso,
                    "mode": "bluetooth",
                    "target_id": pseudonymize_id(ble["mac"]),
                    "display_name": ble["name"],
                    "signal": {
                        "value": rssi,
                        "unit": "dBm",
                        "noise": -96.0,
                    },
                    "radio": None,
                    "quality": {
                        "calibrated": False,
                        "permission_limited": False,
                        "throttled": False,
                        "freshness": "simulated",
                        "source_method": "virtual_simulator",
                        "rssi_processing": "synthetic",
                    },
                    "extra_metadata": {
                        "manufacturer": ble["mfg"],
                        "service_uuid": ble["uuid"],
                    }
                })

        elif self.mode == "radio":
            fft_size = config.fft_size or 512
            center_freq = config.center_frequency_hz or 433920000
            span = config.span_hz or 2000000

            # Generate synthetic noise floor around -92 dBFS
            bins = np.random.normal(-92.0, 2.0, fft_size)

            # Inject 2 synthetic RF carriers (e.g. 433.92 MHz primary and 434.4 MHz secondary)
            center_bin = fft_size // 2
            # Primary peak
            peak_power = -38.0 + 3.0 * math.sin(self._seq * 0.3)
            for offset in [-2, -1, 0, 1, 2]:
                bins[center_bin + offset] = max(bins[center_bin + offset], peak_power - abs(offset) * 4.0)

            # Secondary peak
            sec_bin = int(center_bin + fft_size * 0.24)
            sec_power = -52.0 + 2.0 * math.cos(self._seq * 0.25)
            for offset in [-1, 0, 1]:
                bins[sec_bin + offset] = max(bins[sec_bin + offset], sec_power - abs(offset) * 3.0)

            max_power = round(float(np.max(bins)), 1)
            measurements.append({
                "schema_version": "2.0",
                "session_id": config.session_id,
                "collector_id": collector_settings.COLLECTOR_ID,
                "sequence": self._seq,
                "captured_at": now_iso,
                "mode": "radio",
                "target_id": pseudonymize_id(f"rf_center_{center_freq}"),
                "display_name": f"RF {center_freq / 1e6:.2f} MHz Carrier",
                "signal": {
                    "value": max_power,
                    "unit": "dBFS",
                    "noise": -92.0,
                },
                "radio": {
                    "center_frequency_hz": center_freq,
                    "span_hz": span,
                    "fft_size": fft_size,
                    "fft_bins": [round(float(b), 1) for b in bins],
                },
                "quality": {
                    "calibrated": False,
                    "permission_limited": False,
                    "throttled": False,
                    "freshness": "simulated",
                    "source_method": "virtual_simulator",
                    "rssi_processing": "synthetic",
                },
                "extra_metadata": {}
            })

        return {
            "schema_version": "2.0",
            "session_id": config.session_id,
            "collector_id": collector_settings.COLLECTOR_ID,
            "source_type": config.source_type or "collector",
            "sequence_from": self._seq,
            "sequence_to": self._seq,
            "sent_at": now_iso,
            "measurements": measurements,
        }

    async def stop(self) -> None:
        self._running = False
