from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.games import router as game_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.db import create_db_and_tables
from app.observability import TraceMiddleware, log_json
from app.replay_service import replay_service
from app.ws_manager import ws_manager

settings = get_settings()

app = FastAPI(title="AgentMonopoly Backend", version="0.1.0")
app.add_middleware(TraceMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(game_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "AgentMonopoly backend running"}


@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()


@app.websocket("/ws/games/{game_id}")
async def ws_game_events(websocket: WebSocket, game_id: str, since_ts: float = Query(default=0.0)) -> None:
    await ws_manager.connect(game_id, websocket)
    log_json("ws.connected", game_id=game_id, since_ts=since_ts)
    if since_ts > 0:
        for event in replay_service.get_events_since(game_id=game_id, since_ts=since_ts):
            await websocket.send_json(event.model_dump())
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong", "game_id": game_id})
    except WebSocketDisconnect:
        ws_manager.disconnect(game_id, websocket)
        log_json("ws.disconnected", game_id=game_id)
