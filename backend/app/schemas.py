from enum import Enum

from pydantic import BaseModel, Field

TURN_INPUT_VERSION = "DY-MONO-TURN-IN/3.1"
TURN_OUTPUT_VERSION = "DY-MONO-TURN-OUT/3.1"


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
    accepted: bool
    fallback_used: bool = False
    error_code: ErrorCode | None = None
    message: str = ""


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
    phase: Phase
    action: ActionType
    params: dict = Field(default_factory=dict)


class ActionResponse(BaseModel):
    accepted: bool
    message: str
    error_code: ErrorCode | None = None


class CreateGameRequest(BaseModel):
    game_id: str
    player_ids: list[str]
    start_cash: int = 1000
    start_deposit: int = 0


class PlayTurnRequest(BaseModel):
    player_id: str
    action: ActionType = ActionType.PASS
    params: dict = Field(default_factory=dict)
    dice_value: int | None = None
    idempotency_key: str | None = None
