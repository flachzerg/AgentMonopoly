import random
import time
import uuid
from collections.abc import Iterable
from copy import deepcopy

from app.schemas import (
    ActionCommand,
    ActionType,
    DecisionOptions,
    ErrorCode,
    EventEnvelope,
    GameSnapshot,
    OutputContract,
    Phase,
    PlayerSnapshot,
    TileType,
    TurnInputV31,
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
