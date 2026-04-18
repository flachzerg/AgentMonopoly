import random
import time
import uuid
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.schemas import (
    ActionCommand,
    ActionOption,
    ActionType,
    AgentDecisionEnvelope,
    BoardTileSnapshot,
    DecisionOptions,
    ErrorCode,
    EventEnvelope,
    EventRecord,
    GameSnapshot,
    GameState,
    OutputContract,
    Phase,
    PlayerConfig,
    PlayerSnapshot,
    ReplayResponse,
    ReplayStep,
    TileContext,
    TileState,
    TileType,
    TurnInputV31,
    TurnMeta,
    TurnOutputV31,
)

PHASE_TRANSITIONS: dict[Phase, Phase | None] = {
    Phase.ROLL: Phase.TILE_ENTER,
    Phase.TILE_ENTER: Phase.AUTO_SETTLE,
    Phase.AUTO_SETTLE: Phase.DECISION,
    Phase.DECISION: Phase.EXECUTE,
    Phase.EXECUTE: Phase.LOG,
    Phase.LOG: None,
}

PHASE_ALLOWED_ACTIONS: dict[Phase, set[ActionType]] = {
    Phase.ROLL: {ActionType.ROLL_DICE},
    Phase.TILE_ENTER: {ActionType.PASS},
    Phase.AUTO_SETTLE: {ActionType.PASS},
    Phase.DECISION: {
        ActionType.BUY_PROPERTY,
        ActionType.UPGRADE_PROPERTY,
        ActionType.BANK_DEPOSIT,
        ActionType.BANK_WITHDRAW,
        ActionType.EVENT_CHOICE,
        ActionType.PROPOSE_ALLIANCE,
        ActionType.ACCEPT_ALLIANCE,
        ActionType.REJECT_ALLIANCE,
        ActionType.PASS,
    },
    Phase.EXECUTE: {ActionType.PASS},
    Phase.LOG: {ActionType.PASS},
}

DEFAULT_BOARD = [
    {"type": TileType.START, "name": "Start", "reward": 200},
    {"type": TileType.EMPTY, "name": "Empty-1"},
    {"type": TileType.BANK, "name": "Bank"},
    {"type": TileType.EVENT, "name": "Event-Auto", "event_mode": "auto", "delta": 120},
    {
        "type": TileType.EVENT,
        "name": "Event-Choice",
        "event_mode": "choice",
        "choices": {"safe": 60, "risky": -80},
    },
    {"type": TileType.PROPERTY, "name": "P-5", "base_price": 200, "upgrade_cost": 120, "toll_base": 80},
    {"type": TileType.EMPTY, "name": "Empty-6"},
    {"type": TileType.PROPERTY, "name": "P-7", "base_price": 240, "upgrade_cost": 120, "toll_base": 90},
]


def initialize_game_state(
    game_id: str,
    player_ids: list[str],
    start_cash: int = 1000,
    start_deposit: int = 0,
    board: list[dict] | None = None,
) -> dict:
    players = {
        pid: {
            "player_id": pid,
            "position": 0,
            "cash": start_cash,
            "deposit": start_deposit,
            "alive": True,
            "properties": [],
        }
        for pid in player_ids
    }
    return {
        "game_id": game_id,
        "round_index": 1,
        "turn_seq": 0,
        "player_order": player_ids,
        "current_player_idx": 0,
        "phase": Phase.ROLL,
        "board": deepcopy(board or DEFAULT_BOARD),
        "players": players,
        "alliances": {pid: None for pid in player_ids},
        "pending_alliance": set(),  # {(from, to)}
    }


def validate_action(action: ActionType, allowed_actions: Iterable[ActionType]) -> bool:
    return action in set(allowed_actions)


def get_next_phase(phase: Phase) -> Phase | None:
    return PHASE_TRANSITIONS.get(phase)


def validate_phase_transition(current_phase: Phase, target_phase: Phase | None) -> bool:
    return PHASE_TRANSITIONS.get(current_phase) == target_phase


def validate_phase_action(phase: Phase, action: ActionType) -> tuple[bool, ErrorCode | None]:
    allowed_actions = PHASE_ALLOWED_ACTIONS.get(phase, set())
    if action not in allowed_actions:
        return False, ErrorCode.ILLEGAL_ACTION_FOR_PHASE
    return True, None


def build_decision_options(phase: Phase) -> DecisionOptions:
    return DecisionOptions(
        phase=phase,
        allowed_actions=sorted(PHASE_ALLOWED_ACTIONS.get(phase, set()), key=lambda x: x.value),
    )


def run_turn(turn_input: TurnInputV31) -> TurnOutputV31:
    next_phase = get_next_phase(turn_input.phase)
    if turn_input.protocol_version != "DY-MONO-TURN-IN/3.1":
        contract = OutputContract(
            accepted=False,
            error_code=ErrorCode.INVALID_PARAMS,
            message="unsupported protocol version",
        )
        return _build_output(turn_input, contract, next_phase=None, events=[])

    command_action = turn_input.command.action if turn_input.command else ActionType.PASS
    is_action_valid, error_code = validate_phase_action(turn_input.phase, command_action)
    if not is_action_valid:
        contract = OutputContract(
            accepted=False,
            fallback_used=True,
            error_code=error_code,
            message="action not allowed in current phase",
        )
        return _build_output(turn_input, contract, next_phase=next_phase, events=[])

    events = _emit_phase_events(turn_input, command_action)
    contract = OutputContract(
        accepted=True,
        fallback_used=False,
        message="turn phase executed",
    )
    return _build_output(turn_input, contract, next_phase=next_phase, events=events)


