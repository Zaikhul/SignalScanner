import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy.signal import find_peaks


class SignalProcessor:
    def __init__(self, default_alpha: float = 0.35):
        self.default_alpha = default_alpha
        # In-memory target EMA state tracker: {target_id: last_smoothed_value}
        self._target_ema_state: Dict[str, float] = {}

    def calculate_ema(self, target_id: str, current_value: float, alpha: Optional[float] = None) -> float:
        """
        Calculates Exponential Moving Average for a target.
        S_t = alpha * Y_t + (1 - alpha) * S_{t-1}
        """
        effective_alpha = alpha if alpha is not None else self.default_alpha
        if target_id not in self._target_ema_state:
            smoothed = current_value
        else:
            prev = self._target_ema_state[target_id]
            smoothed = (effective_alpha * current_value) + ((1.0 - effective_alpha) * prev)
        
        self._target_ema_state[target_id] = round(smoothed, 2)
        return self._target_ema_state[target_id]

    def reset_ema(self, target_id: Optional[str] = None) -> None:
        if target_id:
            self._target_ema_state.pop(target_id, None)
        else:
            self._target_ema_state.clear()

    @staticmethod
    def calculate_snr(signal_val: float, noise_floor: Optional[float]) -> Optional[float]:
        """
        SNR (dB) = Signal (dBm/dBFS) - Noise Floor (dBm/dBFS).
        """
        if noise_floor is None:
            return None
        snr = signal_val - noise_floor
        return round(snr, 1)

    @staticmethod
    def estimate_noise_floor(signals: List[float], fallback: float = -95.0) -> float:
        """
        Estimates noise floor from historical or windowed signal measurements using 10th percentile.
        """
        if not signals:
            return fallback
        arr = np.array(signals, dtype=float)
        p10 = float(np.percentile(arr, 10))
        # Ensure reasonable floor estimate (typically between -110 dBm and -80 dBm)
        return round(min(p10 - 5.0, fallback), 1)

    @staticmethod
    def detect_fft_peaks(
        fft_bins: List[float],
        center_freq_hz: int,
        span_hz: int,
        min_prominence_db: float = 6.0,
        max_peaks: int = 8
    ) -> List[Dict[str, float]]:
        """
        Identifies prominent RF carrier peaks from an FFT bin array.
        Returns list of dicts: [{"frequency_hz": ..., "power_dbfs": ..., "prominence_db": ...}]
        """
        if not fft_bins or len(fft_bins) < 4:
            return []
        
        data = np.array(fft_bins, dtype=float)
        peaks, properties = find_peaks(data, prominence=min_prominence_db)
        
        if len(peaks) == 0:
            return []
        
        num_bins = len(data)
        freq_step = span_hz / num_bins
        start_freq = center_freq_hz - (span_hz / 2.0)
        
        prominences = properties.get("prominences", np.zeros(len(peaks)))
        
        # Sort by peak power descending
        peak_records = []
        for idx, peak_idx in enumerate(peaks):
            freq = start_freq + (peak_idx * freq_step)
            power = float(data[peak_idx])
            prom = float(prominences[idx]) if idx < len(prominences) else 0.0
            peak_records.append({
                "frequency_hz": round(freq),
                "power_dbfs": round(power, 2),
                "prominence_db": round(prom, 2),
                "bin_index": int(peak_idx)
            })
        
        # Sort by power desc and limit
        peak_records.sort(key=lambda p: p["power_dbfs"], reverse=True)
        return peak_records[:max_peaks]

    @staticmethod
    def calculate_channel_overlap_metrics(
        targets: List[Dict[str, Any]],
        window_ms: int = 10000,
    ) -> List[Dict[str, Any]]:
        """
        Calculates structured channel overlap metrics (CHAN-01).
        Clearly classifies evidence as 'inferred' (bss_overlap_index) rather than fake 'measured_airtime'.
        """
        ch_map: Dict[int, List[float]] = {}
        for t in targets:
            ch = t.get("channel")
            if ch is None:
                continue
            rssi = float(t.get("signal_value", -90.0))
            if ch not in ch_map:
                ch_map[ch] = []
            ch_map[ch].append(rssi)

        metrics: List[Dict[str, Any]] = []
        for ch, rssi_list in ch_map.items():
            ap_count = len(rssi_list)
            # Weighted BSS overlap index formula: normalize linear sum of estimated RF powers
            # P_lin = sum(10^(rssi/10)), normalized against reference scale
            linear_sum = sum(10 ** (r / 20.0) for r in rssi_list)
            overlap_index = round(min(linear_sum / 2.0, 1.0), 3)

            metrics.append({
                "channel": ch,
                "metric_type": "bss_overlap_index",
                "value": overlap_index,
                "unit": "ratio",
                "evidence": "inferred",
                "method": "weighted_bssid_overlap_v2",
                "window_ms": window_ms,
                "uncertainty": None,
                "ap_count": ap_count,
                "max_rssi": max(rssi_list) if rssi_list else -100.0,
            })
        return metrics

    @staticmethod
    def calculate_wifi_channel_occupancy(
        targets: List[Dict[str, Any]]
    ) -> Dict[str, Dict[int, Dict[str, Any]]]:
        """
        Groups WiFi targets into channel occupancy map by band.
        Output: {
            "2.4GHz": { 1: {"ap_count": 3, "max_rssi": -65, "overlap_index": 0.45, "evidence": "inferred", "ssids": [...]}, ... },
            "5GHz": { 36: {"ap_count": 2, "max_rssi": -72, "overlap_index": 0.30, "evidence": "inferred", "ssids": [...]}, ... },
            "6GHz": { ... }
        }
        """
        occupancy: Dict[str, Dict[int, Dict[str, Any]]] = {
            "2.4GHz": {},
            "5GHz": {},
            "6GHz": {}
        }
        
        for t in targets:
            ch = t.get("channel")
            band = t.get("band") or "2.4GHz"
            rssi = t.get("signal_value", -100)
            ssid = t.get("display_name") or "Hidden"
            
            if ch is None:
                continue
            
            if band not in occupancy:
                occupancy[band] = {}
            
            if ch not in occupancy[band]:
                occupancy[band][ch] = {
                    "channel": ch,
                    "ap_count": 0,
                    "max_rssi": -120.0,
                    "overlap_index": 0.0,
                    "evidence": "inferred",
                    "ap_list": []
                }
            
            occupancy[band][ch]["ap_count"] += 1
            if rssi > occupancy[band][ch]["max_rssi"]:
                occupancy[band][ch]["max_rssi"] = rssi
            
            # Update overlap index (inferred)
            ap_count = occupancy[band][ch]["ap_count"]
            occupancy[band][ch]["overlap_index"] = round(min(ap_count * 0.15, 1.0), 2)
            
            occupancy[band][ch]["ap_list"].append({
                "target_id": t.get("target_id"),
                "display_name": ssid,
                "rssi": rssi
            })
            
        return occupancy


signal_processor = SignalProcessor()
