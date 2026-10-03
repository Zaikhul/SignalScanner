import asyncio
from datetime import datetime, timezone
import logging
import uuid
from typing import Any, AsyncIterator, Dict, Optional
import numpy as np

from collector.app.config import collector_settings
from collector.app.core.adapter_base import (
    AdapterCapabilities,
    ScanConfig,
    SignalAdapter,
    ValidationResult,
)
from collector.app.core.pseudonymizer import pseudonymize_id

logger = logging.getLogger("collector.sdr")

# Optional SoapySDR import
try:
    import SoapySDR
    from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
    SOAPY_AVAILABLE = True
except ImportError:
    SOAPY_AVAILABLE = False


class SoapySDRSignalAdapter(SignalAdapter):
    def __init__(self):
        self._running = False
        self._seq = 0
        self._device = None
        self._rx_stream = None

    async def capabilities(self) -> AdapterCapabilities:
        is_avail = SOAPY_AVAILABLE
        details = {"soapy_installed": SOAPY_AVAILABLE}
        
        if SOAPY_AVAILABLE:
            try:
                results = SoapySDR.Device.enumerate()
                details["devices_found"] = len(results)
                is_avail = len(results) > 0
            except Exception as e:
                details["error"] = str(e)
                is_avail = False

        return AdapterCapabilities(
            adapter_id="sdr_soapy_01",
            mode="radio",
            name="SoapySDR Hardware Receiver",
            is_available=is_avail,
            driver_version="SoapySDR 0.8" if SOAPY_AVAILABLE else "Not Installed",
            details=details,
        )

    async def validate(self, config: ScanConfig) -> ValidationResult:
        if not SOAPY_AVAILABLE:
            return ValidationResult(
                is_valid=False,
                error_message="SoapySDR library is not installed on this system. Use Mock Simulator instead."
            )
        return ValidationResult(is_valid=True)

    async def start(self, config: ScanConfig) -> AsyncIterator[Dict[str, Any]]:
        self._running = True
        center_freq = config.center_frequency_hz or 433920000
        sample_rate = config.sample_rate_hz or 2048000
        gain = config.gain_db or 20.0
        fft_size = config.fft_size or 1024
        interval = max(0.1, config.sample_interval_ms / 1000.0)

        # Connect SDR if available
        if SOAPY_AVAILABLE:
            try:
                self._device = SoapySDR.Device()
                self._device.setSampleRate(SOAPY_SDR_RX, 0, sample_rate)
                self._device.setFrequency(SOAPY_SDR_RX, 0, center_freq)
                self._device.setGain(SOAPY_SDR_RX, 0, gain)
                self._rx_stream = self._device.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, [0])
                self._device.activateStream(self._rx_stream)
            except Exception as e:
                logger.error(f"Failed to activate SoapySDR: {e}")

        buffer = np.zeros(fft_size, dtype=np.complex64)

        if not SOAPY_AVAILABLE or not self._device or not self._rx_stream:
            raise RuntimeError("SoapySDR hardware device or stream is not available. Hardware mode failed.")

        while self._running:
            self._seq += 1
            now_dt = datetime.now(timezone.utc)
            now_iso = now_dt.isoformat()
            scan_id = f"scn_sdr_{uuid.uuid4().hex[:8]}"

            overflow_detected = False
            try:
                sr = self._device.readStream(self._rx_stream, [buffer], fft_size)
                if hasattr(sr, "ret") and sr.ret < 0:
                    overflow_detected = True
                windowed = buffer * np.hanning(fft_size)
                fft_res = np.fft.fftshift(np.fft.fft(windowed))
                power_dbfs = 20 * np.log10(np.abs(fft_res) / fft_size + 1e-12)
                bins = [round(float(b), 1) for b in power_dbfs]
            except Exception as e:
                logger.error(f"Error reading SoapySDR stream: {e}")
                raise RuntimeError(f"SoapySDR stream read error: {e}")

            max_power = round(float(max(bins)), 1)
            clipping_detected = max_power >= -0.5

            q_flags = ["iq_stream", "uncalibrated_dbfs"]
            if clipping_detected:
                q_flags.append("clipping_detected")
            if overflow_detected:
                q_flags.append("overflow_detected")

            yield {
                "schema_version": "2.0",
                "scan_id": scan_id,
                "session_id": config.session_id,
                "collector_id": collector_settings.COLLECTOR_ID,
                "source_type": "collector",
                "sequence_from": self._seq,
                "sequence_to": self._seq,
                "sent_at": now_iso,
                "measurements": [
                    {
                        "schema_version": "2.0",
                        "scan_id": scan_id,
                        "session_id": config.session_id,
                        "collector_id": collector_settings.COLLECTOR_ID,
                        "sequence": self._seq,
                        "captured_at": now_iso,
                        "mode": "radio",
                        "target_id": pseudonymize_id(f"rf_{center_freq}"),
                        "display_name": f"RF {center_freq / 1e6:.2f} MHz",
                        "signal": {
                            "value": max_power,
                            "unit": "dBFS",
                            "noise": -92.0,
                        },
                        "radio": {
                            "center_frequency_hz": center_freq,
                            "span_hz": sample_rate,
                            "fft_size": fft_size,
                            "fft_bins": bins,
                        },
                        "quality": {
                            "calibrated": False,
                            "permission_limited": False,
                            "throttled": False,
                            "scan_id": scan_id,
                            "scan_requested_at": now_iso,
                            "scan_completed_at": now_iso,
                            "observed_at": now_iso,
                            "collector_received_at": now_iso,
                            "age_ms": 0,
                            "actual_interval_ms": int(interval * 1000),
                            "source_method": "soapysdr_rx",
                            "freshness": "fresh",
                            "cache_possible": False,
                            "rssi_processing": "raw",
                            "quality_flags": q_flags,
                            "fields_unavailable": ["absolute_power_dbm"],
                        },
                        "extra_metadata": {
                            "gain_db": gain,
                            "clipping_detected": clipping_detected,
                            "overflow_detected": overflow_detected,
                        }
                    }
                ],
            }
            await asyncio.sleep(interval)

    async def stop(self) -> None:
        self._running = False
        if self._device and self._rx_stream:
            try:
                self._device.deactivateStream(self._rx_stream)
                self._device.closeStream(self._rx_stream)
            except Exception:
                pass


sdr_adapter = SoapySDRSignalAdapter()
