from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryEntry:
    turn_index: int
    action: str
    strategy_tags: tuple[str, ...]
    note: str


class AgentMemoryStore:
    def __init__(self, max_entries: int = 6) -> None:
        self._max_entries = max_entries
        self._memory: dict[tuple[str, str], deque[MemoryEntry]] = defaultdict(
            lambda: deque(maxlen=max_entries)
        )

    def summary(self, game_id: str, player_id: str) -> str:
        bucket = self._memory.get((game_id, player_id))
        if not bucket:
            return "No prior memory."
        chunks = []
        for item in bucket:
            tags = ",".join(item.strategy_tags) if item.strategy_tags else "none"
            chunks.append(
                f"turn={item.turn_index}; action={item.action}; tags={tags}; note={item.note}"
            )
        return " | ".join(chunks)

    def record(
        self,
        game_id: str,
        player_id: str,
        turn_index: int,
        action: str,
        strategy_tags: list[str],
        note: str,
    ) -> None:
        self._memory[(game_id, player_id)].append(
            MemoryEntry(
                turn_index=turn_index,
                action=action,
                strategy_tags=tuple(strategy_tags),
                note=note[:120],
            )
        )
