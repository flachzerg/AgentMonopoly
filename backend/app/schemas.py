from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TURN_IN_PROTOCOL: Literal["DY-MONO-TURN-IN/3.1"] = "DY-MONO-TURN-IN/3.1"
TURN_OUT_PROTOCOL: Literal["DY-MONO-TURN-OUT/3.1"] = "DY-MONO-TURN-OUT/3.1"
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
    SET_ROUTE_PREFERENCE = "set_route_preference"
    PASS = "pass"


class ErrorCode(str, Enum):
    ILLEGAL_ACTION = "ILLEGAL_ACTION"
    INVALID_PARAMS = "INVALID_PARAMS"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"


class OutputContract(BaseModel):
    accepted: bool = True
    fallback_used: bool = False
    error_code: ErrorCode | None = None
    message: str = ""
    protocol: Literal["DY-MONO-TURN-OUT/3.1"] = TURN_OUT_PROTOCOL
    json_only: bool = True
    required_fields: list[str] = Field(default_factory=lambda: ["protocol", "action", "args", "thought"])
    reject_extra_fields: bool = True


class PlayerSnapshot(BaseModel):
    player_id: str
    name: str = ""
    is_agent: bool = True
    net_worth: int = 0
    property_ids: list[str] = Field(default_factory=list)
    alliance_with: str | None = None
    position: int = 0
    current_tile_id: str | None = None
    route_preference_tile_id: str | None = None
    cash: int = 1000
    deposit: int = 0
    alive: bool = True


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrategyProfile(StrictModel):
    player_id: str
    version: str = "strategy-v1.0.0"
    summary: str = "初始策略：稳健现金流与低风险扩张。"
    risk_appetite: Literal["low", "medium", "high"] = "medium"
    alliance_preference: Literal["low", "medium", "high"] = "medium"
    liquidity_floor: int = 350
    updated_at: datetime
    source_game_id: str | None = None


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
    next_tile_ids: list[str] = Field(default_factory=list)
    branch_options: list[str] = Field(default_factory=list)


class BoardTileSnapshot(StrictModel):
    tile_id: str
    tile_index: int
    tile_type: str
    tile_subtype: str
    owner_id: str | None = None
    property_price: int | None = None
    toll: int | None = None
    next_tile_ids: list[str] = Field(default_factory=list)


class BoardSnapshot(StrictModel):
    track_length: int
    topology: Literal["loop", "graph"] = "loop"
    start_tile_id: str | None = None
    tiles: list[BoardTileSnapshot]


class StaticMapContext(StrictModel):
    map_id: str = "unknown"
    topology: Literal["loop", "graph"] = "loop"
    track_length: int = 0
    start_tile_id: str | None = None
    theme: str | None = None
    version: str | None = None
    tiles: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, str]] = Field(default_factory=list)


class LocalHorizonPaths(StrictModel):
    lookahead_steps: int = 6
    branch_entry_tile_id: str | None = None
    paths: list[list[str]] = Field(default_factory=list)


class DynamicStateContext(StrictModel):
    turn_meta: dict[str, Any] = Field(default_factory=dict)
    self_state: dict[str, Any] = Field(default_factory=dict)
    others_state: list[dict[str, Any]] = Field(default_factory=list)
    risk_hints: dict[str, Any] = Field(default_factory=dict)
    local_horizon_paths: LocalHorizonPaths = Field(default_factory=LocalHorizonPaths)


class RecentActionItem(StrictModel):
    turn: int
    action: str
    target: str | None = None
    thought: str | None = None
    amount: int | None = None
    to: str | None = None
    result: str = "accepted"
    delta_cash: int = 0


class MemoryContext(StrictModel):
    short_term_summary: str = ""
    long_term_summary: str = ""
    summary_version: str = "v1"


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
    model_experience_summary: str | None = None
    strategy_profile: StrategyProfile | None = None
    static_map: StaticMapContext = Field(default_factory=StaticMapContext)
    dynamic_state: DynamicStateContext = Field(default_factory=DynamicStateContext)
    recent_actions_3turns: list[RecentActionItem] = Field(default_factory=list)
    memory_context: MemoryContext = Field(default_factory=MemoryContext)


class AgentTurnOutput(StrictModel):
    protocol: Literal["DY-MONO-TURN-OUT/3.1"] = TURN_OUT_PROTOCOL
    action: str
    args: dict[str, Any] = Field(default_factory=dict)
    thought: str = Field(min_length=1, max_length=2000)
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


class AgentConfig(StrictModel):
    provider: str = "openai-compatible"
    model: str = "qwen/qwen-plus-2025-07-28"
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str = ""
    timeout_sec: float = Field(default=8, gt=0.5, le=60)
    max_retries: int = Field(default=2, ge=0, le=5)


class PlayerConfig(StrictModel):
    player_id: str
    name: str
    is_agent: bool = True
    agent_config: AgentConfig | None = None


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
    next_tile_ids: list[str] = Field(default_factory=list)


class GameState(StrictModel):
    game_id: str
    status: Literal["waiting", "running", "finished"]
    map_asset: str | None = None
    round_index: int
    turn_index: int
    max_rounds: int
    current_player_id: str
    current_phase: str
    active_tile_id: str
    players: list[PlayerSnapshot]
    board: list[TileState]
    allowed_actions: list[ActionOption]
    minimal_human_actions: list[ActionOption] = Field(default_factory=list)
    waiting_for_human: bool = False
    human_wait_reason: Literal["none", "roll_dice", "branch_decision"] = "none"
    last_events: list[EventRecord]


class ActionRequest(BaseModel):
    game_id: str
    player_id: str
    action: ActionType | str
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
    room_name: str | None = None
    map_asset: str | None = None
    map_theme: str | None = None
    players: list[PlayerConfig] = Field(default_factory=list)
    max_rounds: int = Field(default=20, ge=1, le=200)
    seed: int = 20260418


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
    recap: dict[str, Any]
    prompt_materials: dict[str, Any]
    markdown: str


class StrategyVersionRecord(StrictModel):
    player_id: str
    version: str
    summary: str
    updated_at: datetime
    source_game_id: str | None = None


class StrategyVersionsResponse(StrictModel):
    records: list[StrategyVersionRecord]


class ModelExperienceRecord(StrictModel):
    model_id: str
    provider: str
    game_id: str
    summary: str
    created_at: datetime


class ModelExperienceResponse(StrictModel):
    records: list[ModelExperienceRecord]


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
