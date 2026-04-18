import json
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from sqlmodel import delete, select

from app.agent_runtime import AgentRuntime, RuntimeConfig, TurnBuildInput, decide_fallback
from app.db import get_session
from app.game_engine import GameManager, initialize_game_state, run_game_turn, run_turn
from app.models import Action, Alliance, Game, GameSnapshot, IdempotencyRecord, Player, Property
from app.observability import log_json, metrics
from app.replay_service import replay_service
from app.schemas import (
    ActionCommand,
    ActionRequest,
    ActionResponse,
    ActionType,
    BoardSnapshot,
    CreateGameRequest,
    ErrorCode,
    Phase,
    PlayTurnRequest,
    ReplayExport,
    ReplayResponse,
    TileType,
    TurnInputV31,
)
from app.ws_manager import ws_manager

router = APIRouter(prefix="/games", tags=["games"])
_GAME_RUNTIME_STATE: dict[str, dict] = {}
_GAME_LOCKS: dict[str, threading.Lock] = defaultdict(threading.Lock)
_manager = GameManager()
_runtime = AgentRuntime(config=RuntimeConfig())


def _serialize_state(state: dict) -> str:
    phase_value = state["phase"].value if hasattr(state.get("phase"), "value") else state.get("phase")
    board_payload = []
    for tile in state.get("board", []):
        tile_type = tile.get("type")
        board_payload.append(
            {
                **tile,
                "type": tile_type.value if hasattr(tile_type, "value") else tile_type,
            }
        )
    payload = {
        **state,
        "phase": phase_value,
        "board": board_payload,
        "pending_alliance": [list(item) for item in state.get("pending_alliance", set())],
    }
    return json.dumps(payload, ensure_ascii=False)


def _upsert_game_state_to_db(game_state: dict) -> None:
    with get_session() as session:
        game = session.get(Game, game_state["game_id"])
        if game is None:
            game = Game(
                id=game_state["game_id"],
                round_index=game_state["round_index"],
                current_player_id=game_state["player_order"][game_state["current_player_idx"]],
                phase=str(game_state["phase"]),
                status="active",
            )
            session.add(game)
        else:
            game.round_index = game_state["round_index"]
            game.current_player_id = game_state["player_order"][game_state["current_player_idx"]]
            game.phase = str(game_state["phase"])

        session.execute(delete(Player).where(Player.game_id == game_state["game_id"]))
        session.execute(delete(Property).where(Property.game_id == game_state["game_id"]))
        session.execute(delete(Alliance).where(Alliance.game_id == game_state["game_id"]))

        for player_id, p in game_state["players"].items():
            session.add(
                Player(
                    id=f"{game_state['game_id']}:{player_id}",
                    game_id=game_state["game_id"],
                    name=player_id,
                    position=p["position"],
                    cash=p["cash"],
                    deposit=p["deposit"],
                    alive=p["alive"],
                )
            )
        for idx, tile in enumerate(game_state["board"]):
            if (tile.get("type").value if hasattr(tile.get("type"), "value") else tile.get("type")) != TileType.PROPERTY.value:
                continue
            session.add(
                Property(
                    id=f"{game_state['game_id']}:property:{idx}",
                    game_id=game_state["game_id"],
                    position=idx,
                    owner_id=tile.get("owner_id"),
                    level=int(tile.get("level", 0)),
                )
            )
        for a, b in game_state.get("alliances", {}).items():
            if not b:
                continue
            if a < b:
                session.add(Alliance(game_id=game_state["game_id"], player_a_id=a, player_b_id=b, active=True))

        session.add(
            GameSnapshot(
                game_id=game_state["game_id"],
                round_index=game_state["round_index"],
                snapshot_json=_serialize_state(game_state),
            )
        )
        session.commit()


