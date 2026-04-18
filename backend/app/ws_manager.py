from collections import defaultdict

from fastapi import WebSocket
from starlette.websockets import WebSocketState


class WSManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, game_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[game_id].add(websocket)

    def disconnect(self, game_id: str, websocket: WebSocket) -> None:
        if game_id in self._connections:
            self._connections[game_id].discard(websocket)
            if not self._connections[game_id]:
                del self._connections[game_id]

    async def broadcast(self, game_id: str, payload: dict) -> None:
        for socket in list(self._connections.get(game_id, set())):
            if socket.client_state != WebSocketState.CONNECTED:
                self.disconnect(game_id, socket)
                continue
            try:
                await socket.send_json(payload)
            except Exception:
                self.disconnect(game_id, socket)

    def connection_count(self, game_id: str) -> int:
        return len(self._connections.get(game_id, set()))


ws_manager = WSManager()
