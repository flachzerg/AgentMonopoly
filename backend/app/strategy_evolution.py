from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas import GameState, StrategyProfile, StrategyVersionRecord


def _next_version(version: str) -> str:
    try:
        major, minor, patch = version.replace("strategy-v", "").split(".")
        return f"strategy-v{major}.{minor}.{int(patch) + 1}"
    except Exception:  # noqa: BLE001
        return "strategy-v1.0.1"


def _recommend_profile(player: Any, game_id: str, previous: StrategyProfile | None) -> StrategyProfile:
    base = previous or StrategyProfile(
        player_id=player.player_id,
        updated_at=datetime.now(timezone.utc),
    )
    next_version = _next_version(base.version)
    risk = "medium"
    alliance = "medium"
    liquidity = base.liquidity_floor
    summary_parts = ["局后策略更新："]
    if not player.alive:
        risk = "low"
        alliance = "high"
        liquidity = max(base.liquidity_floor, 500)
        summary_parts.append("上局发生破产，本局先保资金安全垫。")
    elif player.net_worth >= 2800:
        risk = "high"
        alliance = "low"
        liquidity = max(250, base.liquidity_floor - 80)
        summary_parts.append("上局资产领先，本局允许更积极扩张。")
    else:
        risk = "medium"
        alliance = "medium"
        liquidity = max(320, base.liquidity_floor)
        summary_parts.append("上局表现中位，维持均衡打法。")
    return StrategyProfile(
        player_id=player.player_id,
        version=next_version,
        summary="".join(summary_parts),
        risk_appetite=risk,  # type: ignore[arg-type]
        alliance_preference=alliance,  # type: ignore[arg-type]
        liquidity_floor=liquidity,
        updated_at=datetime.now(timezone.utc),
        source_game_id=game_id,
    )


class StrategyEvolutionManager:
    def __init__(self) -> None:
        self._profiles: dict[str, StrategyProfile] = {}
        self._history: list[StrategyVersionRecord] = []

    def profile_for_player(self, player_id: str) -> StrategyProfile | None:
        return self._profiles.get(player_id)

    def snapshot(self) -> list[StrategyVersionRecord]:
        return list(self._history)

    def evolve_from_game(self, game_id: str, state: GameState) -> list[StrategyProfile]:
        updated: list[StrategyProfile] = []
        for player in state.players:
            if not player.is_agent:
                continue
            previous = self._profiles.get(player.player_id)
            next_profile = _recommend_profile(player, game_id, previous)
            self._profiles[player.player_id] = next_profile
            self._history.append(
                StrategyVersionRecord(
                    player_id=player.player_id,
                    version=next_profile.version,
                    summary=next_profile.summary,
                    updated_at=next_profile.updated_at,
                    source_game_id=game_id,
                )
            )
            updated.append(next_profile)
        return updated