def run_game_turn(
    game_state: dict,
    player_id: str,
    decision: ActionCommand | None = None,
    dice_value: int | None = None,
) -> TurnOutputV31:
    turn_id = f"turn-{uuid.uuid4().hex[:8]}"
    events: list[EventEnvelope] = []
    player = game_state["players"].get(player_id)
    if not player or not player["alive"]:
        return _build_turn_result_for_state(
            game_state=game_state,
            player_id=player_id,
            turn_id=turn_id,
            phase=Phase.LOG,
            next_phase=Phase.ROLL,
            events=events,
            contract=OutputContract(
                accepted=False,
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message="player not available",
            ),
            tile_type=TileType.EMPTY,
        )

    game_state["turn_seq"] += 1
    # ROLL
    phase = Phase.ROLL
    rolled = dice_value if dice_value is not None else random.randint(1, 6)
    _append_event(events, game_state, turn_id, phase, "dice.rolled", {"dice": rolled})
    board_size = len(game_state["board"])
    old_pos = player["position"]
    new_pos = (old_pos + rolled) % board_size
    passed_start = old_pos + rolled >= board_size
    player["position"] = new_pos
    _append_event(
        events,
        game_state,
        turn_id,
        Phase.TILE_ENTER,
        "player.moved",
        {"from": old_pos, "to": new_pos, "passed_start": passed_start},
    )
    tile = game_state["board"][new_pos]
    tile_type = TileType(tile["type"])

    # AUTO_SETTLE
    _auto_settle(game_state, player_id, tile, passed_start, events, turn_id)

    # DECISION + EXECUTE
    allowed_actions = _decision_actions_for_tile(game_state, player_id, tile)
    selected = decision.action if decision else ActionType.PASS
    if selected not in allowed_actions:
        selected = ActionType.PASS
        _append_event(
            events,
            game_state,
            turn_id,
            Phase.DECISION,
            "action.rejected",
            {"reason": ErrorCode.ILLEGAL_ACTION_FOR_PHASE.value},
        )
    _execute_decision(
        game_state=game_state,
        player_id=player_id,
        tile=tile,
        action=selected,
        params=decision.params if decision else {},
        events=events,
        turn_id=turn_id,
    )

    # LOG + round rotate
    _append_event(events, game_state, turn_id, Phase.LOG, "turn.finished", {"player_id": player_id})
    game_state["current_player_idx"] = (game_state["current_player_idx"] + 1) % len(game_state["player_order"])
    if game_state["current_player_idx"] == 0:
        game_state["round_index"] += 1
    game_state["phase"] = Phase.ROLL

    return _build_turn_result_for_state(
        game_state=game_state,
        player_id=player_id,
        turn_id=turn_id,
        phase=Phase.LOG,
        next_phase=Phase.ROLL,
        events=events,
        contract=OutputContract(accepted=True, message="full turn executed"),
        tile_type=tile_type,
        allowed_actions=allowed_actions,
    )


def _auto_settle(
    game_state: dict,
    player_id: str,
    tile: dict,
    passed_start: bool,
    events: list[EventEnvelope],
    turn_id: str,
) -> None:
    player = game_state["players"][player_id]
    tile_type = TileType(tile["type"])
    if passed_start:
        reward = game_state["board"][0].get("reward", 200)
        player["cash"] += reward
        _append_event(events, game_state, turn_id, Phase.AUTO_SETTLE, "start.passed", {"reward": reward})

    if tile_type == TileType.START:
        reward = tile.get("reward", 200)
        player["cash"] += reward
        _append_event(events, game_state, turn_id, Phase.AUTO_SETTLE, "start.landed", {"reward": reward})
        return
    if tile_type == TileType.EMPTY:
        _append_event(events, game_state, turn_id, Phase.AUTO_SETTLE, "empty.entered", {})
        return
    if tile_type == TileType.BANK:
        _append_event(events, game_state, turn_id, Phase.AUTO_SETTLE, "bank.entered", {})
        return
    if tile_type == TileType.EVENT and tile.get("event_mode") == "auto":
        delta = int(tile.get("delta", 0))
        player["cash"] += delta
        _append_event(events, game_state, turn_id, Phase.AUTO_SETTLE, "event.auto", {"delta": delta})
        return
    if tile_type == TileType.PROPERTY:
        owner = tile.get("owner_id")
        if not owner:
            _append_event(events, game_state, turn_id, Phase.AUTO_SETTLE, "property.unowned", {})
            return
        if owner == player_id:
            _append_event(events, game_state, turn_id, Phase.AUTO_SETTLE, "property.self", {})
            return
        if _is_ally(game_state, player_id, owner):
            _append_event(events, game_state, turn_id, Phase.AUTO_SETTLE, "toll.waived", {"owner_id": owner})
            return
        toll = _calc_toll(tile)
        paid = _charge_player(game_state, payer_id=player_id, amount=toll, events=events, turn_id=turn_id, reason="toll")
        game_state["players"][owner]["cash"] += paid
        _append_event(
            events,
            game_state,
            turn_id,
            Phase.AUTO_SETTLE,
            "toll.paid",
            {"owner_id": owner, "toll": toll, "paid": paid},
        )


