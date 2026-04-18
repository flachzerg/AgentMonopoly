from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TURN_INPUT_VERSION = "DY-MONO-TURN-IN/3.1"
TURN_OUTPUT_VERSION = "DY-MONO-TURN-OUT/3.1"
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


class Phase(str, Enum):
    ROLL = "ROLL"
    TILE_ENTER = "TILE_ENTER"
    AUTO_SETTLE = "AUTO_SETTLE"
    DECISION = "DECISION"
    EXECUTE = "EXECUTE"
    LOG = "LOG"


class TileType(str, Enum):
    START = "START"
    EMPTY = "EMPTY"
    BANK = "BANK"
    EVENT = "EVENT"
    PROPERTY = "PROPERTY"
    QUIZ = "QUIZ"


class ActionType(str, Enum):
    ROLL_DICE = "roll_dice"
    BUY_PROPERTY = "buy_property"
    UPGRADE_PROPERTY = "upgrade_property"
    BANK_DEPOSIT = "bank_deposit"
    BANK_WITHDRAW = "bank_withdraw"
    EVENT_CHOICE = "event_choice"
    PROPOSE_ALLIANCE = "propose_alliance"
    ACCEPT_ALLIANCE = "accept_alliance"
    REJECT_ALLIANCE = "reject_alliance"
    PASS = "pass"


class ErrorCode(str, Enum):
    ILLEGAL_PHASE_TRANSITION = "ILLEGAL_PHASE_TRANSITION"
    ILLEGAL_ACTION_FOR_PHASE = "ILLEGAL_ACTION_FOR_PHASE"
    ILLEGAL_ACTION = "ILLEGAL_ACTION"
    INVALID_PARAMS = "INVALID_PARAMS"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"


class ActionCommand(BaseModel):
    action: ActionType
    params: dict = Field(default_factory=dict)


class DecisionOptions(BaseModel):
    phase: Phase
    allowed_actions: list[ActionType]


class OutputContract(BaseModel):
    # Legacy engine fields
    accepted: bool = True
    fallback_used: bool = False
    error_code: ErrorCode | None = None
    message: str = ""
    # Agent runtime fields
    protocol: Literal["DY-MONO-TURN-OUT/3.1"] = "DY-MONO-TURN-OUT/3.1"
    json_only: bool = True
    required_fields: list[str] = Field(default_factory=lambda: ["protocol", "action", "args"])
    reject_extra_fields: bool = True


class EventEnvelope(BaseModel):
    event_id: str
    game_id: str
    round_index: int
    turn_id: str
    phase: Phase
    event_type: str
    ts: float
    payload: dict = Field(default_factory=dict)


class PlayerSnapshot(BaseModel):
    player_id: str
    # Phase-B runtime fields
    name: str = ""
    is_agent: bool = True
    net_worth: int = 0
    property_ids: list[str] = Field(default_factory=list)
    alliance_with: str | None = None
    # Legacy engine fields
    position: int = 0
    cash: int = 1000
    deposit: int = 0
    alive: bool = True


class GameSnapshot(BaseModel):
    game_id: str
    round_index: int
    current_player_id: str
    phase: Phase
    tile_type: TileType = TileType.EMPTY
    players: list[PlayerSnapshot] = Field(default_factory=list)


class TurnInputV31(BaseModel):
    protocol_version: str = TURN_INPUT_VERSION
    game_id: str
    player_id: str
    turn_id: str = "turn-0"
    round_index: int = 1
    phase: Phase
    tile_type: TileType = TileType.EMPTY
    command: ActionCommand | None = None


class TurnOutputV31(BaseModel):
    protocol_version: str = TURN_OUTPUT_VERSION
    game_id: str
    player_id: str
    turn_id: str
    round_index: int
    phase: Phase
    next_phase: Phase | None = None
    decision_options: DecisionOptions | None = None
    output_contract: OutputContract
    events: list[EventEnvelope] = Field(default_factory=list)
    snapshot: GameSnapshot


class ActionRequest(BaseModel):
    game_id: str
    player_id: str
    phase: Phase = Phase.DECISION
    action: ActionType | str
    params: dict = Field(default_factory=dict)
    args: dict[str, Any] = Field(default_factory=dict)


class ActionResponse(BaseModel):
    accepted: bool
    message: str
    error_code: ErrorCode | None = None
    state: GameState | None = None
    event: EventRecord | None = None
    audit: DecisionAudit | None = None


class CreateGameRequest(BaseModel):
    game_id: str
    player_ids: list[str] = Field(default_factory=list)
    players: list[PlayerConfig] = Field(default_factory=list)
    start_cash: int = 1000
    start_deposit: int = 0
    max_rounds: int = Field(default=20, ge=1, le=200)
    seed: int = 20260418


class PlayTurnRequest(BaseModel):
    player_id: str
    action: ActionType = ActionType.PASS
    params: dict = Field(default_factory=dict)
    dice_value: int | None = None
    idempotency_key: str | None = None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionOption(StrictModel):
    action: str
    description: str
    required_args: list[str] = Field(default_factory=list)
    allowed_values: dict[str, list[Any]] = Field(default_factory=dict)
    default_args: dict[str, Any] = Field(default_factory=dict)


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
    protocol: Literal["DY-MONO-TURN-IN/3.1"] = "DY-MONO-TURN-IN/3.1"
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
    protocol: Literal["DY-MONO-TURN-OUT/3.1"] = "DY-MONO-TURN-OUT/3.1"
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
