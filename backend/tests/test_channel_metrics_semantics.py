import pytest
from app.core.signal_processor import signal_processor


def test_channel_overlap_metrics_evidence_inferred():
    """Verify CHAN-01 channel overlap taxonomy: evidence is explicitly 'inferred' and never 'measured'."""
    targets = [
        {"channel": 6, "signal_value": -50.0, "display_name": "AP_1"},
        {"channel": 6, "signal_value": -65.0, "display_name": "AP_2"},
        {"channel": 1, "signal_value": -78.0, "display_name": "AP_3"},
    ]

    metrics = signal_processor.calculate_channel_overlap_metrics(targets)
    assert len(metrics) == 2

    m_ch6 = next(m for m in metrics if m["channel"] == 6)
    assert m_ch6["metric_type"] == "bss_overlap_index"
    assert m_ch6["evidence"] == "inferred"
    assert m_ch6["unit"] == "ratio"
    assert m_ch6["ap_count"] == 2
    assert m_ch6["value"] > 0.0

    m_ch1 = next(m for m in metrics if m["channel"] == 1)
    assert m_ch1["evidence"] == "inferred"
    assert m_ch1["ap_count"] == 1


def test_wifi_channel_occupancy_includes_inferred_evidence():
    """Verify calculate_wifi_channel_occupancy outputs explicit inferred evidence."""
    targets = [
        {"channel": 36, "band": "5GHz", "signal_value": -55.0, "display_name": "5G_AP"},
    ]
    occupancy = signal_processor.calculate_wifi_channel_occupancy(targets)
    assert "5GHz" in occupancy
    assert 36 in occupancy["5GHz"]
    assert occupancy["5GHz"][36]["evidence"] == "inferred"