def _decision_actions_for_tile(game_state: dict, player_id: str, tile: dict) -> set[ActionType]:
    if not game_state["players"][player_id]["alive"]:
        return {ActionType.PASS}
    tile_type = TileType(tile["type"])
    actions = {
        ActionType.PROPOSE_ALLIANCE,
        ActionType.ACCEPT_ALLIANCE,
        ActionType.REJECT_ALLIANCE,
        ActionType.PASS,
    }
    if tile_type == TileType.BANK:
        actions.update({ActionType.BANK_DEPOSIT, ActionType.BANK_WITHDRAW})
    if tile_type == TileType.EVENT and tile.get("event_mode") == "choice":
        actions.add(ActionType.EVENT_CHOICE)
    if tile_type == TileType.PROPERTY:
        owner = tile.get("owner_id")
        if owner is None:
            actions.add(ActionType.BUY_PROPERTY)
        elif owner == player_id:
            actions.add(ActionType.UPGRADE_PROPERTY)
    return actions


def _execute_decision(
    game_state: dict,
    player_id: str,
    tile: dict,
    action: ActionType,
    params: dict,
    events: list[EventEnvelope],
    turn_id: str,
) -> None:
    player = game_state["players"][player_id]
    tile_type = TileType(tile["type"])

    if action == ActionType.BUY_PROPERTY and tile_type == TileType.PROPERTY and not tile.get("owner_id"):
        price = int(tile.get("base_price", 200))
        paid = _charge_player(game_state, payer_id=player_id, amount=price, events=events, turn_id=turn_id, reason="buy")
        if paid >= price:
            tile["owner_id"] = player_id
            tile["level"] = 0
            player["properties"].append(player["position"])
            _append_event(events, game_state, turn_id, Phase.EXECUTE, "property.bought", {"price": price})
        return

    if action == ActionType.UPGRADE_PROPERTY and tile_type == TileType.PROPERTY and tile.get("owner_id") == player_id:
        cost = int(tile.get("upgrade_cost", 120))
        paid = _charge_player(game_state, payer_id=player_id, amount=cost, events=events, turn_id=turn_id, reason="upgrade")
        if paid >= cost:
            tile["level"] = int(tile.get("level", 0)) + 1
            _append_event(
                events,
                game_state,
                turn_id,
                Phase.EXECUTE,
                "property.upgraded",
                {"cost": cost, "level": tile["level"]},
            )
        return

    if action == ActionType.BANK_DEPOSIT:
        amount = max(0, int(params.get("amount", 0)))
        amount = min(amount, player["cash"])
        player["cash"] -= amount
        player["deposit"] += amount
        _append_event(events, game_state, turn_id, Phase.EXECUTE, "bank.deposit", {"amount": amount})
        return

    if action == ActionType.BANK_WITHDRAW:
        amount = max(0, int(params.get("amount", 0)))
        amount = min(amount, player["deposit"])
        player["deposit"] -= amount
        player["cash"] += amount
        _append_event(events, game_state, turn_id, Phase.EXECUTE, "bank.withdraw", {"amount": amount})
        return

    if action == ActionType.EVENT_CHOICE and tile_type == TileType.EVENT:
        key = str(params.get("choice", "safe"))
        choices = tile.get("choices", {})
        delta = int(choices.get(key, 0))
        player["cash"] += delta
        _append_event(events, game_state, turn_id, Phase.EXECUTE, "event.choice", {"choice": key, "delta": delta})
        return

    if action == ActionType.PROPOSE_ALLIANCE:
        target = str(params.get("target_player_id", ""))
        if target in game_state["players"] and target != player_id:
            game_state["pending_alliance"].add((player_id, target))
            _append_event(
                events,
                game_state,
                turn_id,
                Phase.EXECUTE,
                "alliance.proposed",
                {"from": player_id, "to": target},
            )
        return

    if action == ActionType.ACCEPT_ALLIANCE:
        requester = str(params.get("requester_player_id", ""))
        if (requester, player_id) in game_state["pending_alliance"]:
            if game_state["alliances"].get(player_id) is None and game_state["alliances"].get(requester) is None:
                game_state["pending_alliance"].discard((requester, player_id))
                game_state["alliances"][player_id] = requester
                game_state["alliances"][requester] = player_id
                _append_event(
                    events,
                    game_state,
                    turn_id,
                    Phase.EXECUTE,
                    "alliance.formed",
                    {"a": requester, "b": player_id},
                )
        return

    if action == ActionType.REJECT_ALLIANCE:
        requester = str(params.get("requester_player_id", ""))
        game_state["pending_alliance"].discard((requester, player_id))
        _append_event(
            events,
            game_state,
            turn_id,
            Phase.EXECUTE,
            "alliance.rejected",
            {"from": requester, "to": player_id},
        )


def _charge_player(
    game_state: dict,
    payer_id: str,
    amount: int,
    events: list[EventEnvelope],
    turn_id: str,
    reason: str,
) -> int:
    player = game_state["players"][payer_id]
    need = amount
    paid = 0
    cash_used = min(player["cash"], need)
    player["cash"] -= cash_used
    need -= cash_used
    paid += cash_used
    deposit_used = min(player["deposit"], need)
    player["deposit"] -= deposit_used
    need -= deposit_used
    paid += deposit_used

    if need > 0:
        _append_event(
            events,
            game_state,
            turn_id,
            Phase.AUTO_SETTLE,
            "insolvent.triggered",
            {"player_id": payer_id, "remaining_debt": need, "reason": reason},
        )
        recovered = _auction_properties(game_state, payer_id, need, events, turn_id)
        paid += recovered
        need -= recovered
        if need > 0:
            player["alive"] = False
            _append_event(
                events,
                game_state,
                turn_id,
                Phase.AUTO_SETTLE,
                "player.bankrupt",
                {"player_id": payer_id, "remaining_debt": need},
            )
    return paid


