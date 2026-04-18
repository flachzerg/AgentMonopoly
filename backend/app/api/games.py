import json
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

from app.agent_runtime import AgentRuntime, RuntimeConfig, TurnBuildInput
from app.core.agent_options import load_agent_options
from app.game_engine import GameManager
from app.map_engine import default_map_path, list_map_paths, map_asset_from_path
from app.model_experience import ModelExperienceStore, build_experience_summary
from app.observability import log_json, metrics
from app.replay_summary import build_replay_export
from app.schemas import (
    ActionRequest,
    ActionResponse,
    ActionType,
    BoardSnapshot,
    CreateGameRequest,
    ReplayExport,
    ReplayResponse,
    ModelExperienceResponse,
    StrategyVersionRecord,
    StrategyVersionsResponse,
)
from app.strategy_evolution import StrategyEvolutionManager
from app.ws_manager import ws_manager

router = APIRouter(prefix="/games", tags=["games"])
_manager = GameManager()
_agent_options = load_agent_options()
_strategy_manager = StrategyEvolutionManager()
_experience_store = ModelExperienceStore()
_summary_cache: dict[str, ReplayExport] = {}
_evolved_games: set[str] = set()


@dataclass
class AutoAdvanceResult:
    steps: int
    stopped_reason: str
    audits: list[dict[str, Any]]


def _map_assets_catalog() -> tuple[list[str], str]:
    assets = [map_asset_from_path(path) for path in list_map_paths()]
    default_asset = map_asset_from_path(default_map_path())
    if default_asset not in assets:
        assets = [default_asset, *assets]
    return assets, default_asset


def _split_thought_chunks(thought: str, max_chunk_len: int = 28) -> list[str]:
    if max_chunk_len < 1:
        raise ValueError("max_chunk_len must be positive")
    if not thought:
        return []
    text = thought.strip()
    if not text:
        return []

    chunks: list[str] = []
    segments = re.split(r"([，。！？；,.!?;])", text)
    cursor = ""
    for segment in segments:
        if not segment:
            continue
        piece = f"{cursor}{segment}"
        if len(piece) <= max_chunk_len:
            cursor = piece
            continue
        if cursor:
            chunks.append(cursor)
            cursor = ""
        for idx in range(0, len(segment), max_chunk_len):
            part = segment[idx : idx + max_chunk_len]
            if len(part) == max_chunk_len:
                chunks.append(part)
            else:
                cursor = part
    if cursor:
        chunks.append(cursor)
    return chunks if chunks else [text]


async def _broadcast_thought_pseudo_stream(
    game_id: str,
    player_id: str,
    player_name: str,
    turn_index: int,
    thought: str,
) -> None:
    chunks = _split_thought_chunks(thought)
    if not chunks:
        return
    now = datetime.now(timezone.utc).isoformat()
    for seq, delta in enumerate(chunks, start=1):
        await ws_manager.broadcast(
            game_id,
            {
                "type": "agent.thought.delta",
                "game_id": game_id,
                "player_id": player_id,
                "player_name": player_name,
                "turn_index": turn_index,
                "seq": seq,
                "delta": delta,
                "ts": now,
            },
        )
    await ws_manager.broadcast(
        game_id,
        {
            "type": "agent.thought.done",
            "game_id": game_id,
            "player_id": player_id,
            "player_name": player_name,
            "turn_index": turn_index,
            "is_final": True,
            "full_text": thought,
            "ts": now,
        },
    )


