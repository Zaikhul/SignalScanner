import hashlib
import json
from datetime import datetime, timezone, timedelta
import pytest

from app.db.session import init_db, AsyncSessionLocal
from app.db.models import ExportJobModel
from app.schemas.common import ScanMode
from app.schemas.session import CreateSessionRequest
from app.schemas.measurement import MeasurementBatch, NormalizedMeasurementEvent, SignalData, RadioMetadata, QualityFlags
from app.schemas.export import ExportRequest
from app.schemas.channel_health import ChannelValidationRequest
from app.services.session_manager import session_manager
from app.services.export_service import export_service
from app.services.channel_health_service import channel_health_service
from app.core.web_scan.network_policy import mask_sensitive_query_params


@pytest.mark.asyncio
async def test_f07_streaming_export_and_checksum_integrity():
    """Verify that export generation streams measurements and matches incremental SHA-256 (F07)."""
    await init_db()
    async with AsyncSessionLocal() as db:
        # Create session
        req = CreateSessionRequest(
            name="Streaming Export Test",
            mode="wifi",
            collector_id="col_default",
            source_type="collector",
        )
        ses = await session_manager.create_session(db, req)
        await session_manager.start_session(db, ses.id)

        # Ingest 10 measurements
        events = [
            NormalizedMeasurementEvent(
                session_id=ses.id,
                collector_id="col_default",
                sequence=i,
                mode=ScanMode.WIFI,
                target_id=f"00:11:22:33:44:{i:02d}",
                signal=SignalData(value=-50.0 - i),
                radio=RadioMetadata(channel=6, band="2.4GHz"),
            )
            for i in range(1, 11)
        ]
        batch = MeasurementBatch(
            session_id=ses.id,
            collector_id="col_default",
            source_type="collector",
            sequence_from=1,
            sequence_to=10,
            measurements=events,
        )
        await session_manager.ingest_batch(db, batch)

        # Test JSON streaming export
        exp_json = await export_service.generate_export(
            db, ses.id, ExportRequest(format="json", include_raw_samples=True)
        )
        job_json = await db.get(ExportJobModel, exp_json.id)
        assert job_json is not None
        assert job_json.file_content is not None
        # Verify checksum integrity
        expected_sha = hashlib.sha256(job_json.file_content.encode("utf-8")).hexdigest()
        assert exp_json.checksum_sha256 == expected_sha
        parsed_json = json.loads(job_json.file_content)
        assert len(parsed_json["measurements"]) == 10

        # Test CSV streaming export
        exp_csv = await export_service.generate_export(
            db, ses.id, ExportRequest(format="csv", include_raw_samples=True)
        )
        job_csv = await db.get(ExportJobModel, exp_csv.id)
        assert job_csv is not None
        assert job_csv.file_content is not None
        expected_csv_sha = hashlib.sha256(job_csv.file_content.encode("utf-8")).hexdigest()
        assert exp_csv.checksum_sha256 == expected_csv_sha
        assert "sequence,captured_at,target_id" in job_csv.file_content


@pytest.mark.asyncio
async def test_f07_export_retention_purge():
    """Verify that purge_expired_exports deletes records older than cutoff (F07)."""
    await init_db()
    async with AsyncSessionLocal() as db:
        old_job = ExportJobModel(
            session_id="ses_old",
            format="json",
            status="completed",
            file_size_bytes=100,
            checksum_sha256="abc",
            file_content="{}",
            created_at=datetime.now(timezone.utc) - timedelta(hours=100),
        )
        db.add(old_job)
        await db.commit()

        purged_count = await export_service.purge_expired_exports(db, max_age_hours=72)
        assert purged_count >= 1


def test_f07_sensitive_query_parameter_masking():
    """Verify that credentials in URL query strings are masked while functional params persist (F07/T08)."""
    url = "https://example.com/api/v1/scan?token=secret123&page=5&api_key=mykey456&debug=true"
    masked = mask_sensitive_query_params(url)
    assert "token=%3Credacted%3E" in masked or "token=<redacted>" in masked
    assert "api_key=%3Credacted%3E" in masked or "api_key=<redacted>" in masked
    assert "page=5" in masked
    assert "debug=true" in masked


