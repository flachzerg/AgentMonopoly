from __future__ import annotations

import time
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class Game(SQLModel, table=True):
    id: str = Field(primary_key=True)
    round_index: int = 1
    current_player_id: str
    phase: str = "ROLL"
    status: str = "active"


class Player(SQLModel, table=True):
    id: str = Field(primary_key=True)
    game_id: str = Field(index=True)
    name: str
    position: int = 0
    cash: int = 1000
    deposit: int = 0
    alive: bool = True


class Property(SQLModel, table=True):
    id: str = Field(primary_key=True)
    game_id: str = Field(index=True)
    position: int
    owner_id: Optional[str] = None
    level: int = 0


class Alliance(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: str = Field(index=True)
    player_a_id: str
    player_b_id: str
    active: bool = True


class Action(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: str = Field(index=True)
    round_index: int = Field(index=True)
    player_id: str = Field(index=True)
    turn_id: str = Field(index=True)
    action: str
    accepted: bool
    message: str
    trace_id: str = ""
    ts: float = Field(default_factory=time.time, index=True)

    __table_args__ = (Index("idx_action_game_player_round", "game_id", "player_id", "round_index"),)


class EventLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: str = Field(index=True)
    round_index: int = Field(index=True)
    turn_id: str = Field(index=True)
    event_type: str = Field(index=True)
    payload_json: str
    ts: float = Field(default_factory=time.time, index=True)

    __table_args__ = (
        Index("idx_event_game_round", "game_id", "round_index"),
        Index("idx_event_game_ts", "game_id", "ts"),
    )


class GameSnapshot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: str = Field(index=True)
    round_index: int = Field(index=True)
    snapshot_json: str
    ts: float = Field(default_factory=time.time, index=True)

    __table_args__ = (
        Index("idx_snapshot_game_round", "game_id", "round_index"),
        Index("idx_snapshot_game_ts", "game_id", "ts"),
    )


class IdempotencyRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: str = Field(index=True)
    endpoint: str = Field(index=True)
    key: str = Field(index=True)
    response_json: str
    ts: float = Field(default_factory=time.time, index=True)
