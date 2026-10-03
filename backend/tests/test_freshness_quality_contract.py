import pytest
from datetime import datetime, timezone, timedelta
from app.schemas.measurement import QualityFlags, MeasurementQuality, NormalizedMeasurementEvent, SignalData, RadioMetadata


def test_measurement_quality_schema_fields():
    """Verify FQ-01 Measurement Quality contract attributes."""
    now = datetime.now(timezone.utc)
    q = MeasurementQuality(
        calibrated=True,
        permission_limited=False,
        throttled=False,
        scan_id="scn_test_123",
        scan_requested_at=now,
        scan_completed_at=now + timedelta(milliseconds=200),
        observed_at=now + timedelta(milliseconds=180),
        collector_received_at=now + timedelta(milliseconds=200),
        age_ms=20,
        actual_interval_ms=500,
        source_method="windows_native_wifi",
        freshness="fresh",
        cache_possible=False,
        rssi_processing="os_filtered",
        quality_flags=["calibrated"],
        fields_unavailable=[],
    )

    assert q.scan_id == "scn_test_123"
    assert q.source_method == "windows_native_wifi"
    assert q.freshness == "fresh"
    assert q.rssi_processing == "os_filtered"
    assert q.age_ms == 20
    assert q.actual_interval_ms == 500
    assert "calibrated" in q.quality_flags


def test_normalized_measurement_event_with_quality():
    """Verify NormalizedMeasurementEvent encapsulates trace_id and MeasurementQuality."""
    event = NormalizedMeasurementEvent(
        schema_version="2.0",
        trace_id="trc_abc_123",
        scan_id="scn_456",
        session_id="ses_test_01",
        collector_id="col_test_01",
        sequence=1,
        captured_at=datetime.now(timezone.utc),
        mode="wifi",
        target_id="hmac:target_01",
        display_name="TestAP",
        signal=SignalData(value=-65.0, unit="dBm", noise=-95.0),
        radio=RadioMetadata(channel=6, band="2.4GHz", frequency_hz=2437000000),
        quality=MeasurementQuality(
            source_method="windows_native_wifi",
            freshness="fresh",
            rssi_processing="os_filtered",
        ),
    )

    dump = event.model_dump(mode="json")
    assert dump["trace_id"] == "trc_abc_123"
    assert dump["quality"]["source_method"] == "windows_native_wifi"
    assert dump["quality"]["freshness"] == "fresh"
