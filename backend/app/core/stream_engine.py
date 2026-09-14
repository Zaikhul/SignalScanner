import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Deque, Dict, List, Optional, Set
import orjson
from fastapi import WebSocket


class StreamEngine:
    """
    In-memory real-time stream hub with replay ring buffer and WebSocket fanout.
    Supports seamless fallback when Redis is not running.
    """
    def __init__(self, buffer_size: int = 500):
        self.buffer_size = buffer_size
        # {session_id: deque([batch_envelope, ...])}
        self._replay_buffers: Dict[str, Deque[Dict[str, Any]]] = {}
        # {session_id: set([WebSocket, ...])}
        self._subscribers: Dict[str, Set[WebSocket]] = {}
        # {session_id: current_sequence_counter}
        self._sequence_counters: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def register_subscriber(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if session_id not in self._subscribers:
                self._subscribers[session_id] = set()
            self._subscribers[session_id].add(websocket)

    async def unregister_subscriber(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if session_id in self._subscribers:
                self._subscribers[session_id].discard(websocket)
                if not self._subscribers[session_id]:
                    del self._subscribers[session_id]

    async def get_next_sequence(self, session_id: str) -> int:
        async with self._lock:
            current = self._sequence_counters.get(session_id, 0) + 1
            self._sequence_counters[session_id] = current
            return current

    async def publish_event(self, session_id: str, event: Dict[str, Any]) -> None:
        """
        Stores event in replay buffer and broadcasts to all active WebSocket listeners for the session.
        """
        async with self._lock:
            if session_id not in self._replay_buffers:
                self._replay_buffers[session_id] = deque(maxlen=self.buffer_size)
            
            self._replay_buffers[session_id].append(event)
            subs = list(self._subscribers.get(session_id, []))

        # Fanout without holding the main lock
        if not subs:
            return

        serialized = orjson.dumps(event).decode("utf-8")
        dead_sockets: List[WebSocket] = []
        
        for ws in subs:
            try:
                await ws.send_text(serialized)
            except Exception:
                dead_sockets.append(ws)

        if dead_sockets:
            async with self._lock:
                for ws in dead_sockets:
                    if session_id in self._subscribers:
                        self._subscribers[session_id].discard(ws)

    async def get_replay_batches(self, session_id: str, after_sequence: int) -> List[Dict[str, Any]]:
        """
        Retrieves all buffered events with sequence number > after_sequence for fast recovery after reconnect.
        """
        async with self._lock:
            buffer = self._replay_buffers.get(session_id)
            if not buffer:
                return []
            
            replays = []
            for event in buffer:
                # check sequence_to or sequence in envelope
                seq = event.get("sequence_to") or event.get("sequence", 0)
                if seq > after_sequence:
                    replays.append(event)
            return replays

    async def clear_session(self, session_id: str) -> None:
        async with self._lock:
            self._replay_buffers.pop(session_id, None)
            self._subscribers.pop(session_id, None)
            self._sequence_counters.pop(session_id, None)


stream_engine = StreamEngine()
