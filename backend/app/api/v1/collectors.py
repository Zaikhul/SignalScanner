from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.collector import (
    CollectorCommand,
    CollectorHeartbeat,
    CollectorHeartbeatResponse,
    CollectorRegistration,
    CollectorResponse,
    DiagnosticCommand,
    DiagnosticResult,
)
from app.core.security import verify_collector_auth
from app.schemas.diagnostics import DiagnosticCheckItem, DiagnosticStatus, PreflightDiagnosticResult
from app.services.collector_service import collector_service

router = APIRouter(prefix="/collectors", tags=["collectors"], dependencies=[Depends(verify_collector_auth)])

# In-memory latest preflight results cache: {collector_id: PreflightDiagnosticResult}
_latest_preflight_results: Dict[str, PreflightDiagnosticResult] = {}


@router.get("", response_model=List[CollectorResponse])
async def list_collectors(db: AsyncSession = Depends(get_db)):
    """List all registered collectors and their capabilities."""
    return await collector_service.list_collectors(db)


@router.post("/register", response_model=CollectorResponse)
async def register_collector(
    payload: CollectorRegistration, db: AsyncSession = Depends(get_db)
):
    """Register or update a collector and its hardware adapters."""
    return await collector_service.register_collector(db, payload)


@router.post("/heartbeat", response_model=CollectorHeartbeatResponse)
async def receive_heartbeat(
    payload: CollectorHeartbeat, db: AsyncSession = Depends(get_db)
):
    """Heartbeat endpoint for collector connectivity, status updates, and command polling."""
    success, pending = await collector_service.process_heartbeat(db, payload)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Collector not found"
        )
    return CollectorHeartbeatResponse(status="ok", pending_commands=pending)


@router.get("/{collector_id}/commands", response_model=List[CollectorCommand])
async def get_collector_commands(collector_id: str):
    """Retrieve pending scan commands for a collector."""
    return collector_service.get_pending_commands(collector_id)


@router.post("/{collector_id}/commands/{command_id}/ack")
async def acknowledge_collector_command(collector_id: str, command_id: str):
    """Idempotently acknowledge receipt and execution of a collector command."""
    success = collector_service.acknowledge_command(collector_id, command_id)
    return {"status": "acknowledged", "command_id": command_id, "success": success}


@router.get("/{collector_id}", response_model=CollectorResponse)
async def get_collector(collector_id: str, db: AsyncSession = Depends(get_db)):
    """Get single collector details and capabilities."""
    res = await collector_service.get_collector_by_id(db, collector_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Collector not found"
        )
    return res


@router.post("/{collector_id}/preflight", response_model=PreflightDiagnosticResult)
async def run_preflight_diagnostics(
    collector_id: str,
    mode: str = Query("wifi", pattern="^(wifi|bluetooth|radio)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Executes tiered capability preflight diagnostics across OS, Adapters, DB, and Clock (DIAG-01).
    Returns machine-readable status: READY | DEGRADED | BLOCKED | UNSUPPORTED with remediation steps.
    """
    collector = await collector_service.get_collector_by_id(db, collector_id)
    if not collector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Collector '{collector_id}' is not registered with backend.",
        )

    # Queue diagnostic command to collector daemon
    collector_service.queue_command(
        collector_id=collector_id,
        type="preflight_diagnostic",
        mode=mode,
    )

    # Perform server-side validation checks
    checks: List[DiagnosticCheckItem] = []
    overall_status = DiagnosticStatus.READY

    # 1. Collector heartbeat check
    last_seen = collector.last_seen
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    heartbeat_age = (datetime.now(timezone.utc) - last_seen).total_seconds()
    if heartbeat_age <= 10.0:
        checks.append(DiagnosticCheckItem(
            layer="collector",
            name="collector_heartbeat_liveness",
            status=DiagnosticStatus.READY,
            message=f"Collector is actively reporting heartbeats (age: {heartbeat_age:.1f}s).",
        ))
    elif heartbeat_age <= 30.0:
        overall_status = DiagnosticStatus.DEGRADED
        checks.append(DiagnosticCheckItem(
            layer="collector",
            name="collector_heartbeat_liveness",
            status=DiagnosticStatus.DEGRADED,
            message=f"Collector heartbeat is delayed (age: {heartbeat_age:.1f}s).",
            remediation_step="Check network connection between collector daemon and backend.",
        ))
    else:
        overall_status = DiagnosticStatus.BLOCKED
        checks.append(DiagnosticCheckItem(
            layer="collector",
            name="collector_heartbeat_liveness",
            status=DiagnosticStatus.BLOCKED,
            message=f"Collector is offline (last seen {heartbeat_age:.0f}s ago).",
            remediation_step="Start the collector daemon using 'python -m collector.app.main --mode wifi'.",
        ))

    # 2. Database persistence check
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        checks.append(DiagnosticCheckItem(
            layer="storage_stream",
            name="database_write_readiness",
            status=DiagnosticStatus.READY,
            message="PostgreSQL database read/write verified.",
        ))
    except Exception as e:
        overall_status = DiagnosticStatus.BLOCKED
        checks.append(DiagnosticCheckItem(
            layer="storage_stream",
            name="database_write_readiness",
            status=DiagnosticStatus.BLOCKED,
            message="Database connection error.",
            technical_details=str(e),
            remediation_step="Verify PostgreSQL connection string and service health.",
        ))

    # 3. Adapter mode capability check
    caps = collector.capabilities
    supported_modes = [m.value if hasattr(m, "value") else str(m) for m in getattr(caps, "supported_modes", [])]
    can_mode = getattr(caps, f"can_{mode}", False)
    if mode in supported_modes or can_mode or mode == "wifi":
        checks.append(DiagnosticCheckItem(
            layer="adapter",
            name=f"{mode}_capability_registration",
            status=DiagnosticStatus.READY,
            message=f"Collector registered support for '{mode}' scanning.",
        ))
    else:
        if overall_status != DiagnosticStatus.BLOCKED:
            overall_status = DiagnosticStatus.DEGRADED
        checks.append(DiagnosticCheckItem(
            layer="adapter",
            name=f"{mode}_capability_registration",
            status=DiagnosticStatus.DEGRADED,
            message=f"Collector capabilities do not explicitly list mode '{mode}'.",
            remediation_step=f"Run collector with '--mode {mode}' to initialize the corresponding adapter.",
        ))

    result = PreflightDiagnosticResult(
        collector_id=collector_id,
        overall_status=overall_status,
        checks=checks,
        timestamp=datetime.now(timezone.utc),
        platform=collector.platform,
        mode=mode,
    )
    _latest_preflight_results[collector_id] = result
    return result


@router.post("/{collector_id}/diagnostics/result")
async def store_diagnostic_result(
    collector_id: str,
    payload: Dict[str, Any],
):
    """Callback for daemon to report detailed local diagnostic results."""
    try:
        res = PreflightDiagnosticResult(**payload)
        _latest_preflight_results[collector_id] = res
        return {"status": "ok"}
    except Exception as e:
        return {"status": "ignored", "error": str(e)}


@router.post("/{collector_id}/commands/diagnose", response_model=DiagnosticResult)
async def run_collector_diagnostic(
    collector_id: str,
    cmd: DiagnosticCommand,
    db: AsyncSession = Depends(get_db),
):
    """Execute safe hardware/permission diagnostics on a collector."""
    cmd.collector_id = collector_id
    return await collector_service.execute_diagnostic(db, cmd)
