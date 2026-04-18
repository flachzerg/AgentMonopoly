from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TURN_IN_PROTOCOL = "DY-MONO-TURN-IN/3.1"
TURN_OUT_PROTOCOL = "DY-MONO-TURN-OUT/3.1"
TURN_PHASE_CHAIN: tuple[str, ...] = (
    "ROLL",
    "TILE_ENTER",
    "AUTO_SETTLE",
    "DECISION",
    "EXECUTE",
    "LOG",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionOption(StrictModel):
    action: str
    description: str
    required_args: list[str] = Field(default_factory=list)
    allowed_values: dict[str, list[Any]] = Field(default_factory=dict)
    default_args: dict[str, Any] = Field(default_factory=dict)


class OutputContract(StrictModel):
    protocol: Literal["DY-MONO-TURN-OUT/3.1"] = TURN_OUT_PROTOCOL
    json_only: bool = True
    required_fields: list[str] = Field(default_factory=lambda: ["protocol", "action", "args"])
    reject_extra_fields: bool = True


class TurnMeta(StrictModel):
    game_id: str
    round_index: int
    turn_index: int
    phase: Literal["DECISION"] = "DECISION"
    chain: tuple[str, ...] = TURN_PHASE_CHAIN
    current_player_id: str
    tile_subtype: str


class TileContext(StrictModel):
    tile_id: str
    tile_index: int
    tile_type: str
    tile_subtype: str
    owner_id: str | None = None
    property_price: int | None = None
    toll: int | None = None
    event_key: str | None = None
    quiz_key: str | None = None


class PlayerSnapshot(StrictModel):
    player_id: str
    name: str
    is_agent: bool
    cash: int
    deposit: int
    net_worth: int
    position: int
    property_ids: list[str] = Field(default_factory=list)
    alliance_with: str | None = None
    alive: bool = True


class BoardTileSnapshot(StrictModel):
    tile_id: str
    tile_index: int
    tile_type: str
    tile_subtype: str
    owner_id: str | None = None
    property_price: int | None = None
    toll: int | None = None


class BoardSnapshot(StrictModel):
    track_length: int
    tiles: list[BoardTileSnapshot]


class TurnInput(StrictModel):
    protocol: Literal["DY-MONO-TURN-IN/3.1"] = TURN_IN_PROTOCOL
    turn_meta: TurnMeta
    tile_context: TileContext
    player_state: PlayerSnapshot
    players_snapshot: list[PlayerSnapshot]
    board_snapshot: BoardSnapshot
    history_records: list[dict[str, Any]] = Field(default_factory=list)
    options: list[ActionOption]
    output_contract: OutputContract
    template_key: str
    template_version: str
    memory_summary: str | None = None


class AgentTurnOutput(StrictModel):
    protocol: Literal["DY-MONO-TURN-OUT/3.1"] = TURN_OUT_PROTOCOL
    action: str
    args: dict[str, Any] = Field(default_factory=dict)
    thought: str | None = None
    strategy_tags: list[str] = Field(default_factory=list)
    candidate_actions: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class DecisionAudit(StrictModel):
    model_tag: str
    template_key: str
    template_version: str
    prompt_hash: str
    prompt_token_estimate: int
    attempt_count: int
    status: Literal["ok", "fallback"]
    failure_codes: list[str] = Field(default_factory=list)
    raw_response_summary: str = ""
    fallback_reason: str | None = None
    final_decision: AgentTurnOutput


class AgentDecisionEnvelope(StrictModel):
    decision: AgentTurnOutput
    audit: DecisionAudit


class PlayerConfig(StrictModel):
    player_id: str
    name: str
    is_agent: bool = True


class CreateGameRequest(StrictModel):
    game_id: str
    players: list[PlayerConfig]
    max_rounds: int = Field(default=20, ge=1, le=200)
    seed: int = 20260418


class ActionRequest(StrictModel):
    game_id: str
    player_id: str
    action: str
    args: dict[str, Any] = Field(default_factory=dict)


class ActionResponse(StrictModel):
    accepted: bool
    message: str
    state: GameState | None = None
    event: EventRecord | None = None
    audit: DecisionAudit | None = None


class TriggerAgentRequest(StrictModel):
    game_id: str
    player_id: str


class EventRecord(StrictModel):
    event_id: str
    ts: datetime
    type: str
    game_id: str
    round_index: int
    turn_index: int
    payload: dict[str, Any] = Field(default_factory=dict)


class TileState(StrictModel):
    tile_id: str
    tile_index: int
    tile_type: str
    tile_subtype: str
    name: str
    owner_id: str | None = None
    property_price: int | None = None
    toll: int | None = None


class GameState(StrictModel):
    game_id: str
    status: Literal["waiting", "running", "finished"]
    round_index: int
    turn_index: int
    max_rounds: int
    current_player_id: str
    current_phase: str
    active_tile_id: str
    players: list[PlayerSnapshot]
    board: list[TileState]
    allowed_actions: list[ActionOption]
    last_events: list[EventRecord]


class ReplayStep(StrictModel):
    turn_index: int
    round_index: int
    phase: str
    phase_trace: list[str] = Field(default_factory=list)
    state: GameState
    events: list[EventRecord]
    candidate_actions: list[str] = Field(default_factory=list)
    final_action: str | None = None
    strategy_tags: list[str] = Field(default_factory=list)
    decision_audit: DecisionAudit | None = None


class ReplayResponse(StrictModel):
    game_id: str
    total_turns: int
    steps: list[ReplayStep]


class ReplayExport(StrictModel):
    game_id: str
    generated_at: datetime
    metrics: dict[str, float]
    strategy_timeline: list[dict[str, Any]]
    markdown: str


class EvaluationResult(StrictModel):
    profile: str
    games: int
    win_rate: float
    avg_total_assets: float
    bankrupt_rate: float
    illegal_action_rate: float
    fallback_rate: float


class TemplateABReport(StrictModel):
    template_key: str
    baseline_version: str
    challenger_version: str
    baseline: EvaluationResult
    challenger: EvaluationResult
    delta: dict[str, float]


ActionResponse.model_rebuild()
