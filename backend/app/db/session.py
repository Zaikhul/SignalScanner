import json
from typing import AsyncGenerator
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings
from app.db.models import Base
import app.db.web_scan_models  # Ensure tables are registered in Base.metadata for init_db()

# Create async engine. For sqlite, check_same_thread is set to False
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args=connect_args,
    json_serializer=lambda obj: json.dumps(jsonable_encoder(obj)),
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Initializes schema and tables using metadata and ensures missing columns are created."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def sync_upgrade_columns(sync_conn):
            from sqlalchemy import inspect, text
            inspector = inspect(sync_conn)
            if "measurements" in inspector.get_table_names():
                existing_cols = {c["name"] for c in inspector.get_columns("measurements")}
                cols_to_add = [
                    ("scan_id", "VARCHAR(64)"),
                    ("trace_id", "VARCHAR(64)"),
                    ("freshness", "VARCHAR(32) DEFAULT 'fresh'"),
                    ("source_method", "VARCHAR(64) DEFAULT 'unknown'"),
                    ("rssi_processing", "VARCHAR(32) DEFAULT 'unknown'"),
                    ("quality_flags", "JSON DEFAULT '{}'"),
                    ("raw_extra", "JSON DEFAULT '{}'"),
                ]
                for col_name, col_type in cols_to_add:
                    if col_name not in existing_cols:
                        try:
                            sync_conn.execute(text(f"ALTER TABLE measurements ADD COLUMN {col_name} {col_type}"))
                        except Exception:
                            pass

            if "export_audit_logs" in inspector.get_table_names():
                try:
                    sync_conn.execute(text("ALTER TABLE export_audit_logs ALTER COLUMN format TYPE VARCHAR(64)"))
                except Exception:
                    pass

            if "lan_hosts" in inspector.get_table_names():
                existing_lan_cols = {c["name"] for c in inspector.get_columns("lan_hosts")}
                if "open_ports" not in existing_lan_cols:
                    try:
                        sync_conn.execute(text("ALTER TABLE lan_hosts ADD COLUMN open_ports JSON DEFAULT '[]'"))
                    except Exception:
                        pass

            if "collectors" in inspector.get_table_names():
                try:
                    sync_conn.execute(text("ALTER TABLE collectors ALTER COLUMN last_seen DROP NOT NULL"))
                except Exception:
                    pass

        await conn.run_sync(sync_upgrade_columns)

    # Auto-seed single Local Host Collector if not present
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.db.models import CollectorModel

    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)

        res_def = await session.execute(select(CollectorModel).where(CollectorModel.id == "col_default"))
        def_col = res_def.scalar_one_or_none()
        if not def_col:
            def_col = CollectorModel(
                id="col_default",
                name="Local Host Collector",
                platform="windows",
                version="1.0.0",
                status="offline",
                capabilities={
                    "supported_modes": ["wifi", "bluetooth", "radio"],
                    "adapters": [
                        {"id": "win_wlan_01", "type": "wifi", "name": "Windows Native WiFi Scanner", "is_available": True},
                        {"id": "ble_bleak_01", "type": "bluetooth", "name": "Bleak BLE Scanner", "is_available": True},
                        {"id": "sdr_soapy_01", "type": "radio", "name": "SoapySDR Rx Scanner", "is_available": True},
                    ],
                    "platform": "windows",
                    "version": "1.0.0",
                    "can_sdr": True,
                    "can_wifi": True,
                    "can_ble": True,
                },
                last_seen=datetime.fromtimestamp(0, timezone.utc),
            )
            session.add(def_col)
        else:
            def_col.name = "Local Host Collector"
            def_col.status = "offline"
            def_col.last_seen = datetime.fromtimestamp(0, timezone.utc)

        await session.commit()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency to yield an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