def _auction_properties(
    game_state: dict,
    owner_id: str,
    target_amount: int,
    events: list[EventEnvelope],
    turn_id: str,
) -> int:
    owner = game_state["players"][owner_id]
    recovered = 0
    owned_positions = list(owner["properties"])
    for pos in owned_positions:
        tile = game_state["board"][pos]
        reserve = int(tile.get("base_price", 200)) + int(tile.get("level", 0)) * int(tile.get("upgrade_cost", 120))
        buyer_id = _find_buyer(game_state, owner_id, reserve)
        if not buyer_id:
            continue
        buyer = game_state["players"][buyer_id]
        buyer["cash"] -= reserve
        owner["cash"] += reserve
        recovered += reserve
        tile["owner_id"] = buyer_id
        owner["properties"].remove(pos)
        buyer["properties"].append(pos)
        _append_event(
            events,
            game_state,
            turn_id,
            Phase.AUTO_SETTLE,
            "auction.sold",
            {"position": pos, "from": owner_id, "to": buyer_id, "price": reserve},
        )
        if recovered >= target_amount:
            break
    return recovered


def _find_buyer(game_state: dict, exclude_player_id: str, price: int) -> str | None:
    for pid, player in game_state["players"].items():
        if pid == exclude_player_id:
            continue
        if player["alive"] and player["cash"] >= price:
            return pid
    return None


def _is_ally(game_state: dict, player_a: str, player_b: str) -> bool:
    return game_state["alliances"].get(player_a) == player_b and game_state["alliances"].get(player_b) == player_a


def _calc_toll(tile: dict) -> int:
    return int(tile.get("toll_base", 80)) + int(tile.get("level", 0)) * 40


def _append_event(
    events: list[EventEnvelope],
    game_state: dict,
    turn_id: str,
    phase: Phase,
    event_type: str,
    payload: dict,
) -> None:
    events.append(
        EventEnvelope(
            event_id=str(uuid.uuid4()),
            game_id=game_state["game_id"],
            round_index=game_state["round_index"],
            turn_id=turn_id,
            phase=phase,
            event_type=event_type,
            ts=time.time(),
            payload=payload,
        )
    )


def _build_turn_result_for_state(
    game_state: dict,
    player_id: str,
    turn_id: str,
    phase: Phase,
    next_phase: Phase | None,
    events: list[EventEnvelope],
    contract: OutputContract,
    tile_type: TileType,
    allowed_actions: set[ActionType] | None = None,
) -> TurnOutputV31:
    players = [
        PlayerSnapshot(
            player_id=pid,
            position=p["position"],
            cash=p["cash"],
            deposit=p["deposit"],
            alive=p["alive"],
        )
        for pid, p in game_state["players"].items()
    ]
    snapshot = GameSnapshot(
        game_id=game_state["game_id"],
        round_index=game_state["round_index"],
        current_player_id=game_state["player_order"][game_state["current_player_idx"]],
        phase=phase,
        tile_type=tile_type,
        players=players,
    )
    options = DecisionOptions(phase=Phase.DECISION, allowed_actions=sorted(allowed_actions, key=lambda x: x.value)) if allowed_actions is not None else build_decision_options(phase)
    return TurnOutputV31(
        game_id=game_state["game_id"],
        player_id=player_id,
        turn_id=turn_id,
        round_index=game_state["round_index"],
        phase=phase,
        next_phase=next_phase,
        decision_options=options,
        output_contract=contract,
        events=events,
        snapshot=snapshot,
    )


def _emit_phase_events(turn_input: TurnInputV31, action: ActionType) -> list[EventEnvelope]:
    base_event = EventEnvelope(
        event_id=str(uuid.uuid4()),
        game_id=turn_input.game_id,
        round_index=turn_input.round_index,
        turn_id=turn_input.turn_id,
        phase=turn_input.phase,
        event_type=f"phase.{turn_input.phase.value.lower()}",
        ts=time.time(),
        payload={"action": action.value},
    )
    events = [base_event]
    if turn_input.phase == Phase.ROLL and action == ActionType.ROLL_DICE:
        events.append(
            EventEnvelope(
                event_id=str(uuid.uuid4()),
                game_id=turn_input.game_id,
                round_index=turn_input.round_index,
                turn_id=turn_input.turn_id,
                phase=turn_input.phase,
                event_type="dice.rolled",
                ts=time.time(),
                payload={"dice": random.randint(1, 6)},
            )
        )
    return events


def _build_output(
    turn_input: TurnInputV31,
    contract: OutputContract,
    next_phase: Phase | None,
    events: list[EventEnvelope],
) -> TurnOutputV31:
    snapshot = GameSnapshot(
        game_id=turn_input.game_id,
        round_index=turn_input.round_index,
        current_player_id=turn_input.player_id,
        phase=turn_input.phase,
        tile_type=turn_input.tile_type,
        players=[PlayerSnapshot(player_id=turn_input.player_id)],
    )
    return TurnOutputV31(
        game_id=turn_input.game_id,
        player_id=turn_input.player_id,
        turn_id=turn_input.turn_id,
        round_index=turn_input.round_index,
        phase=turn_input.phase,
        next_phase=next_phase,
        decision_options=build_decision_options(turn_input.phase),
        output_contract=contract,
        events=events,
        snapshot=snapshot,
    )