def _resolve_runtime_config(game_id: str, player_id: str) -> RuntimeConfig:
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
    if default_cfg.model_provider == "openai-compatible" and not default_cfg.model_api_key:
        default_cfg = RuntimeConfig(
            model_provider="heuristic",
            model_name="heuristic",
            model_base_url=default_cfg.model_base_url,
            model_api_key="",
            timeout_sec=default_cfg.timeout_sec,
            max_retries=default_cfg.max_retries,
        )
    if not cfg:
        return default_cfg

    runtime_cfg = RuntimeConfig(
        model_provider=cfg.provider or default_cfg.model_provider,
        model_name=cfg.model or default_cfg.model_name,
        model_base_url=cfg.base_url or default_cfg.model_base_url,
        model_api_key=cfg.api_key or default_cfg.model_api_key,
        timeout_sec=cfg.timeout_sec or default_cfg.timeout_sec,
        max_retries=cfg.max_retries,
    )
    if runtime_cfg.model_provider == "openai-compatible" and not runtime_cfg.model_api_key:
        runtime_cfg = RuntimeConfig(
            model_provider="heuristic",
            model_name="heuristic",
            model_base_url=runtime_cfg.model_base_url,
            model_api_key="",
            timeout_sec=runtime_cfg.timeout_sec,
            max_retries=runtime_cfg.max_retries,
        )
    return runtime_cfg


def _runtime_for_player(game_id: str, player_id: str) -> AgentRuntime:
    return AgentRuntime(config=_resolve_runtime_config(game_id, player_id))


def _build_turn_input_v2(game_id: str, runtime: AgentRuntime):
    session = _manager.get_game(game_id)
    current = session.players[session.current_player_index]
    runtime_cfg = _resolve_runtime_config(game_id, current.player_id)
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
            for item in session.events[-30:]
        ],
        model_experience_summary=_experience_store.context_for_model(runtime_cfg.model_name),
        strategy_profile=_strategy_manager.profile_for_player(current.player_id),
    )
    return runtime.build_turn_input(payload)


def _build_strategy_timeline(game_id: str) -> list[dict[str, Any]]:
    replay = _manager.replay(game_id)
    return [
        {
            "turn_index": step.turn_index,
            "round_index": step.round_index,
            "final_action": step.final_action,
            "candidate_actions": step.candidate_actions,
            "strategy_tags": step.strategy_tags,
            "phase_trace": step.phase_trace,
            "decision_audit": step.decision_audit.model_dump(mode="json") if step.decision_audit else None,
        }
        for step in replay.steps
    ]


def _build_replay_export_v2(game_id: str) -> ReplayExport:
    state = _manager.state(game_id)
    replay = _manager.replay(game_id)
    session = _manager.get_game(game_id)
    strategy_timeline = _build_strategy_timeline(game_id)
    export = build_replay_export(
        game_id=game_id,
        state=state,
        replay=replay,
        events=session.events,
        strategy_timeline=strategy_timeline,
    )
    total_turns = max(replay.total_turns, 1)
    fallback_turns = sum(1 for step in replay.steps if step.decision_audit and step.decision_audit.status == "fallback")
    illegal_actions = sum(
        1
        for event in session.events
        if event.type == "action.rejected" and event.payload.get("reason") in {"action_not_allowed", "invalid_args"}
    )
    top_net_worth = max((item.net_worth for item in state.players), default=0)
    export.metrics.update(
        {
            "fallback_ratio": fallback_turns / total_turns,
            "illegal_action_rate": illegal_actions / total_turns,
            "top_net_worth": float(top_net_worth),
        }
    )
    return export


def _finalize_if_needed(game_id: str) -> None:
    state = _manager.state(game_id)
    if state.status != "finished":
        return

    if game_id not in _summary_cache:
        _summary_cache[game_id] = _build_replay_export_v2(game_id)

    if game_id in _evolved_games:
        return
    _strategy_manager.evolve_from_game(game_id, state)
    _evolve_model_experience(game_id, state)
    _evolved_games.add(game_id)


