import pytest
import numpy as np
from app.core.signal_processor import SignalProcessor


def test_calculate_ema():
    sp = SignalProcessor(default_alpha=0.5)
    target_id = "test_ap_1"

    # Step 1: First value should equal initial value
    val1 = sp.calculate_ema(target_id, -70.0)
    assert val1 == -70.0

    # Step 2: Second value: 0.5 * (-60.0) + 0.5 * (-70.0) = -65.0
    val2 = sp.calculate_ema(target_id, -60.0)
    assert val2 == -65.0

    # Step 3: Third value: 0.5 * (-50.0) + 0.5 * (-65.0) = -57.5
    val3 = sp.calculate_ema(target_id, -50.0)
    assert val3 == -57.5


def test_calculate_snr():
    sp = SignalProcessor()
    # Signal -60 dBm, Noise -90 dBm -> SNR = 30 dB
    snr = sp.calculate_snr(-60.0, -90.0)
    assert snr == 30.0

    # Signal -85 dBm, Noise -95 dBm -> SNR = 10 dB
    snr2 = sp.calculate_snr(-85.0, -95.0)
    assert snr2 == 10.0

    # Missing noise floor -> None
    assert sp.calculate_snr(-70.0, None) is None


def test_estimate_noise_floor():
    sp = SignalProcessor()
    samples = [-65.0, -70.0, -80.0, -85.0, -90.0, -92.0, -95.0]
    floor = sp.estimate_noise_floor(samples)
    assert floor <= -95.0


def test_detect_fft_peaks():
    sp = SignalProcessor()
    # Create synthetic FFT spectrum with 2 peaks
    fft_size = 128
    bins = np.full(fft_size, -90.0)  # Noise floor at -90 dBFS
    bins[32] = -45.0  # Peak 1 at bin 32
    bins[64] = -30.0  # Peak 2 at bin 64 (higher)

    peaks = sp.detect_fft_peaks(
        fft_bins=bins.tolist(),
        center_freq_hz=433920000,
        span_hz=2000000,
        min_prominence_db=10.0,
    )

    assert len(peaks) == 2
    # Highest peak should be first
    assert peaks[0]["power_dbfs"] == -30.0
    assert peaks[1]["power_dbfs"] == -45.0


def test_calculate_wifi_channel_occupancy():
    sp = SignalProcessor()
    targets = [
        {"channel": 1, "band": "2.4GHz", "signal_value": -65.0, "display_name": "AP_Main"},
        {"channel": 1, "band": "2.4GHz", "signal_value": -78.0, "display_name": "AP_Guest"},
        {"channel": 6, "band": "2.4GHz", "signal_value": -55.0, "display_name": "AP_Office"},
        {"channel": 36, "band": "5GHz", "signal_value": -60.0, "display_name": "AP_5G"},
    ]

    occ = sp.calculate_wifi_channel_occupancy(targets)
    assert "2.4GHz" in occ
    assert "5GHz" in occ
    assert occ["2.4GHz"][1]["ap_count"] == 2
    assert occ["2.4GHz"][1]["max_rssi"] == -65.0
    assert occ["2.4GHz"][6]["ap_count"] == 1
    assert occ["5GHz"][36]["ap_count"] == 1
