"""
websocket_manager.py
--------------------
Manages WebSocket connections and tenant-scoped broadcast for realtime alerts.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import List, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class _WsConn:
    ws: WebSocket
    organization_id: Optional[int]
    is_super_admin: bool


class ConnectionManager:
    """
    Registry of WebSocket connections with optional tenant scope.

    - is_super_admin=True: receives all payloads (Lumicams platform).
    - Otherwise: only payloads with matching organization_id (or missing org for legacy payloads).
    """

    def __init__(self) -> None:
        self._active: List[_WsConn] = []
        self._lock = asyncio.Lock()

    async def connect(
        self,
        ws: WebSocket,
        *,
        organization_id: Optional[int] = None,
        is_super_admin: bool = False,
    ) -> None:
        await ws.accept()
        async with self._lock:
            self._active.append(
                _WsConn(
                    ws=ws,
                    organization_id=organization_id,
                    is_super_admin=is_super_admin,
                )
            )
        logger.info("WS client connected. Total connections: %d", len(self._active))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._active = [c for c in self._active if c.ws is not ws]
        logger.info("WS client disconnected. Total connections: %d", len(self._active))

    @staticmethod
    def _should_send(conn: _WsConn, payload: dict) -> bool:
        if conn.is_super_admin:
            return True
        oid = payload.get("organization_id")
        if oid is None:
            return True
        try:
            oid_i = int(oid)
        except (TypeError, ValueError):
            return True
        if conn.organization_id is None:
            return False
        return conn.organization_id == oid_i

    async def broadcast(self, payload: dict) -> None:
        dead: List[WebSocket] = []

        async with self._lock:
            connections = list(self._active)

        for conn in connections:
            if not self._should_send(conn, payload):
                continue
            try:
                await conn.ws.send_text(json.dumps(payload))
            except Exception as exc:
                logger.warning("Failed to send to WS client (%s). Removing.", exc)
                dead.append(conn.ws)

        if dead:
            async with self._lock:
                self._active = [c for c in self._active if c.ws not in dead]

    def broadcast_from_thread(self, payload: dict, loop: asyncio.AbstractEventLoop) -> None:
        asyncio.run_coroutine_threadsafe(self.broadcast(payload), loop)

    @property
    def connection_count(self) -> int:
        return len(self._active)


manager = ConnectionManager()