def _evolve_model_experience(game_id: str, state) -> None:
    session = _manager.get_game(game_id)
    bankrupt_count = sum(1 for item in state.players if not item.alive)
    winner = max(state.players, key=lambda item: item.net_worth).player_id if state.players else "unknown"
    materials = {
        "game_id": game_id,
        "winner": winner,
        "total_turns": state.turn_index,
        "bankrupt_count": bankrupt_count,
        "last_events": [
            {
                "type": item.type,
                "turn_index": item.turn_index,
                "round_index": item.round_index,
                "payload": item.payload,
            }
            for item in session.events[-50:]
        ],
    }
    done_models: set[str] = set()
    for player in session.players:
        if not player.is_agent:
            continue
        runtime_cfg = _resolve_runtime_config(game_id, player.player_id)
        model_id = runtime_cfg.model_name
        if model_id in done_models:
            continue
        done_models.add(model_id)
        summary = build_experience_summary(runtime_cfg, materials)
        _experience_store.add_record(
            model_id=model_id,
            provider=runtime_cfg.model_provider,
            game_id=game_id,
            summary=summary,
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


def _human_wait_reason(game_id: str) -> str:
    state = _manager.state(game_id)
    if state.status != "running":
        return "game_finished"
    if state.waiting_for_human:
        if state.human_wait_reason == "roll_dice":
            return "waiting_human_roll"
        if state.human_wait_reason == "branch_decision":
            return "waiting_human_branch_decision"
    return "none"


async def _run_model_decision_once(game_id: str, player_id: str, allow_hidden_human_actions: bool) -> tuple[bool, str, ActionResponse]:
    _manager.advance_to_decision_if_needed(game_id, player_id)
    state = _manager.state(game_id)
    if state.current_player_id != player_id:
        return False, "not current player", ActionResponse(accepted=False, message="not current player", state=state)
    if state.current_phase != "DECISION":
        return False, "phase not decision", ActionResponse(accepted=False, message="phase not decision", state=state)

    runtime = _runtime_for_player(game_id, player_id)
    turn_input = _build_turn_input_v2(game_id, runtime)
    envelope = runtime.decide(turn_input)
    session = _manager.get_game(game_id)
    player = next((item for item in session.players if item.player_id == player_id), None)
    player_name = player.name if player else player_id
    await _broadcast_thought_pseudo_stream(
        game_id=game_id,
        player_id=player_id,
        player_name=player_name,
        turn_index=turn_input.turn_meta.turn_index,
        thought=envelope.decision.thought,
    )
    accepted, message, event = _manager.apply_action(
        game_id=game_id,
        player_id=player_id,
        action=envelope.decision.action,
        args=envelope.decision.args,
        decision_audit=envelope,
        enforce_human_restrictions=not allow_hidden_human_actions,
    )
    _finalize_if_needed(game_id)
    await _broadcast_state_sync(
        game_id,
        event=event.model_dump(mode="json") if event else None,
        audit=envelope.audit.model_dump(mode="json"),
    )
    return accepted, message, ActionResponse(
        accepted=accepted,
        message=message,
        state=_manager.state(game_id),
        event=event,
        audit=envelope.audit,
    )


async def _auto_advance_until_human(game_id: str, max_steps: int = 120) -> AutoAdvanceResult:
    steps = 0
    audits: list[dict[str, Any]] = []
    stopped_reason = "max_steps"

    while steps < max_steps:
        state = _manager.state(game_id)
        if state.status != "running":
            stopped_reason = "game_finished"
            break

        wait_reason = _human_wait_reason(game_id)
        if wait_reason != "none":
            stopped_reason = wait_reason
            break

        session = _manager.get_game(game_id)
        current_player = session.players[session.current_player_index]

        accepted, message, response = await _run_model_decision_once(
            game_id=game_id,
            player_id=current_player.player_id,
            allow_hidden_human_actions=not current_player.is_agent,
        )
        steps += 1
        if response.audit is not None:
            audits.append(response.audit.model_dump(mode="json"))

        if not accepted:
            stopped_reason = f"blocked:{message}"
            break

    if steps >= max_steps and stopped_reason == "max_steps":
        stopped_reason = "max_steps"

    _finalize_if_needed(game_id)
    return AutoAdvanceResult(steps=steps, stopped_reason=stopped_reason, audits=audits)


@router.post("", response_model=dict)
async def create_game_v2(payload: CreateGameRequest) -> dict[str, Any]:
    if not payload.players:
        raise HTTPException(status_code=400, detail="players is required")
    game_id = payload.game_id.strip()
    if not game_id:
        room_hint = (payload.room_name or "room").strip().replace(" ", "-").lower()
        game_id = f"{room_hint}-{uuid4().hex[:8]}"
    requested_map_asset = (payload.map_asset or payload.map_theme or "").strip() or None
    try:
        session = _manager.create_game(game_id, payload.players, payload.max_rounds, payload.seed, map_asset=requested_map_asset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    auto = await _auto_advance_until_human(session.game_id)
    state = _manager.state(session.game_id)
    await ws_manager.broadcast(session.game_id, {"type": "game.started", "state": state.model_dump(mode="json")})
    log_json("game.created", game_id=session.game_id, players=[item.player_id for item in payload.players])
    return {
        "game_id": session.game_id,
        "state": state.model_dump(mode="json"),
        "auto_advanced_steps": auto.steps,
        "stopped_reason": auto.stopped_reason,
    }


@router.get("", response_model=dict)
def list_games_v2() -> dict[str, Any]:
    return {"games": _manager.list_games()}


@router.get("/map-options", response_model=dict)
def get_map_options() -> dict[str, Any]:
    map_assets, default_asset = _map_assets_catalog()
    return {
        "map_assets": map_assets,
        "default_map_asset": default_asset,
    }


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
    await _broadcast_state_sync(game_id, event=event.model_dump(mode="json") if event else None)
    metrics.inc("game.action.count")
    if not accepted:
        metrics.inc("game.action.rejected.count")
        return ActionResponse(accepted=accepted, message=message, state=_manager.state(game_id), event=event)

    auto = await _auto_advance_until_human(game_id)
    wait_reason = _human_wait_reason(game_id)
    next_message = auto.stopped_reason if auto.stopped_reason != "max_steps" else wait_reason
    if next_message == "none":
        next_message = "state_updated"
    return ActionResponse(accepted=True, message=next_message, state=_manager.state(game_id), event=event)


@router.post("/{game_id}/agent/{player_id}/act", response_model=ActionResponse)
async def agent_act_v2(game_id: str, player_id: str) -> ActionResponse:
    if not _manager.has_game(game_id):
        raise HTTPException(status_code=404, detail="unknown game")
    _, _, response = await _run_model_decision_once(game_id, player_id, allow_hidden_human_actions=False)
    auto = await _auto_advance_until_human(game_id)
    response.message = auto.stopped_reason
    response.state = _manager.state(game_id)
    return response


@router.post("/{game_id}/auto-play", response_model=dict)
async def auto_play_agents_v2(
    game_id: str,
    max_steps: int = Query(default=16, ge=1, le=200),
) -> dict[str, Any]:
    if not _manager.has_game(game_id):
        raise HTTPException(status_code=404, detail="unknown game")

    result = await _auto_advance_until_human(game_id, max_steps=max_steps)
    final_state = _manager.state(game_id).model_dump(mode="json")
    return {
        "game_id": game_id,
        "steps": result.steps,
        "stopped_reason": result.stopped_reason,
        "state": final_state,
        "audits": result.audits[-8:],
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
    _finalize_if_needed(game_id)
    if game_id not in _summary_cache:
        _summary_cache[game_id] = _build_replay_export_v2(game_id)
    return _summary_cache[game_id]


@router.get("/strategy/versions", response_model=StrategyVersionsResponse)
def strategy_versions_v2() -> StrategyVersionsResponse:
    records: list[StrategyVersionRecord] = _strategy_manager.snapshot()
    return StrategyVersionsResponse(records=records)


@router.get("/model-experiences", response_model=ModelExperienceResponse)
def model_experiences_v2(model_id: str | None = Query(default=None), limit: int = Query(default=50, ge=1, le=500)) -> ModelExperienceResponse:
    return ModelExperienceResponse(records=_experience_store.list_records(model_id=model_id, limit=limit))


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
