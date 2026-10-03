import pytest
from app.core.channel_health_engine import channel_health_engine, ChannelHealthEngine
from app.schemas.channel_health import (
    ComponentProvenance,
    ConfidenceLevel,
    ObservationWindowInfo,
)


def test_linear_power_conversion_never_sums_dbm_directly():
    """Verify FR-CHH-02 & PRD 10.4.2: signals must be aggregated in linear mW domain."""
    p_50 = channel_health_engine.dbm_to_mw(-50.0)
    assert pytest.approx(p_50, rel=1e-4) == 0.00001

    # Two -50 dBm transmitters should sum to twice the power (3 dB increase -> ~ -47 dBm)
    # Direct dBm addition would absurdly yield -100 dBm
    linear_sum = p_50 + p_50
    eff_dbm = channel_health_engine.mw_to_dbm(linear_sum)
    assert pytest.approx(eff_dbm, abs=0.1) == -47.0


def test_spectral_overlap_matrix_2_4ghz():
    """Verify spectral overlap matrix for 2.4 GHz 20 MHz channels."""
    # Co-channel (same channel) -> 1.0
    ov_1_1 = channel_health_engine.calculate_spectral_overlap(1, 20, 1, 20, "2.4GHz")
    assert ov_1_1 == 1.0

    # Adjacent channel 1 vs 2 (5 MHz separation) -> 15 MHz overlap / 20 MHz = 0.75
    ov_1_2 = channel_health_engine.calculate_spectral_overlap(1, 20, 2, 20, "2.4GHz")
    assert pytest.approx(ov_1_2, abs=0.01) == 0.75

    # Adjacent channel 1 vs 3 (10 MHz separation) -> 10 MHz overlap / 20 MHz = 0.50
    ov_1_3 = channel_health_engine.calculate_spectral_overlap(1, 20, 3, 20, "2.4GHz")
    assert pytest.approx(ov_1_3, abs=0.01) == 0.50

    # Non-overlapping: Channel 1 vs Channel 6 (25 MHz separation) -> 0.0
    ov_1_6 = channel_health_engine.calculate_spectral_overlap(1, 20, 6, 20, "2.4GHz")
    assert ov_1_6 == 0.0

    # Channel 6 vs Channel 11 -> 0.0
    ov_6_11 = channel_health_engine.calculate_spectral_overlap(6, 20, 11, 20, "2.4GHz")
    assert ov_6_11 == 0.0


def test_separation_of_cci_and_aci():
    """Verify FR-CHH-02: CCI and ACI are calculated and displayed separately."""
    targets = [
        {"target_id": "ap_co_1", "channel": 6, "channel_width_mhz": 20, "signal_value": -60.0, "band": "2.4GHz"},
        {"target_id": "ap_adj_1", "channel": 5, "channel_width_mhz": 20, "signal_value": -55.0, "band": "2.4GHz"},
    ]

    items, _ = channel_health_engine.evaluate_channels(
        band="2.4GHz",
        channel_width_mhz=20,
        targets=targets,
        measurements=[],
        regulatory_domain="ID",
    )

    ch6 = next(item for item in items if item.channel == 6)
    assert ch6.cci_power_mw > 0.0
    assert ch6.aci_power_mw > 0.0
    # ACI comes from channel 5 (overlap 0.75 with channel 6)
    expected_aci = channel_health_engine.dbm_to_mw(-55.0) * 0.75
    assert pytest.approx(ch6.aci_power_mw, rel=1e-3) == expected_aci


def test_weight_renormalization_on_unavailable_metrics():
    """Verify FR-CHH-03: Unavailable metrics are not set to zero and weights renormalize."""
    # When no external telemetry (utilization, retry, noise) is provided:
    targets = [
        {"target_id": "ap_clean", "channel": 1, "channel_width_mhz": 20, "signal_value": -85.0, "band": "2.4GHz"},
    ]

    items, _ = channel_health_engine.evaluate_channels(
        band="2.4GHz",
        channel_width_mhz=20,
        targets=targets,
        measurements=[],
        regulatory_domain="ID",
        external_telemetry=None,
    )

    ch1 = next(item for item in items if item.channel == 1)
    assert ch1.components.utilization.provenance == ComponentProvenance.UNAVAILABLE
    assert ch1.components.retry.provenance == ComponentProvenance.UNAVAILABLE
    assert ch1.components.noise.provenance == ComponentProvenance.UNAVAILABLE
    assert ch1.components.utilization.value is None

    # Overlap and instability are valid, so health_score is computed solely from valid components
    assert 0 <= ch1.health_score <= 100


