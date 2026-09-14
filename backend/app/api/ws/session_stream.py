import asyncio
from datetime import datetime, timezone
import orjson
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.stream_engine import stream_engine
from app.db.models import ScanSessionModel
from app.db.session import AsyncSessionLocal
from app.services.session_manager import session_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/v1/sessions/{session_id}")
async def session_websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    after_sequence: int = Query(0, ge=0),
):
    """
    Real-time streaming WebSocket endpoint for Live Scan.
    Provides snapshot bootstrap, sequence replay, and low-latency batch broadcasts.
    """
    await websocket.accept()

    # Bootstrap snapshot from DB
    try:
        async with AsyncSessionLocal() as db:
            session_resp = await session_manager.get_session_response(db, session_id)
            targets = await session_manager.list_targets(db, session_id)

        snapshot_event = {
            "type": "session.snapshot",
            "schema_version": "1.0",
            "session_id": session_id,
            "status": session_resp.status.value,
            "session": session_resp.model_dump(mode="json"),
            "targets": [t.model_dump(mode="json") for t in targets],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await websocket.send_text(orjson.dumps(snapshot_event).decode("utf-8"))

        # Replay any buffered batches if reconnecting with after_sequence > 0
        if after_sequence > 0:
            replays = await stream_engine.get_replay_batches(session_id, after_sequence)
            for replay_batch in replays:
                await websocket.send_text(orjson.dumps(replay_batch).decode("utf-8"))

        # Register for live fanout
        await stream_engine.register_subscriber(session_id, websocket)

        # Keep connection open and receive client control signals or pings
        while True:
            data_text = await websocket.receive_text()
            try:
                msg = orjson.loads(data_text)
                if msg.get("type") == "ping":
                    await websocket.send_text(
                        orjson.dumps({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()}).decode("utf-8")
                    )
            except Exception:
                pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            error_event = {
                "type": "error.contextual",
                "session_id": session_id,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await websocket.send_text(orjson.dumps(error_event).decode("utf-8"))
        except Exception:
            pass
    finally:
        await stream_engine.unregister_subscriber(session_id, websocket)
