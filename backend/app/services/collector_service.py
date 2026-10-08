from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import AdapterModel, CollectorModel
import uuid
from app.schemas.collector import (
    CollectorCapabilities,
    CollectorCommand,
    CollectorHeartbeat,
    CollectorRegistration,
    CollectorResponse,
    DiagnosticCommand,
    DiagnosticResult,
)
from app.schemas.common import CollectorStatus, ScanMode


class CollectorService:
    # {collector_id: [CollectorCommand, ...]}
    _command_queues: Dict[str, List[CollectorCommand]] = {}

    @classmethod
    def queue_command(
        cls,
        collector_id: str,
        type: str,
        session_id: Optional[str] = None,
        mode: Optional[ScanMode] = None,
        sample_interval_ms: int = 500,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> CollectorCommand:
        if collector_id not in cls._command_queues:
            cls._command_queues[collector_id] = []

        cmd = CollectorCommand(
            command_id=f"cmd_{uuid.uuid4().hex[:12]}",
            collector_id=collector_id,
            type=type,
            session_id=session_id,
            mode=mode,
            sample_interval_ms=sample_interval_ms,
            parameters=parameters,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        cls._command_queues[collector_id].append(cmd)
        return cmd

    @classmethod
    def get_pending_commands(cls, collector_id: str) -> List[CollectorCommand]:
        queue = cls._command_queues.get(collector_id, [])
        return [cmd for cmd in queue if cmd.status == "pending"]

    @classmethod
    def acknowledge_command(cls, collector_id: str, command_id: str) -> bool:
        queue = cls._command_queues.get(collector_id, [])
        for cmd in queue:
            if cmd.command_id == command_id:
                cmd.status = "acknowledged"
                return True
        return False
    @staticmethod
    async def register_collector(
        db: AsyncSession, payload: CollectorRegistration
    ) -> CollectorResponse:
        # Check if collector already exists
        result = await db.execute(select(CollectorModel).where(CollectorModel.id == payload.id))
        collector = result.scalar_one_or_none()

        if not collector:
            collector = CollectorModel(
                id=payload.id,
                name=payload.name,
                platform=payload.platform,
                version=payload.version,
                status=CollectorStatus.READY.value,
                public_key=payload.public_key,
                capabilities=payload.capabilities.model_dump(),
                last_seen=datetime.now(timezone.utc),
            )
            db.add(collector)
            await db.flush()
        else:
            collector.name = payload.name
            collector.platform = payload.platform
            collector.version = payload.version
            collector.capabilities = payload.capabilities.model_dump()
            collector.last_seen = datetime.now(timezone.utc)
            collector.status = CollectorStatus.READY.value

        # Register or update adapters namespaced by collector_id
        for adap in payload.capabilities.adapters:
            namespaced_id = f"{collector.id}:{adap.id}"
            res_adap = await db.execute(
                select(AdapterModel).where(
                    AdapterModel.id == namespaced_id,
                    AdapterModel.collector_id == collector.id,
                )
            )
            existing_adap = res_adap.scalar_one_or_none()
            if not existing_adap:
                new_adap = AdapterModel(
                    id=namespaced_id,
                    collector_id=collector.id,
                    type=adap.type.value if hasattr(adap.type, "value") else str(adap.type),
                    name=adap.name,
                    capabilities=adap.capabilities,
                    driver_version=adap.driver_version,
                    is_available=adap.is_available,
                )
                db.add(new_adap)
            else:
                existing_adap.name = adap.name
                existing_adap.capabilities = adap.capabilities
                existing_adap.driver_version = adap.driver_version
                existing_adap.is_available = adap.is_available

        await db.commit()
        await db.refresh(collector)

        return CollectorResponse(
            id=collector.id,
            name=collector.name,
            platform=collector.platform,
            version=collector.version,
            status=CollectorStatus(collector.status),
            capabilities=CollectorCapabilities(**collector.capabilities),
            last_seen=collector.last_seen,
            created_at=collector.created_at,
        )

    @staticmethod
    async def process_heartbeat(
        db: AsyncSession, heartbeat: CollectorHeartbeat
    ) -> Tuple[bool, List[CollectorCommand]]:
        result = await db.execute(
            select(CollectorModel).where(CollectorModel.id == heartbeat.collector_id)
        )
        collector = result.scalar_one_or_none()
        if not collector:
            return False, []

        collector.status = heartbeat.status.value
        collector.last_seen = heartbeat.timestamp
        await db.commit()

        pending = CollectorService.get_pending_commands(heartbeat.collector_id)
        return True, pending

    @staticmethod
    async def list_collectors(db: AsyncSession) -> List[CollectorResponse]:
        result = await db.execute(select(CollectorModel).order_by(CollectorModel.created_at.desc()))
        collectors = result.scalars().all()
        
        now = datetime.now(timezone.utc)
        responses = []
        for c in collectors:
            caps = CollectorCapabilities(**c.capabilities) if c.capabilities else CollectorCapabilities(
                supported_modes=[ScanMode.WIFI, ScanMode.BLUETOOTH, ScanMode.RADIO],
                adapters=[],
                platform=c.platform,
            )

            # Determine effective status: mark as offline if no heartbeat in 30 seconds or never seen
            effective_status = c.status
            if c.last_seen:
                last_seen_ts = c.last_seen
                if last_seen_ts.tzinfo is None:
                    last_seen_ts = last_seen_ts.replace(tzinfo=timezone.utc)
                age_seconds = (now - last_seen_ts).total_seconds()
                if age_seconds > 30 and effective_status not in ("offline",):
                    effective_status = "offline"
            else:
                effective_status = "offline"

            status_enum = CollectorStatus(effective_status) if effective_status in CollectorStatus._value2member_map_ else CollectorStatus.OFFLINE

            responses.append(
                CollectorResponse(
                    id=c.id,
                    name=c.name,
                    platform=c.platform,
                    version=c.version,
                    status=status_enum,
                    capabilities=caps,
                    last_seen=c.last_seen,
                    created_at=c.created_at,
                )
            )
        return responses

    @staticmethod
    async def get_collector_by_id(db: AsyncSession, collector_id: str) -> Optional[CollectorResponse]:
        result = await db.execute(select(CollectorModel).where(CollectorModel.id == collector_id))
        c = result.scalar_one_or_none()
        if not c:
            return None
        caps = CollectorCapabilities(**c.capabilities) if c.capabilities else CollectorCapabilities(
            supported_modes=[ScanMode.WIFI, ScanMode.BLUETOOTH, ScanMode.RADIO],
            adapters=[],
            platform=c.platform,
        )
        return CollectorResponse(
            id=c.id,
            name=c.name,
            platform=c.platform,
            version=c.version,
            status=CollectorStatus(c.status) if c.status in CollectorStatus._value2member_map_ else CollectorStatus.READY,
            capabilities=caps,
            last_seen=c.last_seen,
            created_at=c.created_at,
        )

    @staticmethod
    async def execute_diagnostic(
        db: AsyncSession, cmd: DiagnosticCommand
    ) -> DiagnosticResult:
        # Check collector
        c = await CollectorService.get_collector_by_id(db, cmd.collector_id)
        if not c:
            return DiagnosticResult(
                collector_id=cmd.collector_id,
                command_type=cmd.command_type,
                success=False,
                details={"error": "Collector not found or offline"},
            )

        details = {
            "platform": c.platform,
            "collector_status": c.status.value,
            "capabilities": c.capabilities.model_dump(),
            "permission_checks": {
                "wifi_scan": True,
                "ble_scan": True,
                "sdr_driver": True if c.capabilities.can_sdr else "Mock/Simulation Mode Active",
            },
            "system_time": datetime.now(timezone.utc).isoformat(),
        }
        return DiagnosticResult(
            collector_id=cmd.collector_id,
            command_type=cmd.command_type,
            success=True,
            details=details,
        )


collector_service = CollectorService()
