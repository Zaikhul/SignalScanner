import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.schemas.common import ScanMode
from app.schemas.measurement import (
    MeasurementBatch,
    NormalizedMeasurementEvent,
    QualityFlags,
    SignalData,
)
from app.schemas.session import CreateSessionRequest
from app.services.session_manager import session_manager


@pytest_asyncio.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_source_mismatch_rejection(async_db: AsyncSession):
    # 1. Create a hardware collector session
    req = CreateSessionRequest(
        name="Real WiFi Scan",
        mode=ScanMode.WIFI,
        collector_id="col_host_01",
        source_type="collector",
    )
    session = await session_manager.create_session(async_db, req)
    await session_manager.start_session(async_db, session.id)

    # 2. Attempt to ingest a batch from a simulator
    fake_batch = MeasurementBatch(
        session_id=session.id,
        collector_id="col_host_01",
        source_type="simulator",  # Mismatch!
        sequence_from=1,
        sequence_to=1,
        measurements=[
            NormalizedMeasurementEvent(
                session_id=session.id,
                collector_id="col_host_01",
                sequence=1,
                mode=ScanMode.WIFI,
                target_id="aa:bb:cc:dd:ee:ff",
                display_name="Fake_AP",
                signal=SignalData(value=-50.0, unit="dBm"),
                quality=QualityFlags(),
            )
        ],
    )

    with pytest.raises(ValueError) as excinfo:
        await session_manager.ingest_batch(async_db, fake_batch)
    assert "SOURCE_MISMATCH" in str(excinfo.value)


@pytest.mark.asyncio
async def test_collector_mismatch_rejection(async_db: AsyncSession):
    # 1. Create a hardware collector session for col_host_01
    req = CreateSessionRequest(
        name="Real WiFi Scan",
        mode=ScanMode.WIFI,
        collector_id="col_host_01",
        source_type="collector",
    )
    session = await session_manager.create_session(async_db, req)
    await session_manager.start_session(async_db, session.id)

    # 2. Attempt to ingest a batch from a different collector
    wrong_collector_batch = MeasurementBatch(
        session_id=session.id,
        collector_id="col_rogue_99",  # Mismatch!
        source_type="collector",
        sequence_from=1,
        sequence_to=1,
        measurements=[
            NormalizedMeasurementEvent(
                session_id=session.id,
                collector_id="col_rogue_99",
                sequence=1,
                mode=ScanMode.WIFI,
                target_id="aa:bb:cc:dd:ee:ff",
                display_name="Real_AP",
                signal=SignalData(value=-50.0, unit="dBm"),
                quality=QualityFlags(),
            )
        ],
    )

    with pytest.raises(ValueError) as excinfo:
        await session_manager.ingest_batch(async_db, wrong_collector_batch)
    assert "COLLECTOR_MISMATCH" in str(excinfo.value)


@pytest.mark.asyncio
async def test_valid_batch_ingest_success(async_db: AsyncSession):
    # 1. Create a matching collector session
    req = CreateSessionRequest(
        name="Real WiFi Scan",
        mode=ScanMode.WIFI,
        collector_id="col_host_01",
        source_type="collector",
    )
    session = await session_manager.create_session(async_db, req)
    await session_manager.start_session(async_db, session.id)

    valid_batch = MeasurementBatch(
        session_id=session.id,
        collector_id="col_host_01",
        source_type="collector",
        sequence_from=1,
        sequence_to=1,
        measurements=[
            NormalizedMeasurementEvent(
                session_id=session.id,
                collector_id="col_host_01",
                sequence=1,
                mode=ScanMode.WIFI,
                target_id="c8:4c:78:19:d8:b2",
                display_name="Jaya-Network",
                signal=SignalData(value=-47.0, unit="dBm"),
                quality=QualityFlags(),
            )
        ],
    )

    res = await session_manager.ingest_batch(async_db, valid_batch)
    assert res["status"] == "ok"
    assert res["ingested_count"] == 1
