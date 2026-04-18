from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.agent_runtime import AgentRuntime, RuntimeConfig, TurnBuildInput
from app.game_engine import GameManager
from app.schemas import (
    ActionRequest,
    ActionResponse,
    BoardSnapshot,
    CreateGameRequest,
    ReplayExport,
    ReplayResponse,
)

router = APIRouter(prefix="/games", tags=["games"])


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
            except Exception:  # noqa: BLE001
                stale.append(socket)
        for socket in stale:
            self.disconnect(game_id, socket)


manager = GameManager()
runtime = AgentRuntime(config=RuntimeConfig())
ws_hub = WsHub()


def _build_turn_input(game_id: str):
    session = manager.get_game(game_id)
    current = session.players[session.current_player_index]
    snapshots = manager.build_players_snapshot(session)
    player_snapshot = next(item for item in snapshots if item.player_id == current.player_id)
    payload = TurnBuildInput(
        turn_meta=manager.build_turn_meta(session),
        tile_context=manager.build_tile_context(session),
        player_state=player_snapshot,
        players_snapshot=snapshots,
        board_snapshot=BoardSnapshot(
            track_length=len(session.board),
            tiles=manager.build_board_snapshot(session),
        ),
        options=session.allowed_actions,
    )
    return runtime.build_turn_input(payload)


def _build_replay_export(game_id: str) -> ReplayExport:
    session = manager.get_game(game_id)
    replay = manager.replay(game_id)
    total_turns = max(replay.total_turns, 1)

    fallback_turns = sum(
        1 for step in replay.steps if step.decision_audit and step.decision_audit.status == "fallback"
    )
    illegal_actions = sum(
        1
        for event in session.events
        if event.type == "action.rejected" and event.payload.get("reason") == "action_not_allowed"
    )
    net_worths = {player.player_id: player.net_worth for player in manager.state(game_id).players}

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

    metrics = {
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
        f"- total_turns: {int(metrics['total_turns'])}",
        f"- fallback_ratio: {metrics['fallback_ratio']:.3f}",
        f"- illegal_action_rate: {metrics['illegal_action_rate']:.3f}",
        f"- top_net_worth: {metrics['top_net_worth']:.1f}",
        f"- avg_net_worth: {metrics['avg_net_worth']:.1f}",
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
        metrics=metrics,
        strategy_timeline=strategy_timeline,
        markdown="\n".join(lines),
    )


@router.post("", response_model=dict)
async def create_game(payload: CreateGameRequest) -> dict[str, Any]:
    try:
        session = manager.create_game(payload.game_id, payload.players, payload.max_rounds, payload.seed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    state = manager.state(session.game_id)
    await ws_hub.broadcast(
        payload.game_id,
        {
            "type": "game.started",
            "state": state.model_dump(mode="json"),
        },
    )
    return {
        "game_id": payload.game_id,
        "state": state.model_dump(mode="json"),
    }


@router.get("", response_model=dict)
def list_games() -> dict[str, Any]:
    return {"games": manager.list_games()}


@router.get("/{game_id}/state", response_model=dict)
def get_state(game_id: str) -> dict[str, Any]:
    try:
        return {"state": manager.state(game_id).model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{game_id}/actions", response_model=ActionResponse)
async def submit_action(game_id: str, payload: ActionRequest) -> ActionResponse:
    if payload.game_id != game_id:
        raise HTTPException(status_code=400, detail="game_id mismatch")

    try:
        accepted, message, event = manager.apply_action(
            game_id=game_id,
            player_id=payload.player_id,
            action=payload.action,
            args=payload.args,
        )
        state = manager.state(game_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await ws_hub.broadcast(
        game_id,
        {
            "type": "state.sync",
            "state": state.model_dump(mode="json"),
            "event": event.model_dump(mode="json") if event else None,
        },
    )
    return ActionResponse(accepted=accepted, message=message, state=state, event=event)


@router.post("/{game_id}/agent/{player_id}/act", response_model=ActionResponse)
async def agent_act(game_id: str, player_id: str) -> ActionResponse:
    try:
        manager.advance_to_decision_if_needed(game_id, player_id)
        state = manager.state(game_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if state.current_player_id != player_id:
        return ActionResponse(accepted=False, message="not current player", state=state)

    if state.current_phase != "DECISION":
        return ActionResponse(accepted=False, message="phase not decision", state=state)

    turn_input = _build_turn_input(game_id)
    envelope = runtime.decide(turn_input)
    accepted, message, event = manager.apply_action(
        game_id=game_id,
        player_id=player_id,
        action=envelope.decision.action,
        args=envelope.decision.args,
        decision_audit=envelope,
    )
    state = manager.state(game_id)

    await ws_hub.broadcast(
        game_id,
        {
            "type": "state.sync",
            "state": state.model_dump(mode="json"),
            "event": event.model_dump(mode="json") if event else None,
            "audit": envelope.audit.model_dump(mode="json"),
        },
    )
    return ActionResponse(
        accepted=accepted,
        message=message,
        state=state,
        event=event,
        audit=envelope.audit,
    )


@router.get("/{game_id}/replay", response_model=ReplayResponse)
def replay(game_id: str) -> ReplayResponse:
    try:
        return manager.replay(game_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{game_id}/summary", response_model=ReplayExport)
def replay_summary(game_id: str) -> ReplayExport:
    try:
        return _build_replay_export(game_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.websocket("/{game_id}/ws")
async def game_ws(game_id: str, socket: WebSocket) -> None:
    await ws_hub.connect(game_id, socket)
    try:
        state = manager.state(game_id)
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
            elif payload.get("type") == "sync_request":
                state = manager.state(game_id)
                await socket.send_json({"type": "state.sync", "state": state.model_dump(mode="json")})
            else:
                await socket.send_json({"type": "error", "message": "unknown message type"})
    except KeyError:
        await socket.send_json({"type": "error", "message": "unknown game"})
    except WebSocketDisconnect:
        ws_hub.disconnect(game_id, socket)
    finally:
        ws_hub.disconnect(game_id, socket)


# legacy compatibility endpoints
@router.post("/action", response_model=ActionResponse)
async def legacy_submit_action(payload: ActionRequest) -> ActionResponse:
    return await submit_action(payload.game_id, payload)


@router.get("/{game_id}/agent/{player_id}")
async def legacy_agent_act(game_id: str, player_id: str) -> dict[str, Any]:
    result = await agent_act(game_id, player_id)
    return {
        "game_id": game_id,
        "player_id": player_id,
        "decision": result.audit.final_decision.model_dump(mode="json") if result.audit else None,
        "audit": result.audit.model_dump(mode="json") if result.audit else None,
        "accepted": result.accepted,
        "message": result.message,
    }
