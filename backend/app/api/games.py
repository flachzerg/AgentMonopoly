import json
import threading
import time
import uuid
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlmodel import delete, select

from app.agent_runtime import decide_fallback
from app.db import get_session
from app.game_engine import initialize_game_state, run_game_turn, run_turn
from app.models import Action, Alliance, Game, GameSnapshot, IdempotencyRecord, Player, Property
from app.observability import log_json, metrics
from app.replay_service import replay_service
from app.schemas import (
    ActionCommand,
    ActionRequest,
    ActionResponse,
    ActionType,
    CreateGameRequest,
    ErrorCode,
    Phase,
    PlayTurnRequest,
    TileType,
    TurnInputV31,
)
from app.ws_manager import ws_manager

router = APIRouter(prefix="/games", tags=["games"])
_GAME_RUNTIME_STATE: dict[str, dict] = {}
_GAME_LOCKS: dict[str, threading.Lock] = defaultdict(threading.Lock)


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
    turn_id = f"turn-{uuid.uuid4().hex[:8]}"
    turn_input = TurnInputV31(
        game_id=payload.game_id,
        player_id=payload.player_id,
        turn_id=turn_id,
        round_index=_GAME_RUNTIME_STATE.get(payload.game_id, {}).get("round_index", 1),
        phase=payload.phase,
        tile_type=TileType.EMPTY,
        command=ActionCommand(action=payload.action, params=payload.params),
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


@router.get("/metrics")
def get_metrics() -> dict:
    return metrics.snapshot()