VALID_ACTIONS = {
    "roll_dice",
    "buy_property",
    "skip_buy",
    "bank_deposit",
    "bank_withdraw",
    "propose_alliance",
    "pass",
}


@dataclass
class Player:
    player_id: str
    name: str
    is_agent: bool
    cash: int = 2000
    deposit: int = 500
    position: int = 0
    property_ids: list[str] = field(default_factory=list)
    alliance_with: str | None = None
    alive: bool = True


@dataclass
class Tile:
    tile_id: str
    tile_index: int
    tile_type: str
    tile_subtype: str
    name: str
    owner_id: str | None = None
    property_price: int | None = None
    toll: int | None = None
    event_key: str | None = None
    quiz_key: str | None = None


@dataclass
class GameSession:
    game_id: str
    max_rounds: int
    rng: random.Random
    players: list[Player]
    board: list[Tile]
    status: str = "running"
    round_index: int = 1
    turn_index: int = 1
    current_player_index: int = 0
    current_phase: str = "ROLL"
    active_tile_index: int = 0
    events: list[EventRecord] = field(default_factory=list)
    replay_steps: list[ReplayStep] = field(default_factory=list)
    allowed_actions: list[ActionOption] = field(default_factory=list)


class GameManager:
    def __init__(self) -> None:
        self._games: dict[str, GameSession] = {}

    def create_game(self, game_id: str, players: list[PlayerConfig], max_rounds: int, seed: int) -> GameSession:
        if game_id in self._games:
            raise ValueError(f"game already exists: {game_id}")
        if len(players) < 2:
            raise ValueError("at least two players are required")

        session = GameSession(
            game_id=game_id,
            max_rounds=max_rounds,
            rng=random.Random(seed),
            players=[Player(player_id=item.player_id, name=item.name, is_agent=item.is_agent) for item in players],
            board=build_default_board(),
        )
        session.allowed_actions = self._allowed_actions(session)
        self._games[game_id] = session
        self._append_event(
            session,
            "game.started",
            {
                "game_id": game_id,
                "round_index": session.round_index,
                "turn_index": session.turn_index,
                "current_player_id": session.players[0].player_id,
            },
        )
        return session

    def list_games(self) -> list[str]:
        return sorted(self._games.keys())

    def has_game(self, game_id: str) -> bool:
        return game_id in self._games

    def get_game(self, game_id: str) -> GameSession:
        session = self._games.get(game_id)
        if not session:
            raise KeyError(f"unknown game: {game_id}")
        return session

    def state(self, game_id: str) -> GameState:
        return self._to_state(self.get_game(game_id))

    def replay(self, game_id: str) -> ReplayResponse:
        session = self.get_game(game_id)
        return ReplayResponse(game_id=game_id, total_turns=len(session.replay_steps), steps=session.replay_steps)

    def valid_action(self, action: str, allowed_actions: list[ActionOption]) -> bool:
        if action not in VALID_ACTIONS:
            return False
        return action in {item.action for item in allowed_actions}

    def apply_action(
        self,
        game_id: str,
        player_id: str,
        action: str,
        args: dict[str, Any],
        decision_audit: AgentDecisionEnvelope | None = None,
    ) -> tuple[bool, str, EventRecord | None]:
        session = self.get_game(game_id)
        if session.status != "running":
            return False, "game already finished", None

        current_player = session.players[session.current_player_index]
        if player_id != current_player.player_id:
            return False, "not current player", None

        if not self.valid_action(action, session.allowed_actions):
            self._append_event(
                session,
                "action.rejected",
                {"player_id": player_id, "action": action, "reason": "action_not_allowed"},
            )
            return False, "action not allowed", None

        option = next(item for item in session.allowed_actions if item.action == action)
        if not self._validate_args(option, args):
            self._append_event(
                session,
                "action.rejected",
                {"player_id": player_id, "action": action, "reason": "invalid_args", "args": args},
            )
            return False, "invalid args", None

        merged_args = option.default_args | args
        event = self._execute_action(session, current_player, action, merged_args)
        if action in {"buy_property", "skip_buy", "bank_deposit", "bank_withdraw", "propose_alliance", "pass"}:
            self._finalize_turn(session, decision_audit)
        return True, "action accepted", event

    def advance_to_decision_if_needed(self, game_id: str, player_id: str) -> None:
        session = self.get_game(game_id)
        current_player = session.players[session.current_player_index]
        if current_player.player_id != player_id:
            return
        if session.current_phase == "ROLL":
            self.apply_action(game_id, player_id, "roll_dice", {}, None)

    def build_tile_context(self, session: GameSession) -> TileContext:
        current_player = session.players[session.current_player_index]
        tile = session.board[session.active_tile_index]
        subtype = resolve_tile_subtype(tile, current_player)
        return TileContext(
            tile_id=tile.tile_id,
            tile_index=tile.tile_index,
            tile_type=tile.tile_type,
            tile_subtype=subtype,
            owner_id=tile.owner_id,
            property_price=tile.property_price,
            toll=tile.toll,
            event_key=tile.event_key,
            quiz_key=tile.quiz_key,
        )

    def build_turn_meta(self, session: GameSession) -> TurnMeta:
        current_player = session.players[session.current_player_index]
        tile_context = self.build_tile_context(session)
        return TurnMeta(
            game_id=session.game_id,
            round_index=session.round_index,
            turn_index=session.turn_index,
            current_player_id=current_player.player_id,
            tile_subtype=tile_context.tile_subtype,
        )

    def _finalize_turn(self, session: GameSession, decision_audit: AgentDecisionEnvelope | None) -> None:
        snapshot = self._to_state(session)
        step = ReplayStep(
            turn_index=session.turn_index,
            round_index=session.round_index,
            phase="LOG",
            phase_trace=["ROLL", "TILE_ENTER", "AUTO_SETTLE", "DECISION", "EXECUTE", "LOG"],
            state=snapshot,
            events=session.events[-5:],
            candidate_actions=(decision_audit.decision.candidate_actions if decision_audit else []),
            final_action=(decision_audit.decision.action if decision_audit else None),
            strategy_tags=(decision_audit.decision.strategy_tags if decision_audit else []),
            decision_audit=(decision_audit.audit if decision_audit else None),
        )
        session.replay_steps.append(step)
        self._append_event(
            session,
            "turn.logged",
            {"turn_index": session.turn_index, "round_index": session.round_index},
        )

        alive_players = [item for item in session.players if item.alive]
        if session.round_index >= session.max_rounds or len(alive_players) <= 1:
            session.status = "finished"
            session.current_phase = "LOG"
            session.allowed_actions = []
            self._append_event(
                session,
                "game.finished",
                {"winner": self._winner_id(session), "round_index": session.round_index},
            )
            return

        session.turn_index += 1
        session.current_player_index = (session.current_player_index + 1) % len(session.players)
        if session.current_player_index == 0:
            session.round_index += 1
        session.current_phase = "ROLL"
        current_player = session.players[session.current_player_index]
        session.active_tile_index = current_player.position
        session.allowed_actions = self._allowed_actions(session)

    def _execute_action(self, session: GameSession, player: Player, action: str, args: dict[str, Any]) -> EventRecord | None:
        if action == "roll_dice":
            return self._roll_and_settle(session, player)

        if action == "buy_property":
            tile_id = str(args["tile_id"])
            tile = self._find_tile(session, tile_id)
            if tile.owner_id is not None:
                return self._append_event(
                    session,
                    "action.rejected",
                    {"player_id": player.player_id, "action": action, "reason": "property_owned"},
                )
            price = tile.property_price or 0
            if player.cash < price:
                return self._append_event(
                    session,
                    "action.rejected",
                    {"player_id": player.player_id, "action": action, "reason": "cash_not_enough"},
                )
            player.cash -= price
            tile.owner_id = player.player_id
            player.property_ids.append(tile.tile_id)
            return self._append_event(
                session,
                "action.accepted",
                {"player_id": player.player_id, "action": action, "tile_id": tile.tile_id, "price": price},
            )

        if action == "skip_buy":
            return self._append_event(session, "action.accepted", {"player_id": player.player_id, "action": action})

        if action == "bank_deposit":
            amount = int(args["amount"])
            player.cash -= amount
            player.deposit += amount
            return self._append_event(
                session,
                "action.accepted",
                {"player_id": player.player_id, "action": action, "amount": amount, "cash": player.cash, "deposit": player.deposit},
            )

        if action == "bank_withdraw":
            amount = int(args["amount"])
            player.deposit -= amount
            player.cash += amount
            return self._append_event(
                session,
                "action.accepted",
                {"player_id": player.player_id, "action": action, "amount": amount, "cash": player.cash, "deposit": player.deposit},
            )

        if action == "propose_alliance":
            target_id = str(args["target_player_id"])
            target = self._find_player(session, target_id)
            if not target.alive:
                return self._append_event(
                    session,
                    "action.rejected",
                    {"player_id": player.player_id, "action": action, "reason": "target_bankrupt"},
                )
            if player.alliance_with or target.alliance_with:
                return self._append_event(
                    session,
                    "action.rejected",
                    {"player_id": player.player_id, "action": action, "reason": "alliance_busy"},
                )
            player.alliance_with = target.player_id
            target.alliance_with = player.player_id
            return self._append_event(
                session,
                "alliance.created",
                {"player_id": player.player_id, "target_player_id": target.player_id},
            )

        return self._append_event(session, "action.accepted", {"player_id": player.player_id, "action": "pass"})

    def _roll_and_settle(self, session: GameSession, player: Player) -> EventRecord:
        session.current_phase = "TILE_ENTER"
        dice = session.rng.randint(1, 6)
        old_position = player.position
        player.position = (player.position + dice) % len(session.board)
        passed_start = player.position < old_position
        if passed_start:
            player.cash += 200
        session.active_tile_index = player.position
        self._append_event(
            session,
            "dice.rolled",
            {"player_id": player.player_id, "dice": dice, "position": player.position, "passed_start": passed_start},
        )
        session.current_phase = "AUTO_SETTLE"
        tile = session.board[player.position]
        settle_event = self._auto_settle_v2(session, player, tile)
        session.current_phase = "DECISION"
        session.allowed_actions = self._allowed_actions(session)
        return settle_event

    def _auto_settle_v2(self, session: GameSession, player: Player, tile: Tile) -> EventRecord:
        if tile.tile_type == "PROPERTY" and tile.owner_id and tile.owner_id != player.player_id:
            if player.alliance_with == tile.owner_id:
                return self._append_event(
                    session,
                    "settlement.applied",
                    {"player_id": player.player_id, "tile_id": tile.tile_id, "type": "toll_waived_by_alliance"},
                )
            toll = tile.toll or 0
            owner = self._find_player(session, tile.owner_id)
            remaining = self._pay_amount(player, toll)
            owner.cash += toll - remaining
            if remaining > 0:
                player.alive = False
                return self._append_event(
                    session,
                    "player.bankrupt",
                    {"player_id": player.player_id, "debt": remaining, "tile_id": tile.tile_id},
                )
            return self._append_event(
                session,
                "settlement.applied",
                {"player_id": player.player_id, "tile_id": tile.tile_id, "type": "toll_paid", "amount": toll, "owner_id": owner.player_id},
            )

        if tile.tile_type == "EVENT":
            delta = session.rng.choice([-200, -100, 100, 200, 300])
            player.cash = max(0, player.cash + delta)
            return self._append_event(
                session,
                "settlement.applied",
                {"player_id": player.player_id, "tile_id": tile.tile_id, "type": "event_delta", "delta": delta},
            )

        if tile.tile_type == "BANK":
            return self._append_event(
                session,
                "settlement.applied",
                {"player_id": player.player_id, "tile_id": tile.tile_id, "type": "bank_enter"},
            )

        if tile.tile_type == "QUIZ":
            return self._append_event(
                session,
                "quiz.placeholder",
                {"player_id": player.player_id, "tile_id": tile.tile_id, "status": "reserved"},
            )

        return self._append_event(
            session,
            "settlement.applied",
            {"player_id": player.player_id, "tile_id": tile.tile_id, "type": "no_effect"},
        )

    def _pay_amount(self, player: Player, amount: int) -> int:
        if amount <= 0:
            return 0
        if player.cash >= amount:
            player.cash -= amount
            return 0
        shortage = amount - player.cash
        player.cash = 0
        if player.deposit >= shortage:
            player.deposit -= shortage
            return 0
        remaining = shortage - player.deposit
        player.deposit = 0
        return remaining

    def _allowed_actions(self, session: GameSession) -> list[ActionOption]:
        player = session.players[session.current_player_index]
        if session.current_phase == "ROLL":
            return [ActionOption(action="roll_dice", description="Roll dice", required_args=[])]
        if session.current_phase != "DECISION":
            return [ActionOption(action="pass", description="Pass", required_args=[])]

        tile = session.board[session.active_tile_index]
        subtype = resolve_tile_subtype(tile, player)
        options: list[ActionOption] = []
        if subtype == "PROPERTY_UNOWNED":
            options.append(
                ActionOption(
                    action="buy_property",
                    description="Buy property",
                    required_args=["tile_id"],
                    allowed_values={"tile_id": [tile.tile_id]},
                    default_args={"tile_id": tile.tile_id},
                )
            )
            options.append(ActionOption(action="skip_buy", description="Skip buy"))

        if subtype == "BANK":
            max_deposit = max((player.cash // 100) * 100, 0)
            max_withdraw = max((player.deposit // 100) * 100, 0)
            if max_deposit >= 100:
                options.append(
                    ActionOption(
                        action="bank_deposit",
                        description="Deposit to bank",
                        required_args=["amount"],
                        allowed_values={"amount": list(range(100, max_deposit + 1, 100))},
                        default_args={"amount": min(200, max_deposit)},
                    )
                )
            if max_withdraw >= 100:
                options.append(
                    ActionOption(
                        action="bank_withdraw",
                        description="Withdraw from bank",
                        required_args=["amount"],
                        allowed_values={"amount": list(range(100, max_withdraw + 1, 100))},
                        default_args={"amount": min(200, max_withdraw)},
                    )
                )

        target_players = [item.player_id for item in session.players if item.player_id != player.player_id and item.alive and item.alliance_with is None]
        if target_players and player.alliance_with is None and session.current_phase == "DECISION":
            options.append(
                ActionOption(
                    action="propose_alliance",
                    description="Create alliance",
                    required_args=["target_player_id"],
                    allowed_values={"target_player_id": target_players},
                    default_args={"target_player_id": target_players[0]},
                )
            )

        options.append(ActionOption(action="pass", description="Pass"))
        return options

    def _validate_args(self, option: ActionOption, args: dict[str, Any]) -> bool:
        merged = option.default_args | args
        for key in option.required_args:
            if key not in merged:
                return False
        for key, allowed in option.allowed_values.items():
            if key in merged and merged[key] not in allowed:
                return False
        return True

    def _to_state(self, session: GameSession) -> GameState:
        players = [self._to_player_snapshot(session, item) for item in session.players]
        board = [
            TileState(
                tile_id=item.tile_id,
                tile_index=item.tile_index,
                tile_type=item.tile_type,
                tile_subtype=item.tile_subtype,
                name=item.name,
                owner_id=item.owner_id,
                property_price=item.property_price,
                toll=item.toll,
            )
            for item in session.board
        ]
        current_player = session.players[session.current_player_index]
        return GameState(
            game_id=session.game_id,
            status=session.status,  # type: ignore[arg-type]
            round_index=session.round_index,
            turn_index=session.turn_index,
            max_rounds=session.max_rounds,
            current_player_id=current_player.player_id,
            current_phase=session.current_phase,
            active_tile_id=session.board[session.active_tile_index].tile_id,
            players=players,
            board=board,
            allowed_actions=session.allowed_actions,
            last_events=session.events[-20:],
        )

    def _to_player_snapshot(self, session: GameSession, player: Player) -> PlayerSnapshot:
        property_value = 0
        for item in session.board:
            if item.owner_id == player.player_id and item.property_price:
                property_value += item.property_price
        return PlayerSnapshot(
            player_id=player.player_id,
            name=player.name,
            is_agent=player.is_agent,
            cash=player.cash,
            deposit=player.deposit,
            net_worth=player.cash + player.deposit + property_value,
            position=player.position,
            property_ids=list(player.property_ids),
            alliance_with=player.alliance_with,
            alive=player.alive,
        )

    def build_players_snapshot(self, session: GameSession) -> list[PlayerSnapshot]:
        return [self._to_player_snapshot(session, item) for item in session.players]

    def build_board_snapshot(self, session: GameSession) -> list[BoardTileSnapshot]:
        return [
            BoardTileSnapshot(
                tile_id=item.tile_id,
                tile_index=item.tile_index,
                tile_type=item.tile_type,
                tile_subtype=item.tile_subtype,
                owner_id=item.owner_id,
                property_price=item.property_price,
                toll=item.toll,
            )
            for item in session.board
        ]

    def _find_player(self, session: GameSession, player_id: str) -> Player:
        for item in session.players:
            if item.player_id == player_id:
                return item
        raise KeyError(f"unknown player: {player_id}")

    def _find_tile(self, session: GameSession, tile_id: str) -> Tile:
        for item in session.board:
            if item.tile_id == tile_id:
                return item
        raise KeyError(f"unknown tile: {tile_id}")

    def _winner_id(self, session: GameSession) -> str | None:
        scores = sorted(((self._to_player_snapshot(session, item).net_worth, item.player_id) for item in session.players if item.alive), reverse=True)
        return scores[0][1] if scores else None

    def _append_event(self, session: GameSession, event_type: str, payload: dict[str, Any]) -> EventRecord:
        event = EventRecord(
            event_id=uuid4().hex,
            ts=datetime.now(timezone.utc),
            type=event_type,
            game_id=session.game_id,
            round_index=session.round_index,
            turn_index=session.turn_index,
            payload=payload,
        )
        session.events.append(event)
        return event


def resolve_tile_subtype(tile: Tile, current_player: Player) -> str:
    if tile.tile_type == "PROPERTY":
        if tile.owner_id is None:
            return "PROPERTY_UNOWNED"
        if tile.owner_id == current_player.player_id:
            return "PROPERTY_SELF"
        if current_player.alliance_with == tile.owner_id:
            return "PROPERTY_ALLY"
        return "PROPERTY_OTHER"
    if tile.tile_type == "BANK":
        return "BANK"
    if tile.tile_type == "EVENT":
        return "EVENT"
    if tile.tile_type == "QUIZ":
        return "QUIZ"
    return "EMPTY"


def template_key_for_tile_subtype(tile_subtype: str) -> str:
    mapping = {
        "PROPERTY_UNOWNED": "PROPERTY_UNOWNED_TEMPLATE",
        "PROPERTY_SELF": "PROPERTY_SELF_TEMPLATE",
        "PROPERTY_ALLY": "PROPERTY_ALLY_TEMPLATE",
        "PROPERTY_OTHER": "PROPERTY_OTHER_TEMPLATE",
        "BANK": "BANK_TEMPLATE",
        "EVENT": "EVENT_TEMPLATE",
        "QUIZ": "QUIZ_TEMPLATE",
        "EMPTY": "EMPTY_TEMPLATE",
    }
    return mapping.get(tile_subtype, "EMPTY_TEMPLATE")


def build_default_board() -> list[Tile]:
    return [
        Tile("T00", 0, "START", "START", "Start"),
        Tile("T01", 1, "PROPERTY", "PROPERTY", "Hill Road", property_price=200, toll=40),
        Tile("T02", 2, "EMPTY", "EMPTY", "Open Park"),
        Tile("T03", 3, "BANK", "BANK", "City Bank"),
        Tile("T04", 4, "EVENT", "EVENT", "Event Plaza", event_key="EVT_SMALL"),
        Tile("T05", 5, "PROPERTY", "PROPERTY", "River Side", property_price=240, toll=48),
        Tile("T06", 6, "EMPTY", "EMPTY", "Coffee Spot"),
        Tile("T07", 7, "PROPERTY", "PROPERTY", "Sunset Ave", property_price=280, toll=56),
        Tile("T08", 8, "BANK", "BANK", "Main Bank"),
        Tile("T09", 9, "EVENT", "EVENT", "Fortune Gate", event_key="EVT_BIG"),
        Tile("T10", 10, "PROPERTY", "PROPERTY", "Lake View", property_price=320, toll=64),
        Tile("T11", 11, "EMPTY", "EMPTY", "Metro Station"),
        Tile("T12", 12, "PROPERTY", "PROPERTY", "Market Square", property_price=360, toll=72),
        Tile("T13", 13, "EMPTY", "EMPTY", "Open Street"),
        Tile("T14", 14, "EVENT", "EVENT", "Lucky Lane", event_key="EVT_RANDOM"),
        Tile("T15", 15, "BANK", "BANK", "Reserve Bank"),
    ]
