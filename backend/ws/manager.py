from typing import Dict, List
from fastapi import WebSocket
import asyncio

class WSManager:
    def __init__(self):
        self.active: Dict[int, List[WebSocket]] = {}

    async def connect(self, comparison_id: int, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(comparison_id, []).append(ws)

    def disconnect(self, comparison_id: int, ws: WebSocket):
        conns = self.active.get(comparison_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self.active.pop(comparison_id, None)

    async def broadcast(self, comparison_id: int, message: dict):
        conns = list(self.active.get(comparison_id, []))
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                try:
                    await ws.close()
                except Exception:
                    pass
                self.disconnect(comparison_id, ws)

ws_manager = WSManager()
