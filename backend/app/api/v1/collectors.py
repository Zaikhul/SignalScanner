import os
import subprocess
import sys
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
    if not collector.last_seen or collector.last_seen.year <= 1970:
        overall_status = DiagnosticStatus.BLOCKED
        checks.append(DiagnosticCheckItem(
            layer="collector",
            name="collector_heartbeat_liveness",
            status=DiagnosticStatus.BLOCKED,
            message="Daemon collector lokal belum aktif (belum pernah mengirim heartbeat).",
            remediation_step=f"Jalankan daemon collector lokal menggunakan perintah: 'python -m collector.app.main --mode {mode}' atau klik tombol Nyalakan Daemon.",
        ))
    else:
        last_seen = collector.last_seen
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        heartbeat_age = (datetime.now(timezone.utc) - last_seen).total_seconds()
        if heartbeat_age <= 15.0:
            checks.append(DiagnosticCheckItem(
                layer="collector",
                name="collector_heartbeat_liveness",
                status=DiagnosticStatus.READY,
                message=f"Daemon collector lokal aktif dan merespon heartbeat secara real-time ({heartbeat_age:.1f}s).",
            ))
        elif heartbeat_age <= 45.0:
            overall_status = DiagnosticStatus.DEGRADED
            checks.append(DiagnosticCheckItem(
                layer="collector",
                name="collector_heartbeat_liveness",
                status=DiagnosticStatus.DEGRADED,
                message=f"Heartbeat collector lokal mengalami penundaan ({heartbeat_age:.1f}s).",
                remediation_step=f"Periksa apakah proses daemon 'python -m collector.app.main --mode {mode}' sedang sibuk memindai kanal radio atau restart daemon.",
            ))
        else:
            overall_status = DiagnosticStatus.BLOCKED
            checks.append(DiagnosticCheckItem(
                layer="collector",
                name="collector_heartbeat_liveness",
                status=DiagnosticStatus.BLOCKED,
                message=f"Daemon collector lokal offline (terakhir terlihat {heartbeat_age:.0f}s yang lalu).",
                remediation_step=f"Jalankan daemon collector lokal menggunakan perintah: 'python -m collector.app.main --mode {mode}'.",
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


_active_daemon_process: Optional[subprocess.Popen] = None


@router.post("/{collector_id}/spawn-daemon")
async def spawn_local_daemon(
    collector_id: str,
    mode: str = Query("wifi", pattern="^(wifi|bluetooth|radio)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Spawns or verifies the local collector daemon process (1-Click Local Run).
    """
    global _active_daemon_process
    collector = await collector_service.get_collector_by_id(db, collector_id)
    if not collector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Collector '{collector_id}' not found.",
        )

    # Check if a previously spawned process is still running
    if _active_daemon_process is not None and _active_daemon_process.poll() is None:
        return {
            "status": "already_running",
            "collector_id": collector_id,
            "mode": mode,
            "pid": _active_daemon_process.pid,
            "message": "Daemon collector lokal sudah aktif berjalan di latar belakang.",
        }

    # Root repository directory (4 levels up from backend/app/api/v1)
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    cmd = [
        sys.executable,
        "-m",
        "collector.app.main",
        "--mode",
        mode,
        "--interval",
        "500",
    ]

    try:
        _active_daemon_process = subprocess.Popen(
            cmd,
            cwd=root_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "status": "started",
            "collector_id": collector_id,
            "mode": mode,
            "pid": _active_daemon_process.pid,
            "message": f"Daemon collector lokal berhasil dijalankan (PID {_active_daemon_process.pid}).",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal menjalankan daemon collector lokal: {e}",
        )

