import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

from app.agent_runtime import AgentRuntime, RuntimeConfig, TurnBuildInput
from app.core.agent_options import load_agent_options
from app.game_engine import GameManager
from app.observability import log_json, metrics
from app.schemas import (
    ActionRequest,
    ActionResponse,
    ActionType,
    BoardSnapshot,
    CreateGameRequest,
    ReplayExport,
    ReplayResponse,
)
from app.ws_manager import ws_manager

router = APIRouter(prefix="/games", tags=["games"])
_manager = GameManager()
_agent_options = load_agent_options()
_THOUGHT_STREAM_MODE = os.getenv("THOUGHT_STREAM_MODE", "summary").strip().lower()
_THOUGHT_STREAM_DELAY_MS = max(0, int(os.getenv("THOUGHT_STREAM_DELAY_MS", "50")))
_THOUGHT_STREAM_MAX_LEN = max(0, int(os.getenv("THOUGHT_STREAM_MAX_LEN", "1024")))


def _runtime_for_player(game_id: str, player_id: str) -> AgentRuntime:
    session = _manager.get_game(game_id)
    player = next(item for item in session.players if item.player_id == player_id)
    cfg = player.agent_config
    default_cfg = RuntimeConfig(
        model_provider=_agent_options.provider,
        model_name=(_agent_options.model_options[0] if _agent_options.model_options else "qwen/qwen-plus-2025-07-28"),
        model_base_url=_agent_options.base_url,
        model_api_key=_agent_options.api_key,
        timeout_sec=_agent_options.default_timeout_sec,
        max_retries=_agent_options.default_max_retries,
    )
    if not cfg:
        return AgentRuntime(config=default_cfg)

    runtime_cfg = RuntimeConfig(
        model_provider=cfg.provider or default_cfg.model_provider,
        model_name=cfg.model or default_cfg.model_name,
        model_base_url=cfg.base_url or default_cfg.model_base_url,
        model_api_key=cfg.api_key or default_cfg.model_api_key,
        timeout_sec=cfg.timeout_sec or default_cfg.timeout_sec,
        max_retries=cfg.max_retries,
    )
    return AgentRuntime(config=runtime_cfg)