def _record_action(
    game_id: str,
    round_index: int,
    player_id: str,
    turn_id: str,
    action: str,
    accepted: bool,
    message: str,
    trace_id: str,
) -> None:
    with get_session() as session:
        session.add(
            Action(
                game_id=game_id,
                round_index=round_index,
                player_id=player_id,
                turn_id=turn_id,
                action=action,
                accepted=accepted,
                message=message,
                trace_id=trace_id,
            )
        )
        session.commit()


def _load_idempotent(endpoint: str, game_id: str, key: str) -> dict | None:
    with get_session() as session:
        stmt = (
            select(IdempotencyRecord)
            .where(IdempotencyRecord.endpoint == endpoint)
            .where(IdempotencyRecord.game_id == game_id)
            .where(IdempotencyRecord.key == key)
        )
        row = session.exec(stmt).first()
        if not row:
            return None
        return json.loads(row.response_json)


def _save_idempotent(endpoint: str, game_id: str, key: str, response: dict) -> None:
    with get_session() as session:
        session.add(
            IdempotencyRecord(
                endpoint=endpoint,
                game_id=game_id,
                key=key,
                response_json=json.dumps(response, ensure_ascii=False),
            )
        )
        session.commit()


class WsHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, game_id: str, socket: WebSocket) -> None:
        await socket.accept()
        self._connections[game_id].add(socket)

    def disconnect(self, game_id: str, socket: WebSocket) -> None:
        if game_id in self._connections:
            self._connections[game_id].discard(socket)
            if not self._connections[game_id]:
                del self._connections[game_id]

    async def broadcast(self, game_id: str, payload: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for socket in self._connections.get(game_id, set()):
            try:
                await socket.send_json(payload)
            except Exception:
                stale.append(socket)
        for socket in stale:
            self.disconnect(game_id, socket)


_ws_hub = WsHub()


def _build_turn_input_v2(game_id: str):
    session = _manager.get_game(game_id)
    current = session.players[session.current_player_index]
    snapshots = _manager.build_players_snapshot(session)
    player_snapshot = next(item for item in snapshots if item.player_id == current.player_id)
    payload = TurnBuildInput(
        turn_meta=_manager.build_turn_meta(session),
        tile_context=_manager.build_tile_context(session),
        player_state=player_snapshot,
        players_snapshot=snapshots,
        board_snapshot=BoardSnapshot(track_length=len(session.board), tiles=_manager.build_board_snapshot(session)),
        options=session.allowed_actions,
        history_records=[
            {
                "event_id": item.event_id,
                "type": item.type,
                "round_index": item.round_index,
                "turn_index": item.turn_index,
                "payload": item.payload,
            }
            for item in session.events[-20:]
        ],
    )
    return _runtime.build_turn_input(payload)


def _build_replay_export_v2(game_id: str) -> ReplayExport:
    session = _manager.get_game(game_id)
    replay = _manager.replay(game_id)
    total_turns = max(replay.total_turns, 1)
    fallback_turns = sum(1 for step in replay.steps if step.decision_audit and step.decision_audit.status == "fallback")
    illegal_actions = sum(
        1 for event in session.events if event.type == "action.rejected" and event.payload.get("reason") == "action_not_allowed"
    )
    net_worths = {player.player_id: player.net_worth for player in _manager.state(game_id).players}
    strategy_timeline = [
        {
            "turn_index": step.turn_index,
            "round_index": step.round_index,
            "final_action": step.final_action,
            "candidate_actions": step.candidate_actions,
            "strategy_tags": step.strategy_tags,
            "phase_trace": step.phase_trace,
        }
        for step in replay.steps
    ]
    metrics_payload = {
        "total_turns": float(replay.total_turns),
        "fallback_ratio": fallback_turns / total_turns,
        "illegal_action_rate": illegal_actions / total_turns,
        "top_net_worth": float(max(net_worths.values()) if net_worths else 0),
        "avg_net_worth": float(sum(net_worths.values()) / max(len(net_worths), 1)),
    }
    lines = [
        f"# Game Summary {game_id}",
        "",
        "## Metrics",
        f"- total_turns: {int(metrics_payload['total_turns'])}",
        f"- fallback_ratio: {metrics_payload['fallback_ratio']:.3f}",
        f"- illegal_action_rate: {metrics_payload['illegal_action_rate']:.3f}",
        f"- top_net_worth: {metrics_payload['top_net_worth']:.1f}",
        f"- avg_net_worth: {metrics_payload['avg_net_worth']:.1f}",
        "",
        "## Strategy Timeline",
    ]
    for row in strategy_timeline[-20:]:
        lines.append(
            f"- turn {row['turn_index']} / round {row['round_index']} => final={row['final_action']}, "
            f"candidates={row['candidate_actions']}, tags={row['strategy_tags']}"
        )
    return ReplayExport(
        game_id=game_id,
        generated_at=datetime.now(timezone.utc),
        metrics=metrics_payload,
        strategy_timeline=strategy_timeline,
        markdown="\n".join(lines),
    )


@router.post("", response_model=dict)
async def create_game_v2(payload: CreateGameRequest) -> dict[str, Any]:
    if not payload.players:
        raise HTTPException(status_code=400, detail="players is required for v2 create")
    try:
        session = _manager.create_game(payload.game_id, payload.players, payload.max_rounds, payload.seed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    state = _manager.state(session.game_id)
    await _ws_hub.broadcast(payload.game_id, {"type": "game.started", "state": state.model_dump(mode="json")})
    return {"game_id": payload.game_id, "state": state.model_dump(mode="json")}


@router.get("", response_model=dict)
def list_games_v2() -> dict[str, Any]:
    return {"games": _manager.list_games()}


@router.post("/{game_id}/actions", response_model=ActionResponse)
async def submit_action_v2(game_id: str, payload: ActionRequest) -> ActionResponse:
    if payload.game_id != game_id:
        raise HTTPException(status_code=400, detail="game_id mismatch")
    if not _manager.has_game(game_id):
        raise HTTPException(status_code=404, detail="unknown game")
    action = payload.action.value if isinstance(payload.action, ActionType) else str(payload.action)
    args = payload.args or payload.params
    accepted, message, event = _manager.apply_action(game_id=game_id, player_id=payload.player_id, action=action, args=args)
    state = _manager.state(game_id)
    await _ws_hub.broadcast(
        game_id,
        {
            "type": "state.sync",
            "state": state.model_dump(mode="json"),
            "event": event.model_dump(mode="json") if event else None,
        },
    )
    return ActionResponse(accepted=accepted, message=message, state=state, event=event)


@router.post("/{game_id}/agent/{player_id}/act", response_model=ActionResponse)
async def agent_act_v2(game_id: str, player_id: str) -> ActionResponse:
    if not _manager.has_game(game_id):
        raise HTTPException(status_code=404, detail="unknown game")
    _manager.advance_to_decision_if_needed(game_id, player_id)
    state = _manager.state(game_id)
    if state.current_player_id != player_id:
        return ActionResponse(accepted=False, message="not current player", state=state)
    if state.current_phase != "DECISION":
        return ActionResponse(accepted=False, message="phase not decision", state=state)
    turn_input = _build_turn_input_v2(game_id)
    envelope = _runtime.decide(turn_input)
    accepted, message, event = _manager.apply_action(
        game_id=game_id,
        player_id=player_id,
        action=envelope.decision.action,
        args=envelope.decision.args,
        decision_audit=envelope,
    )
    state = _manager.state(game_id)
    await _ws_hub.broadcast(
        game_id,
        {
            "type": "state.sync",
            "state": state.model_dump(mode="json"),
            "event": event.model_dump(mode="json") if event else None,
            "audit": envelope.audit.model_dump(mode="json"),
        },
    )
    return ActionResponse(accepted=accepted, message=message, state=state, event=event, audit=envelope.audit)


@router.post("/start")
def create_game(payload: CreateGameRequest, request: Request) -> dict:
    if payload.game_id in _GAME_RUNTIME_STATE:
        raise HTTPException(status_code=400, detail="game already exists")
    if len(payload.player_ids) < 2:
        raise HTTPException(status_code=400, detail="at least 2 players required")
    _GAME_RUNTIME_STATE[payload.game_id] = initialize_game_state(
        game_id=payload.game_id,
        player_ids=payload.player_ids,
        start_cash=payload.start_cash,
        start_deposit=payload.start_deposit,
    )
    _upsert_game_state_to_db(_GAME_RUNTIME_STATE[payload.game_id])
    metrics.inc("game.start.count")
    log_json(
        "game.started",
        trace_id=getattr(request.state, "trace_id", ""),
        game_id=payload.game_id,
        players=payload.player_ids,
    )
    return {"ok": True, "game_id": payload.game_id, "players": payload.player_ids}


@router.post("/{game_id}/turn")
async def play_turn(game_id: str, payload: PlayTurnRequest, request: Request) -> dict:
    game = _GAME_RUNTIME_STATE.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail=ErrorCode.RESOURCE_NOT_FOUND.value)
    if payload.idempotency_key:
        cached = _load_idempotent("play_turn", game_id, payload.idempotency_key)
        if cached is not None:
            metrics.inc("idempotency.hit")
            return cached

    lock = _GAME_LOCKS[game_id]
    lock.acquire()
    start = time.perf_counter()
    try:
        command = ActionCommand(action=payload.action, params=payload.params)
        result = run_game_turn(
            game_state=game,
            player_id=payload.player_id,
            decision=command,
            dice_value=payload.dice_value,
        )
        replay_service.append_events(game_id, result.events)
        _upsert_game_state_to_db(game)
        _record_action(
            game_id=game_id,
            round_index=result.round_index,
            player_id=payload.player_id,
            turn_id=result.turn_id,
            action=payload.action.value,
            accepted=result.output_contract.accepted,
            message=result.output_contract.message,
            trace_id=getattr(request.state, "trace_id", ""),
        )
    finally:
        lock.release()

    ws_start = time.perf_counter()
    for event in result.events:
        await ws_manager.broadcast(game_id, event.model_dump())
    ws_latency_ms = (time.perf_counter() - ws_start) * 1000
    metrics.observe("ws.push.latency_ms", ws_latency_ms)
    metrics.observe("phase.turn.latency_ms", (time.perf_counter() - start) * 1000)
    if any(e.event_type == "action.rejected" for e in result.events):
        metrics.inc("action.reject.count")
    if result.output_contract.fallback_used:
        metrics.inc("fallback.count")
    command = ActionCommand(action=payload.action, params=payload.params)
    response = result.model_dump()
    if payload.idempotency_key:
        _save_idempotent("play_turn", game_id, payload.idempotency_key, response)
    log_json(
        "turn.played",
        trace_id=getattr(request.state, "trace_id", ""),
        game_id=game_id,
        round_index=result.round_index,
        turn_id=result.turn_id,
        player_id=payload.player_id,
        ws_clients=ws_manager.connection_count(game_id),
    )
    return response


@router.post("/action", response_model=ActionResponse)
def submit_action(payload: ActionRequest) -> ActionResponse:
    action = payload.action if isinstance(payload.action, ActionType) else ActionType(str(payload.action))
    turn_id = f"turn-{uuid.uuid4().hex[:8]}"
    turn_input = TurnInputV31(
        game_id=payload.game_id,
        player_id=payload.player_id,
        turn_id=turn_id,
        round_index=_GAME_RUNTIME_STATE.get(payload.game_id, {}).get("round_index", 1),
        phase=payload.phase,
        tile_type=TileType.EMPTY,
        command=ActionCommand(action=action, params=payload.params),
    )
    result = run_turn(turn_input)
    replay_service.append_events(payload.game_id, result.events)
    _GAME_RUNTIME_STATE[payload.game_id] = _GAME_RUNTIME_STATE.get(payload.game_id, {})
    _GAME_RUNTIME_STATE[payload.game_id]["round_index"] = result.round_index + (
        1 if result.phase == Phase.LOG else 0
    )
    _GAME_RUNTIME_STATE[payload.game_id]["phase"] = (
        result.next_phase.value if result.next_phase else Phase.ROLL.value
    )
    _GAME_RUNTIME_STATE[payload.game_id]["current_player_id"] = payload.player_id
    _GAME_RUNTIME_STATE[payload.game_id]["last_snapshot"] = result.snapshot.model_dump()
    return ActionResponse(
        accepted=result.output_contract.accepted,
        message=result.output_contract.message,
        error_code=result.output_contract.error_code,
    )


@router.post("/{game_id}/agent/act")
def agent_act(game_id: str, player_id: str) -> dict:
    allowed_actions = [ActionType.ROLL_DICE.value, ActionType.PASS.value]
    decision = decide_fallback(allowed_actions)
    return {
        "game_id": game_id,
        "player_id": player_id,
        "decision": decision.model_dump(),
    }


@router.get("/{game_id}/state")
def get_game_state(game_id: str) -> dict:
    if _manager.has_game(game_id):
        return {"state": _manager.state(game_id).model_dump(mode="json")}
    state = _GAME_RUNTIME_STATE.get(game_id)
    if not state:
        raise HTTPException(status_code=404, detail=ErrorCode.RESOURCE_NOT_FOUND.value)
    return state if isinstance(state, dict) else {"state": state}


@router.get("/{game_id}/replay")
def get_game_replay(
    game_id: str,
    start_round: int | None = Query(default=None),
    end_round: int | None = Query(default=None),
    event_type: str | None = Query(default=None),
) -> dict:
    if _manager.has_game(game_id):
        replay: ReplayResponse = _manager.replay(game_id)
        return replay.model_dump(mode="json")
    events = replay_service.get_events(
        game_id=game_id,
        start_round=start_round,
        end_round=end_round,
        event_type=event_type,
    )
    return {"game_id": game_id, "count": len(events), "events": [e.model_dump() for e in events]}


@router.get("/{game_id}/replay/export", response_class=PlainTextResponse)
def export_replay_jsonl(
    game_id: str,
    start_round: int | None = Query(default=None),
    end_round: int | None = Query(default=None),
    event_type: str | None = Query(default=None),
) -> str:
    return replay_service.export_events_jsonl(
        game_id=game_id,
        start_round=start_round,
        end_round=end_round,
        event_type=event_type,
    )


@router.get("/{game_id}/summary", response_model=ReplayExport)
def replay_summary_v2(game_id: str) -> ReplayExport:
    if not _manager.has_game(game_id):
        raise HTTPException(status_code=404, detail="unknown game")
    return _build_replay_export_v2(game_id)


@router.websocket("/{game_id}/ws")
async def game_ws_v2(game_id: str, socket: WebSocket) -> None:
    await _ws_hub.connect(game_id, socket)
    try:
        if _manager.has_game(game_id):
            state = _manager.state(game_id)
            await socket.send_json({"type": "state.sync", "state": state.model_dump(mode="json")})
        while True:
            text = await socket.receive_text()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                await socket.send_json({"type": "error", "message": "invalid json"})
                continue
            if payload.get("type") == "ping":
                await socket.send_json({"type": "pong"})
            elif payload.get("type") == "sync_request" and _manager.has_game(game_id):
                state = _manager.state(game_id)
                await socket.send_json({"type": "state.sync", "state": state.model_dump(mode="json")})
            else:
                await socket.send_json({"type": "error", "message": "unknown message type"})
    except WebSocketDisconnect:
        _ws_hub.disconnect(game_id, socket)
    finally:
        _ws_hub.disconnect(game_id, socket)


@router.get("/metrics")
def get_metrics() -> dict:
    return metrics.snapshot()
