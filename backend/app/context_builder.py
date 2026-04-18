from __future__ import annotations

from collections import deque
from functools import lru_cache
from typing import Any

from app.agent_memory import AgentMemoryStore
from app.game_engine import GameManager, GameSession, Player
from app.map_engine import load_map_definition
from app.schemas import (
    DynamicStateContext,
    LocalHorizonPaths,
    MemoryContext,
    RecentActionItem,
    StaticMapContext,
    StrategyProfile,
)


@lru_cache(maxsize=16)
def _cached_map_definition(map_asset: str) -> dict[str, Any]:
    return load_map_definition(map_asset=map_asset)


class AgentContextBuilder:
    def __init__(self, lookahead_steps: int = 6, recent_action_window: int = 3) -> None:
        self.lookahead_steps = lookahead_steps
        self.recent_action_window = recent_action_window

    def build(
        self,
        manager: GameManager,
        session: GameSession,
        current_player: Player,
        strategy_profile: StrategyProfile | None,
        memory: AgentMemoryStore,
    ) -> tuple[StaticMapContext, DynamicStateContext, list[RecentActionItem], MemoryContext]:
        static_map = self._build_static_map(session)
        dynamic_state = self._build_dynamic_state(manager, session, current_player)
        recent_actions = self._build_recent_actions(memory, session.game_id, current_player.player_id)
        memory_context = self._build_memory_context(memory, session.game_id, current_player.player_id, strategy_profile)
        return static_map, dynamic_state, recent_actions, memory_context

    def _build_static_map(self, session: GameSession) -> StaticMapContext:
        payload = _cached_map_definition(session.map_asset)
        meta = payload.get("meta", {})
        rows = payload.get("tiles", [])
        edges: list[dict[str, str]] = []
        for tile in rows:
            from_tile_id = str(tile.get("tile_id", ""))
            for next_id in list(tile.get("next_tile_ids") or []):
                edges.append({"from_tile_id": from_tile_id, "to_tile_id": str(next_id)})
        return StaticMapContext(
            map_id=str(meta.get("map_id", session.map_asset)),
            topology=str(meta.get("topology", "loop")),  # type: ignore[arg-type]
            track_length=int(meta.get("track_length", len(rows))),
            start_tile_id=str(meta.get("start_tile_id")) if meta.get("start_tile_id") else None,
            theme=str(meta.get("theme")) if meta.get("theme") else None,
            version=str(meta.get("version")) if meta.get("version") else None,
            tiles=[tile for tile in rows if isinstance(tile, dict)],
            edges=edges,
        )

    def _build_dynamic_state(self, manager: GameManager, session: GameSession, current_player: Player) -> DynamicStateContext:
        snapshots = manager.build_players_snapshot(session)
        current_snapshot = next((item for item in snapshots if item.player_id == current_player.player_id), None)
        horizon = manager.build_local_horizon_paths(session, current_player, lookahead=self.lookahead_steps)
        risk_hints = self._build_risk_hints(manager, session, current_player, horizon)
        turn_meta = manager.build_turn_meta(session).model_dump(mode="json")
        turn_meta["current_tile_id"] = session.active_tile_id
        turn_meta["current_tile_subtype"] = turn_meta.pop("tile_subtype", "")

        return DynamicStateContext(
            turn_meta=turn_meta,
            self_state=(current_snapshot.model_dump(mode="json") if current_snapshot else {}),
            others_state=[
                {
                    "player_id": item.player_id,
                    "position": item.position,
                    "net_worth": item.net_worth,
                    "alliance_with": item.alliance_with,
                    "alive": item.alive,
                }
                for item in snapshots
                if item.player_id != current_player.player_id
            ],
            risk_hints=risk_hints,
            local_horizon_paths=LocalHorizonPaths.model_validate(horizon),
        )

    def _build_risk_hints(
        self,
        manager: GameManager,
        session: GameSession,
        current_player: Player,
        horizon: dict[str, Any],
    ) -> dict[str, Any]:
        paths = horizon.get("paths", [])
        forward_tile_ids = {tile_id for path in paths for tile_id in path}
        high_toll = any(
            tile.tile_id in forward_tile_ids and (tile.toll or 0) >= 80
            for tile in session.board
        )
        return {
            "distance_to_nearest_bank": manager.distance_to_nearest_tile_type(
                session, current_player, target_tile_types={"BANK"}, lookahead=max(self.lookahead_steps, 12)
            ),
            "distance_to_nearest_event": manager.distance_to_nearest_tile_type(
                session, current_player, target_tile_types={"EVENT"}, lookahead=max(self.lookahead_steps, 12)
            ),
            "distance_to_nearest_enemy_property": self._distance_to_enemy_property(session, current_player),
            "projected_branch_count_6": len(paths),
            "high_toll_tile_in_6": high_toll,
        }

    def _distance_to_enemy_property(self, session: GameSession, current_player: Player) -> int | None:
        tile_by_id = {tile.tile_id: tile for tile in session.board}
        ordered_tiles = sorted(session.board, key=lambda item: item.tile_index)
        if not current_player.current_tile_id:
            current_player.current_tile_id = ordered_tiles[0].tile_id
        start_tile_id = current_player.current_tile_id
        queue: deque[tuple[str, int]] = deque([(start_tile_id, 0)])
        best_depth: dict[str, int] = {start_tile_id: 0}
        max_depth = max(self.lookahead_steps, 12)

        def next_ids_for(tile_id: str) -> list[str]:
            tile = tile_by_id.get(tile_id)
            if tile is None:
                return []
            if tile.next_tile_ids:
                return [next_id for next_id in tile.next_tile_ids if next_id in tile_by_id]
            idx = next((i for i, item in enumerate(ordered_tiles) if item.tile_id == tile_id), 0)
            return [ordered_tiles[(idx + 1) % len(ordered_tiles)].tile_id]

        while queue:
            tile_id, depth = queue.popleft()
            tile = tile_by_id[tile_id]
            if (
                depth > 0
                and tile.tile_type == "PROPERTY"
                and tile.owner_id is not None
                and tile.owner_id != current_player.player_id
                and tile.owner_id != current_player.alliance_with
            ):
                return depth
            if depth >= max_depth:
                continue
            for next_id in next_ids_for(tile_id):
                next_depth = depth + 1
                previous = best_depth.get(next_id)
                if previous is not None and previous <= next_depth:
                    continue
                best_depth[next_id] = next_depth
                queue.append((next_id, next_depth))
        return None

    def _build_recent_actions(self, memory: AgentMemoryStore, game_id: str, player_id: str) -> list[RecentActionItem]:
        rows = memory.recent_actions(game_id, player_id, limit=self.recent_action_window)
        return [RecentActionItem.model_validate(item) for item in rows]

    def _build_memory_context(
        self,
        memory: AgentMemoryStore,
        game_id: str,
        player_id: str,
        strategy_profile: StrategyProfile | None,
    ) -> MemoryContext:
        short_term_summary = memory.summary(game_id, player_id)
        long_term = memory.long_term_summary(player_id)
        if not long_term and strategy_profile:
            long_term = strategy_profile.summary
        return MemoryContext(
            short_term_summary=short_term_summary,
            long_term_summary=long_term,
            summary_version="v1",
        )