def _build_turn_input_v2(game_id: str, runtime: AgentRuntime):
    session = _manager.get_game(game_id)
    current = session.players[session.current_player_index]
    snapshots = _manager.build_players_snapshot(session)
    player_snapshot = next(item for item in snapshots if item.player_id == current.player_id)
    board_tiles = _manager.build_board_snapshot(session)
    topology = "graph" if any(len(item.next_tile_ids) > 1 for item in board_tiles) else "loop"
    payload = TurnBuildInput(
        turn_meta=_manager.build_turn_meta(session),
        tile_context=_manager.build_tile_context(session),
        player_state=player_snapshot,
        players_snapshot=snapshots,
        board_snapshot=BoardSnapshot(
            track_length=len(session.board),
            topology=topology,
            start_tile_id=next((item.tile_id for item in session.board if item.tile_type == "START"), session.board[0].tile_id),
            tiles=board_tiles,
        ),
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
    return runtime.build_turn_input(payload)


def _build_replay_export_v2(game_id: str) -> ReplayExport:
    session = _manager.get_game(game_id)
    replay = _manager.replay(game_id)
    total_turns = max(replay.total_turns, 1)
    fallback_turns = sum(1 for step in replay.steps if step.decision_audit and step.decision_audit.status == "fallback")
    illegal_actions = sum(
        1
        for event in session.events
        if event.type == "action.rejected" and event.payload.get("reason") in {"action_not_allowed", "invalid_args"}
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


async def _broadcast_state_sync(game_id: str, event: dict[str, Any] | None = None, audit: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {
        "type": "state.sync",
        "state": _manager.state(game_id).model_dump(mode="json"),
        "event": event,
    }
    if audit is not None:
        payload["audit"] = audit
    await ws_manager.broadcast(game_id, payload)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_thought_chunks(text: str, max_chunk_len: int = 18) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    current = ""
    punctuations = {",", ".", ";", "!", "?", "，", "。", "；", "！", "？"}
    for char in text:
        current += char
        if len(current) >= max_chunk_len or char in punctuations:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


def _normalized_thought(raw_thought: str | None) -> str:
    text = (raw_thought or "").strip()
    if _THOUGHT_STREAM_MAX_LEN and len(text) > _THOUGHT_STREAM_MAX_LEN:
        text = text[: _THOUGHT_STREAM_MAX_LEN - 3] + "..."
    if _THOUGHT_STREAM_MODE == "off":
        return ""
    if _THOUGHT_STREAM_MODE == "summary":
        return (text[:117] + "...") if len(text) > 120 else text
    return text


async def _stream_agent_thought(
    game_id: str,
    player_id: str,
    player_name: str,
    turn_index: int,
    thought: str,
) -> None:
    if not thought:
        return
    chunks = _split_thought_chunks(thought)
    if not chunks:
        return
    total = len(chunks)
    for idx, chunk in enumerate(chunks, start=1):
        await ws_manager.broadcast(
            game_id,
            {
                "type": "agent.thought.delta",
                "game_id": game_id,
                "player_id": player_id,
                "player_name": player_name,
                "turn_index": turn_index,
                "seq": idx,
                "delta": chunk,
                "is_final": idx == total,
                "ts": _now_iso(),
            },
        )
        if _THOUGHT_STREAM_DELAY_MS:
            await asyncio.sleep(_THOUGHT_STREAM_DELAY_MS / 1000)
    await ws_manager.broadcast(
        game_id,
        {
            "type": "agent.thought.done",
            "game_id": game_id,
            "player_id": player_id,
            "player_name": player_name,
            "turn_index": turn_index,
            "full_text": thought,
            "ts": _now_iso(),
        },
    )


async def _run_agent_turn_once(game_id: str, player_id: str) -> tuple[bool, str, ActionResponse]:
    _manager.advance_to_decision_if_needed(game_id, player_id)
    state = _manager.state(game_id)
    if state.current_player_id != player_id:
        return False, "not current player", ActionResponse(accepted=False, message="not current player", state=state)
    if state.current_phase != "DECISION":
        return False, "phase not decision", ActionResponse(accepted=False, message="phase not decision", state=state)

    runtime = _runtime_for_player(game_id, player_id)
    turn_input = _build_turn_input_v2(game_id, runtime)
    envelope = runtime.decide(turn_input)
    thought_text = _normalized_thought(envelope.decision.thought)
    session = _manager.get_game(game_id)
    current = next(item for item in session.players if item.player_id == player_id)
    player_name = current.name
    await _stream_agent_thought(
        game_id=game_id,
        player_id=player_id,
        player_name=player_name,
        turn_index=turn_input.turn_meta.turn_index,
        thought=thought_text,
    )
    accepted, message, event = _manager.apply_action(
        game_id=game_id,
        player_id=player_id,
        action=envelope.decision.action,
        args=envelope.decision.args,
        decision_audit=envelope,
    )
    state = _manager.state(game_id)
    await _broadcast_state_sync(
        game_id,
        event=event.model_dump(mode="json") if event else None,
        audit=envelope.audit.model_dump(mode="json"),
    )
    return accepted, message, ActionResponse(
        accepted=accepted,
        message=message,
        state=state,
        event=event,
        audit=envelope.audit,
    )


@router.post("", response_model=dict)
async def create_game_v2(payload: CreateGameRequest) -> dict[str, Any]:
    if not payload.players:
        raise HTTPException(status_code=400, detail="players is required")
    game_id = payload.game_id.strip()
    if not game_id:
        room_hint = (payload.room_name or "room").strip().replace(" ", "-").lower()
        game_id = f"{room_hint}-{uuid4().hex[:8]}"
    try:
        session = _manager.create_game(game_id, payload.players, payload.max_rounds, payload.seed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    state = _manager.state(session.game_id)
    await ws_manager.broadcast(session.game_id, {"type": "game.started", "state": state.model_dump(mode="json")})
    log_json("game.created", game_id=session.game_id, players=[item.player_id for item in payload.players])
    return {"game_id": session.game_id, "state": state.model_dump(mode="json")}


@router.get("", response_model=dict)
def list_games_v2() -> dict[str, Any]:
    return {"games": _manager.list_games()}


@router.get("/{game_id}/state", response_model=dict)
def get_game_state_v2(game_id: str) -> dict[str, Any]:
    if not _manager.has_game(game_id):
        raise HTTPException(status_code=404, detail="unknown game")
    return {"state": _manager.state(game_id).model_dump(mode="json")}


@router.post("/{game_id}/actions", response_model=ActionResponse)
async def submit_action_v2(game_id: str, payload: ActionRequest) -> ActionResponse:
    if payload.game_id != game_id:
        raise HTTPException(status_code=400, detail="game_id mismatch")
    if not _manager.has_game(game_id):
        raise HTTPException(status_code=404, detail="unknown game")

    action = payload.action.value if isinstance(payload.action, ActionType) else str(payload.action)
    accepted, message, event = _manager.apply_action(game_id=game_id, player_id=payload.player_id, action=action, args=payload.args)
    state = _manager.state(game_id)
    await _broadcast_state_sync(game_id, event=event.model_dump(mode="json") if event else None)
    metrics.inc("game.action.count")
    if not accepted:
        metrics.inc("game.action.rejected.count")
    return ActionResponse(accepted=accepted, message=message, state=state, event=event)


@router.post("/{game_id}/agent/{player_id}/act", response_model=ActionResponse)
async def agent_act_v2(game_id: str, player_id: str) -> ActionResponse:
    if not _manager.has_game(game_id):
        raise HTTPException(status_code=404, detail="unknown game")
    _, _, response = await _run_agent_turn_once(game_id, player_id)
    return response


@router.post("/{game_id}/auto-play", response_model=dict)
async def auto_play_agents_v2(
    game_id: str,
    max_steps: int = Query(default=16, ge=1, le=200),
) -> dict[str, Any]:
    if not _manager.has_game(game_id):
        raise HTTPException(status_code=404, detail="unknown game")

    steps = 0
    stopped_reason = "max_steps"
    audits: list[dict[str, Any]] = []

    while steps < max_steps:
        state = _manager.state(game_id)
        if state.status != "running":
            stopped_reason = "game_finished"
            break

        session = _manager.get_game(game_id)
        current_player = session.players[session.current_player_index]
        if not current_player.is_agent:
            stopped_reason = "human_turn"
            break

        accepted, message, response = await _run_agent_turn_once(game_id, current_player.player_id)
        steps += 1
        if response.audit is not None:
            audits.append(response.audit.model_dump(mode="json"))

        if not accepted:
            stopped_reason = f"blocked:{message}"
            break

    if steps == max_steps and stopped_reason == "max_steps":
        stopped_reason = "max_steps"

    final_state = _manager.state(game_id).model_dump(mode="json")
    return {
        "game_id": game_id,
        "steps": steps,
        "stopped_reason": stopped_reason,
        "state": final_state,
        "audits": audits[-8:],
    }


@router.get("/{game_id}/replay", response_model=ReplayResponse)
def get_game_replay_v2(game_id: str) -> ReplayResponse:
    if not _manager.has_game(game_id):
        raise HTTPException(status_code=404, detail="unknown game")
    return _manager.replay(game_id)


@router.get("/{game_id}/replay/export", response_class=PlainTextResponse)
def export_replay_jsonl_v2(
    game_id: str,
    start_round: int | None = Query(default=None),
    end_round: int | None = Query(default=None),
    event_type: str | None = Query(default=None),
) -> str:
    if not _manager.has_game(game_id):
        raise HTTPException(status_code=404, detail="unknown game")

    session = _manager.get_game(game_id)
    rows = session.events
    if start_round is not None:
        rows = [item for item in rows if item.round_index >= start_round]
    if end_round is not None:
        rows = [item for item in rows if item.round_index <= end_round]
    if event_type:
        rows = [item for item in rows if item.type == event_type]

    return "\n".join(json.dumps(item.model_dump(mode="json"), ensure_ascii=False) for item in rows)


@router.get("/{game_id}/summary", response_model=ReplayExport)
def replay_summary_v2(game_id: str) -> ReplayExport:
    if not _manager.has_game(game_id):
        raise HTTPException(status_code=404, detail="unknown game")
    return _build_replay_export_v2(game_id)


@router.websocket("/{game_id}/ws")
async def game_ws_v2(game_id: str, socket: WebSocket) -> None:
    await ws_manager.connect(game_id, socket)
    log_json("ws.connected", game_id=game_id, channel="/games/{game_id}/ws")
    try:
        if _manager.has_game(game_id):
            state = _manager.state(game_id)
            await socket.send_json({"type": "state.sync", "state": state.model_dump(mode="json")})
        else:
            await socket.send_json({"type": "error", "message": "unknown game"})

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
        ws_manager.disconnect(game_id, socket)
        log_json("ws.disconnected", game_id=game_id, channel="/games/{game_id}/ws")
    finally:
        ws_manager.disconnect(game_id, socket)


@router.get("/metrics")
def get_metrics() -> dict:
    return metrics.snapshot()


@router.get("/agent-options")
def get_agent_options() -> dict[str, Any]:
    return {
        "provider": _agent_options.provider,
        "base_url": _agent_options.base_url,
        "models_checked_at": _agent_options.models_checked_at,
        "model_options": _agent_options.model_options,
    }
