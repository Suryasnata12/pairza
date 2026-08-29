"""
Per-session connection registry + broadcast helper. Kept dependency-free
(only stdlib + FastAPI's WebSocket type) so any domain service — sessions,
rewards, moderation — can import and broadcast without circular imports.

MVP scope: in-process only. A single Postgres/Redis-backed API process
holds all sockets for a session in memory. Scaling to multiple API
processes later means fanning broadcast() out through Redis pub/sub
instead of iterating a local dict — the call sites in the rest of the app
don't change, only this file would.
"""
import json
import uuid
from datetime import datetime, timezone

from fastapi import WebSocket


def _json_default(value):
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


class ConnectionManager:
    def __init__(self) -> None:
        # session_id -> { user_id -> set of live sockets (a user can have >1 tab open) }
        self._rooms: dict[uuid.UUID, dict[uuid.UUID, set[WebSocket]]] = {}

    async def connect(self, session_id: uuid.UUID, user_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        room = self._rooms.setdefault(session_id, {})
        room.setdefault(user_id, set()).add(websocket)

    def disconnect(self, session_id: uuid.UUID, user_id: uuid.UUID, websocket: WebSocket) -> None:
        room = self._rooms.get(session_id)
        if not room or user_id not in room:
            return
        room[user_id].discard(websocket)
        if not room[user_id]:
            del room[user_id]
        if not room:
            self._rooms.pop(session_id, None)

    def is_online(self, session_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        room = self._rooms.get(session_id, {})
        return bool(room.get(user_id))

    def online_user_ids(self, session_id: uuid.UUID) -> set[uuid.UUID]:
        return set(self._rooms.get(session_id, {}).keys())

    async def broadcast(self, session_id: uuid.UUID, event_type: str, payload: dict, exclude_user: uuid.UUID | None = None) -> None:
        room = self._rooms.get(session_id, {})
        message = json.dumps({"type": event_type, "payload": payload}, default=_json_default)
        dead: list[tuple[uuid.UUID, WebSocket]] = []
        for user_id, sockets in room.items():
            if exclude_user is not None and user_id == exclude_user:
                continue
            for ws in sockets:
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.append((user_id, ws))
        for user_id, ws in dead:
            self.disconnect(session_id, user_id, ws)

    async def send_to_user(self, session_id: uuid.UUID, user_id: uuid.UUID, event_type: str, payload: dict) -> None:
        room = self._rooms.get(session_id, {})
        sockets = room.get(user_id, set())
        message = json.dumps({"type": event_type, "payload": payload}, default=_json_default)
        for ws in list(sockets):
            try:
                await ws.send_text(message)
            except Exception:
                self.disconnect(session_id, user_id, ws)


# Process-wide singleton — every module broadcasts through this same instance.
manager = ConnectionManager()
