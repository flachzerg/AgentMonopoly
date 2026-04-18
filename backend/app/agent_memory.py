from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryEntry:
    turn_index: int
    action: str
    args: dict[str, object]
    strategy_tags: tuple[str, ...]
    thought: str
    target: str | None = None
    amount: int | None = None
    to: str | None = None
    result: str = "accepted"
    delta_cash: int = 0


class AgentMemoryStore:
    def __init__(self, max_entries: int = 6) -> None:
        self._max_entries = max_entries
        self._memory: dict[tuple[str, str], deque[MemoryEntry]] = defaultdict(
            lambda: deque(maxlen=max_entries)
        )
        self._long_term_summary: dict[str, str] = {}

    def summary(self, game_id: str, player_id: str) -> str:
        bucket = self._memory.get((game_id, player_id))
        if not bucket:
            return "No prior memory."
        chunks = []
        for item in bucket:
            tags = ",".join(item.strategy_tags) if item.strategy_tags else "none"
            chunks.append(
                f"turn={item.turn_index}; action={item.action}; tags={tags}; thought={item.thought}"
            )
        return " | ".join(chunks)

    def short_term_items(self, game_id: str, player_id: str, limit: int = 3) -> list[MemoryEntry]:
        bucket = self._memory.get((game_id, player_id))
        if not bucket:
            return []
        if limit <= 0:
            return []
        return list(bucket)[-limit:]

    def recent_actions(self, game_id: str, player_id: str, limit: int = 3) -> list[dict[str, object | None]]:
        rows: list[dict[str, object | None]] = []
        for item in self.short_term_items(game_id, player_id, limit=limit):
            rows.append(
                {
                    "turn": item.turn_index,
                    "action": item.action.upper(),
                    "target": item.target,
                    "thought": item.thought,
                    "amount": item.amount,
                    "to": item.to,
                    "result": item.result,
                    "delta_cash": item.delta_cash,
                }
            )
        return rows

    def update_long_term_summary(self, player_id: str, summary: str) -> None:
        text = summary.strip()
        if not text:
            return
        self._long_term_summary[player_id] = text[:600]

    def long_term_summary(self, player_id: str) -> str:
        return self._long_term_summary.get(player_id, "")

    def record(
        self,
        game_id: str,
        player_id: str,
        turn_index: int,
        action: str,
        args: dict[str, object] | None,
        strategy_tags: list[str],
        thought: str,
        target: str | None = None,
        amount: int | None = None,
        to: str | None = None,
        result: str = "accepted",
        delta_cash: int = 0,
    ) -> None:
        self._memory[(game_id, player_id)].append(
            MemoryEntry(
                turn_index=turn_index,
                action=action,
                args=dict(args or {}),
                strategy_tags=tuple(strategy_tags),
                thought=thought[:300],
                target=target,
                amount=amount,
                to=to,
                result=result,
                delta_cash=delta_cash,
            )
        )
