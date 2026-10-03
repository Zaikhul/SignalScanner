from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.services.web_scan_service import WebScanService

logger = logging.getLogger("signal_scanner.web_scan.ws")

router = APIRouter(tags=["web-scan-websocket"])


@router.websocket("/ws/v1/web-scans/{scan_id}")
async def web_scan_websocket_endpoint(
    websocket: WebSocket,
    scan_id: str,
    ticket: Optional[str] = Query(None),
    after_sequence: int = Query(0, ge=0),
):
    """
    Real-time streaming WebSocket endpoint for Web Scanner.
    Authenticates via single-use ticket, bootstraps current snapshot,
    replays historical events from after_sequence, and streams live updates.
    """
    if not getattr(settings, "WEB_SCANNER_ENABLED", False):
        await websocket.close(code=4404, reason="Web Scanner is disabled")
        return

    if not ticket:
        await websocket.close(code=4401, reason="Missing authorization ticket")
        return

    # Authenticate single-use ticket against database
    async with AsyncSessionLocal() as db:
        auth_data = await WebScanService.consume_ws_ticket(db, ticket)
        if not auth_data or auth_data.get("scan_id") != scan_id:
            await websocket.close(code=4401, reason="Invalid or expired ticket")
            return
        tenant_id = auth_data["tenant_id"]

    await websocket.accept()

    try:
        # Bootstrap snapshot and events
        async with AsyncSessionLocal() as db:
            snapshot = await WebScanService.get_scan_snapshot(db, tenant_id, scan_id)
            if snapshot:
                await websocket.send_text(
                    json.dumps({
                        "type": "snapshot",
                        "scan_id": scan_id,
                        "payload": snapshot.model_dump(mode="json"),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                )

            # Replay any events missed
            replays = await WebScanService.list_scan_events(db, tenant_id, scan_id, after_sequence=after_sequence)
            for ev in replays:
                await websocket.send_text(
                    json.dumps({
                        "type": ev.type,
                        "scan_id": scan_id,
                        "sequence": ev.sequence,
                        "payload": ev.payload if isinstance(ev.payload, dict) else (
                            ev.payload.model_dump(mode="json") if hasattr(ev.payload, "model_dump") else {}
                        ),
                        "timestamp": ev.occurred_at.isoformat(),
                    })
                )

        # Connection keep-alive and event loop
        last_polled_seq = replays[-1].sequence if replays else after_sequence
        while True:
            try:
                # Non-blocking receive with short timeout for responsive streaming
                msg_text = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                try:
                    data = json.loads(msg_text)
                    if data.get("type") == "ping":
                        await websocket.send_text(
                            json.dumps({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
                        )
                except Exception:
                    pass
            except asyncio.TimeoutError:
                pass

            # Periodic event check on every cycle
            async with AsyncSessionLocal() as db:
                new_events = await WebScanService.list_scan_events(
                    db, tenant_id, scan_id, after_sequence=last_polled_seq
                )
                for ev in new_events:
                    await websocket.send_text(
                        json.dumps({
                            "type": ev.type,
                            "scan_id": scan_id,
                            "sequence": ev.sequence,
                            "payload": ev.payload if isinstance(ev.payload, dict) else (
                                ev.payload.model_dump(mode="json") if hasattr(ev.payload, "model_dump") else {}
                            ),
                            "timestamp": ev.occurred_at.isoformat(),
                        })
                    )
                    last_polled_seq = ev.sequence

    except WebSocketDisconnect:
        logger.debug("Web scan websocket disconnected for scan %s", scan_id)
    except Exception as exc:
        logger.warning("Error in web scan websocket loop for scan %s: %s", scan_id, exc)