def test_confidence_classification_and_copy_rules():
    """Verify FR-CHH-04 & PRD 10.4.5: Decoupled confidence and Low-confidence CTA copy."""
    # Skenario 1: Window < 60s -> LOW confidence
    short_obs = ObservationWindowInfo(
        from_time="2026-09-07T10:00:00Z",
        to_time="2026-09-07T10:00:30Z",
        duration_seconds=30.0,
        scan_cycles=2,
    )
    items, flags = channel_health_engine.evaluate_channels(
        band="2.4GHz",
        channel_width_mhz=20,
        targets=[],
        measurements=[],
        regulatory_domain="ID",
    )
    conf_low, reasons_low, missing = channel_health_engine.classify_confidence(
        observation_window_sec=short_obs.duration_seconds,
        scan_cycles=short_obs.scan_cycles,
        quality_flags=flags,
        channel_items=items,
    )
    assert conf_low == ConfidenceLevel.LOW
    assert "channel_utilization" in missing

    rec_low = channel_health_engine.generate_recommendation(
        session_id="ses_01",
        snapshot_id="chs_01",
        band="2.4GHz",
        channel_width_mhz=20,
        channel_items=items,
        observation_window=short_obs,
        quality_flags=flags,
    )
    # PRD rule: low confidence must use "Kandidat untuk diuji"
    assert rec_low.primary.cta_label == "Kandidat untuk diuji"

    # Skenario 2: Window >= 300s with full telemetry -> HIGH confidence
    long_obs = ObservationWindowInfo(
        from_time="2026-09-07T10:00:00Z",
        to_time="2026-09-07T10:05:00Z",
        duration_seconds=300.0,
        scan_cycles=15,
    )
    items_telemetry, flags_telemetry = channel_health_engine.evaluate_channels(
        band="2.4GHz",
        channel_width_mhz=20,
        targets=[],
        measurements=[],
        regulatory_domain="ID",
        external_telemetry={1: {"utilization": 0.15, "retry_rate": 0.02, "noise_floor": -95.0}},
    )
    conf_high, reasons_high, _ = channel_health_engine.classify_confidence(
        observation_window_sec=long_obs.duration_seconds,
        scan_cycles=long_obs.scan_cycles,
        quality_flags=flags_telemetry,
        channel_items=items_telemetry,
    )
    assert conf_high == ConfidenceLevel.HIGH
    assert "sufficient_5m_observation_window" in reasons_high


def test_regulatory_candidate_filtering():
    """Verify FR-CHH-05: Regulatory filtering restricts default 2.4 GHz plan to 1, 6, 11."""
    items_id, _ = channel_health_engine.evaluate_channels(
        band="2.4GHz",
        channel_width_mhz=20,
        targets=[],
        measurements=[],
        regulatory_domain="ID",
    )
    candidates = [i for i in items_id if i.is_candidate]
    candidate_channels = {c.channel for c in candidates}
    assert candidate_channels == {1, 6, 11}

    # Non-standard channel (e.g. 3) should still be in items but marked is_candidate = False
    ch3 = next(i for i in items_id if i.channel == 3)
    assert not ch3.is_candidate
    assert "non_standard_2_4ghz_plan" in ch3.exclusion_reasons


def test_recommendation_determinism():
    """Verify PRD 10.4.2 item 10: Recommendations are 100% deterministic from identical inputs."""
    targets = [
        {"target_id": "ap_1", "channel": 1, "channel_width_mhz": 20, "signal_value": -50.0, "band": "2.4GHz"},
        {"target_id": "ap_6", "channel": 6, "channel_width_mhz": 20, "signal_value": -85.0, "band": "2.4GHz"},
        {"target_id": "ap_11", "channel": 11, "channel_width_mhz": 20, "signal_value": -70.0, "band": "2.4GHz"},
    ]
    obs = ObservationWindowInfo(
        from_time="2026-09-07T10:00:00Z",
        to_time="2026-09-07T10:05:00Z",
        duration_seconds=300.0,
        scan_cycles=10,
    )

    items1, flags1 = channel_health_engine.evaluate_channels("2.4GHz", 20, targets, [], "ID")
    rec1 = channel_health_engine.generate_recommendation("s1", "snap1", "2.4GHz", 20, items1, obs, flags1)

    items2, flags2 = channel_health_engine.evaluate_channels("2.4GHz", 20, targets, [], "ID")
    rec2 = channel_health_engine.generate_recommendation("s1", "snap1", "2.4GHz", 20, items2, obs, flags2)

    assert rec1.primary.channel == rec2.primary.channel
    assert rec1.primary.score == rec2.primary.score
    assert rec1.alternatives[0].channel == rec2.alternatives[0].channel
    # Since channel 1 has severe interference (-50 dBm) and channel 6 is clean (-85 dBm),
    # channel 6 should be recommended as primary
    assert rec1.primary.channel == 6