def test_f08_noise_basis_flag_default():
    """Verify that QualityFlags records noise_basis as assumed when estimated (F08)."""
    q = QualityFlags(noise_basis="assumed")
    assert q.noise_basis == "assumed"


@pytest.mark.asyncio
async def test_f08_channel_validation_matched_targets_and_minimum_samples():
    """Verify that channel validation evaluates matched APs and reports insufficient_data for < 3 samples (F08)."""
    await init_db()
    async with AsyncSessionLocal() as db:
        # Create session
        req = CreateSessionRequest(
            name="Validation Matched Test",
            mode="wifi",
            collector_id="col_default",
            source_type="collector",
        )
        ses = await session_manager.create_session(db, req)
        await session_manager.start_session(db, ses.id)

        now = datetime.now(timezone.utc)
        # Create a marker at now
        from app.schemas.session import SessionMarkerCreate
        marker = await session_manager.add_marker(
            db, ses.id, SessionMarkerCreate(label="Channel 6 Transition", timestamp=now)
        )

        # 1. Test insufficient samples: only 2 samples before and 2 after
        meas_insufficient = []
        for i in range(2):
            meas_insufficient.append(
                NormalizedMeasurementEvent(
                    session_id=ses.id,
                    collector_id="col_default",
                    sequence=100 + i,
                    captured_at=now - timedelta(seconds=10 - i),
                    mode=ScanMode.WIFI,
                    target_id="tgt_ap_matched",
                    signal=SignalData(value=-70.0),
                    radio=RadioMetadata(channel=1, band="2.4GHz"),
                )
            )
        for i in range(2):
            meas_insufficient.append(
                NormalizedMeasurementEvent(
                    session_id=ses.id,
                    collector_id="col_default",
                    sequence=200 + i,
                    captured_at=now + timedelta(seconds=5 + i),
                    mode=ScanMode.WIFI,
                    target_id="tgt_ap_matched",
                    signal=SignalData(value=-60.0),
                    radio=RadioMetadata(channel=6, band="2.4GHz"),
                )
            )
        batch1 = MeasurementBatch(
            session_id=ses.id,
            collector_id="col_default",
            source_type="collector",
            sequence_from=100,
            sequence_to=201,
            measurements=meas_insufficient,
        )
        await session_manager.ingest_batch(db, batch1)

        val_req = ChannelValidationRequest(
            marker_id=marker.id,
            before_window_sec=60,
            after_window_sec=60,
        )
        res_insufficient = await channel_health_service.create_channel_validation_run(db, ses.id, val_req)
        assert "insufficient_data" in res_insufficient.summary_label
        assert res_insufficient.metric_deltas["mean_signal_rssi"].delta is None

        # 2. Ingest enough samples (at least 3 more before and after)
        meas_sufficient = []
        for i in range(3):
            meas_sufficient.append(
                NormalizedMeasurementEvent(
                    session_id=ses.id,
                    collector_id="col_default",
                    sequence=300 + i,
                    captured_at=now - timedelta(seconds=20 - i),
                    mode=ScanMode.WIFI,
                    target_id="tgt_ap_matched",
                    signal=SignalData(value=-70.0),
                    radio=RadioMetadata(channel=1, band="2.4GHz"),
                )
            )
            meas_sufficient.append(
                NormalizedMeasurementEvent(
                    session_id=ses.id,
                    collector_id="col_default",
                    sequence=400 + i,
                    captured_at=now + timedelta(seconds=20 + i),
                    mode=ScanMode.WIFI,
                    target_id="tgt_ap_matched",
                    signal=SignalData(value=-60.0),
                    radio=RadioMetadata(channel=6, band="2.4GHz"),
                )
            )
        batch2 = MeasurementBatch(
            session_id=ses.id,
            collector_id="col_default",
            source_type="collector",
            sequence_from=300,
            sequence_to=402,
            measurements=meas_sufficient,
        )
        await session_manager.ingest_batch(db, batch2)

        res_sufficient = await channel_health_service.create_channel_validation_run(db, ses.id, val_req)
        assert "AP setara teramati" in res_sufficient.summary_label
        assert res_sufficient.metric_deltas["mean_signal_rssi"].delta == 10.0
        assert res_sufficient.metric_deltas["mean_signal_rssi"].improved is True
