from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.map_engine import load_runtime_board
from app.schemas import (
    ActionOption,
    AgentConfig,
    AgentDecisionEnvelope,
    BoardTileSnapshot,
    EventRecord,
    GameState,
    PlayerConfig,
    PlayerSnapshot,
    ReplayResponse,
    ReplayStep,
    TileContext,
    TileState,
    TurnMeta,
)

VALID_ACTIONS = {
    "roll_dice",
    "buy_property",
    "skip_buy",
    "upgrade_property",
    "bank_deposit",
    "bank_withdraw",
    "event_choice",
    "propose_alliance",
    "accept_alliance",
    "reject_alliance",
    "set_route_preference",
    "pass",
}


@dataclass
class Player:
    player_id: str
    name: str
    is_agent: bool
    agent_config: AgentConfig | None = None
    cash: int = 2000
    deposit: int = 500
    position: int = 0
    current_tile_id: str | None = None
    route_preference_tile_id: str | None = None
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
    next_tile_ids: list[str] = field(default_factory=list)


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
    active_tile_id: str = ""
    events: list[EventRecord] = field(default_factory=list)
    replay_steps: list[ReplayStep] = field(default_factory=list)
    allowed_actions: list[ActionOption] = field(default_factory=list)
    pending_alliances: set[tuple[str, str]] = field(default_factory=set)


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
            players=[
                Player(
                    player_id=item.player_id,
                    name=item.name,
                    is_agent=item.is_agent,
                    agent_config=item.agent_config,
                )
                for item in players
            ],
            board=build_default_board(),
        )
        if session.board:
            start_tile_id = self._start_tile_id(session)
            for item in session.players:
                item.current_tile_id = start_tile_id
                item.position = self._tile_index_by_id(session, start_tile_id)
            session.active_tile_id = start_tile_id
            session.active_tile_index = self._tile_index_by_id(session, start_tile_id)
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
        if not current_player.alive:
            return False, "current player is bankrupt", None

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

        if session.current_phase == "DECISION" and action not in {"roll_dice", "set_route_preference"}:
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
        tile = self._active_tile(session, current_player)
        subtype = resolve_tile_subtype(tile, current_player)
        next_tile_ids = self._next_tile_ids(session, tile)
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
            next_tile_ids=next_tile_ids,
            branch_options=next_tile_ids if len(next_tile_ids) > 1 else [],
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
                next_tile_ids=self._next_tile_ids(session, item),
            )
            for item in session.board
        ]

    def _finalize_turn(self, session: GameSession, decision_audit: AgentDecisionEnvelope | None) -> None:
        snapshot = self._to_state(session)
        step = ReplayStep(
            turn_index=session.turn_index,
            round_index=session.round_index,
            phase="LOG",
            phase_trace=["ROLL", "TILE_ENTER", "AUTO_SETTLE", "DECISION", "EXECUTE", "LOG"],
            state=snapshot,
            events=session.events[-8:],
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

        self._advance_to_next_alive_player(session)
        session.turn_index += 1
        session.current_phase = "ROLL"
        current_player = session.players[session.current_player_index]
        active_tile = self._player_tile(session, current_player)
        session.active_tile_id = active_tile.tile_id
        session.active_tile_index = active_tile.tile_index
        session.allowed_actions = self._allowed_actions(session)

    def _advance_to_next_alive_player(self, session: GameSession) -> None:
        total = len(session.players)
        start = session.current_player_index
        wrapped = False

        while True:
            next_index = (session.current_player_index + 1) % total
            if next_index == 0:
                wrapped = True
            session.current_player_index = next_index
            if session.players[next_index].alive:
                if wrapped:
                    session.round_index += 1
                return
            if next_index == start:
                return

    def _execute_action(self, session: GameSession, player: Player, action: str, args: dict[str, Any]) -> EventRecord | None:
        if action == "roll_dice":
            return self._roll_and_settle(session, player)

        if action == "buy_property":
            tile = self._find_tile(session, str(args["tile_id"]))
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
            if tile.tile_id not in player.property_ids:
                player.property_ids.append(tile.tile_id)
            return self._append_event(
                session,
                "action.accepted",
                {"player_id": player.player_id, "action": action, "tile_id": tile.tile_id, "price": price},
            )

        if action == "skip_buy":
            return self._append_event(session, "action.accepted", {"player_id": player.player_id, "action": action})

        if action == "upgrade_property":
            tile = self._find_tile(session, str(args["tile_id"]))
            if tile.owner_id != player.player_id:
                return self._append_event(
                    session,
                    "action.rejected",
                    {"player_id": player.player_id, "action": action, "reason": "not_owner"},
                )
            upgrade_cost = max((tile.property_price or 0) // 2, 100)
            if player.cash < upgrade_cost:
                return self._append_event(
                    session,
                    "action.rejected",
                    {"player_id": player.player_id, "action": action, "reason": "cash_not_enough"},
                )
            player.cash -= upgrade_cost
            tile.toll = (tile.toll or 0) + max(upgrade_cost // 4, 20)
            return self._append_event(
                session,
                "action.accepted",
                {
                    "player_id": player.player_id,
                    "action": action,
                    "tile_id": tile.tile_id,
                    "upgrade_cost": upgrade_cost,
                    "new_toll": tile.toll,
                },
            )

        if action == "bank_deposit":
            amount = int(args["amount"])
            player.cash -= amount
            player.deposit += amount
            return self._append_event(
                session,
                "action.accepted",
                {
                    "player_id": player.player_id,
                    "action": action,
                    "amount": amount,
                    "cash": player.cash,
                    "deposit": player.deposit,
                },
            )

        if action == "bank_withdraw":
            amount = int(args["amount"])
            player.deposit -= amount
            player.cash += amount
            return self._append_event(
                session,
                "action.accepted",
                {
                    "player_id": player.player_id,
                    "action": action,
                    "amount": amount,
                    "cash": player.cash,
                    "deposit": player.deposit,
                },
            )

        if action == "event_choice":
            tile = self._active_tile(session, player)
            if tile.tile_type != "EVENT":
                return self._append_event(
                    session,
                    "action.rejected",
                    {"player_id": player.player_id, "action": action, "reason": "not_event_tile"},
                )
            choice = str(args.get("choice", "safe"))
            if choice == "safe":
                delta = 80
            else:
                delta = session.rng.choice([220, -150, -240])
            player.cash = max(0, player.cash + delta)
            return self._append_event(
                session,
                "action.accepted",
                {
                    "player_id": player.player_id,
                    "action": action,
                    "choice": choice,
                    "delta": delta,
                    "cash": player.cash,
                },
            )

        if action == "set_route_preference":
            target_tile_id = str(args["target_tile_id"])
            player.route_preference_tile_id = target_tile_id
            session.allowed_actions = self._allowed_actions(session)
            return self._append_event(
                session,
                "action.accepted",
                {
                    "player_id": player.player_id,
                    "action": action,
                    "target_tile_id": target_tile_id,
                },
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
            session.pending_alliances.add((player.player_id, target.player_id))
            return self._append_event(
                session,
                "alliance.proposed",
                {"player_id": player.player_id, "target_player_id": target.player_id},
            )

        if action == "accept_alliance":
            requester_id = str(args["requester_player_id"])
            requester = self._find_player(session, requester_id)
            if (requester.player_id, player.player_id) not in session.pending_alliances:
                return self._append_event(
                    session,
                    "action.rejected",
                    {"player_id": player.player_id, "action": action, "reason": "request_missing"},
                )
            if requester.alliance_with or player.alliance_with:
                return self._append_event(
                    session,
                    "action.rejected",
                    {"player_id": player.player_id, "action": action, "reason": "alliance_busy"},
                )
            session.pending_alliances.discard((requester.player_id, player.player_id))
            requester.alliance_with = player.player_id
            player.alliance_with = requester.player_id
            return self._append_event(
                session,
                "alliance.created",
                {"player_id": player.player_id, "target_player_id": requester.player_id},
            )

        if action == "reject_alliance":
            requester_id = str(args["requester_player_id"])
            session.pending_alliances.discard((requester_id, player.player_id))
            return self._append_event(
                session,
                "alliance.rejected",
                {"player_id": player.player_id, "requester_player_id": requester_id},
            )

        return self._append_event(session, "action.accepted", {"player_id": player.player_id, "action": "pass"})

    def _roll_and_settle(self, session: GameSession, player: Player) -> EventRecord:
        session.current_phase = "TILE_ENTER"
        dice = session.rng.randint(1, 6)
        start_tile_id = self._start_tile_id(session)
        current_tile = self._player_tile(session, player)
        current_tile_id = current_tile.tile_id
        movement_trace = [current_tile_id]
        passed_start_count = 0

        for _ in range(dice):
            tile = self._find_tile(session, current_tile_id)
            next_candidates = self._next_tile_ids(session, tile)
            if not next_candidates:
                break
            chosen_tile_id = self._choose_next_tile(player, next_candidates)
            if chosen_tile_id == start_tile_id:
                passed_start_count += 1
            current_tile_id = chosen_tile_id
            movement_trace.append(current_tile_id)

        if passed_start_count > 0:
            player.cash += 200 * passed_start_count
        player.current_tile_id = current_tile_id
        arrived_tile = self._find_tile(session, current_tile_id)
        player.position = arrived_tile.tile_index
        session.active_tile_id = arrived_tile.tile_id
        session.active_tile_index = arrived_tile.tile_index
        self._append_event(
            session,
            "dice.rolled",
            {
                "player_id": player.player_id,
                "dice": dice,
                "position": player.position,
                "current_tile_id": player.current_tile_id,
                "movement_trace": movement_trace,
                "passed_start": passed_start_count > 0,
                "passed_start_count": passed_start_count,
            },
        )
        session.current_phase = "AUTO_SETTLE"
        settle_event = self._auto_settle(session, player, arrived_tile)
        session.current_phase = "DECISION"
        session.allowed_actions = self._allowed_actions(session)
        return settle_event

    def _auto_settle(self, session: GameSession, player: Player, tile: Tile) -> EventRecord:
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
            if remaining > 0:
                remaining = self._auction_for_debt(session, player, remaining)

            paid = toll - remaining
            owner.cash += paid

            if remaining > 0:
                player.alive = False
                player.alliance_with = None
                for item in session.players:
                    if item.alliance_with == player.player_id:
                        item.alliance_with = None
                return self._append_event(
                    session,
                    "player.bankrupt",
                    {
                        "player_id": player.player_id,
                        "debt": remaining,
                        "tile_id": tile.tile_id,
                        "owner_id": owner.player_id,
                    },
                )

            return self._append_event(
                session,
                "settlement.applied",
                {
                    "player_id": player.player_id,
                    "tile_id": tile.tile_id,
                    "type": "toll_paid",
                    "amount": paid,
                    "owner_id": owner.player_id,
                },
            )

        if tile.tile_type == "EVENT":
            if tile.event_key in {"EVT_BIG", "EVT_RANDOM"}:
                return self._append_event(
                    session,
                    "settlement.applied",
                    {
                        "player_id": player.player_id,
                        "tile_id": tile.tile_id,
                        "type": "event_choice_waiting",
                    },
                )

            delta = session.rng.choice([-120, -40, 100, 180])
            player.cash = max(0, player.cash + delta)
            return self._append_event(
                session,
                "settlement.applied",
                {
                    "player_id": player.player_id,
                    "tile_id": tile.tile_id,
                    "type": "event_delta",
                    "delta": delta,
                    "cash": player.cash,
                },
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

    def _auction_for_debt(self, session: GameSession, debtor: Player, debt: int) -> int:
        if debt <= 0:
            return 0

        for tile_id in list(debtor.property_ids):
            tile = self._find_tile(session, tile_id)
            reserve = max(100, tile.property_price or 200)
            buyers = [
                item
                for item in session.players
                if item.player_id != debtor.player_id and item.alive and item.cash >= reserve
            ]
            if not buyers:
                continue
            buyers.sort(key=lambda item: item.cash, reverse=True)
            buyer = buyers[0]

            buyer.cash -= reserve
            debtor.cash += reserve
            tile.owner_id = buyer.player_id
            debtor.property_ids.remove(tile.tile_id)
            if tile.tile_id not in buyer.property_ids:
                buyer.property_ids.append(tile.tile_id)

            self._append_event(
                session,
                "auction.sold",
                {
                    "tile_id": tile.tile_id,
                    "from_player_id": debtor.player_id,
                    "to_player_id": buyer.player_id,
                    "price": reserve,
                },
            )

            pay_now = min(debtor.cash, debt)
            debtor.cash -= pay_now
            debt -= pay_now
            if debt <= 0:
                return 0

        return debt

    def _allowed_actions(self, session: GameSession) -> list[ActionOption]:
        player = session.players[session.current_player_index]
        if not player.alive:
            return [ActionOption(action="pass", description="Pass")]

        if session.current_phase == "ROLL":
            return [ActionOption(action="roll_dice", description="Roll dice", required_args=[])]

        if session.current_phase != "DECISION":
            return [ActionOption(action="pass", description="Pass", required_args=[])]

        tile = self._active_tile(session, player)
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

        if subtype == "PROPERTY_SELF":
            options.append(
                ActionOption(
                    action="upgrade_property",
                    description="Upgrade property",
                    required_args=["tile_id"],
                    allowed_values={"tile_id": [tile.tile_id]},
                    default_args={"tile_id": tile.tile_id},
                )
            )

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

        if subtype == "EVENT" and tile.event_key in {"EVT_BIG", "EVT_RANDOM"}:
            options.append(
                ActionOption(
                    action="event_choice",
                    description="Choose event option",
                    required_args=["choice"],
                    allowed_values={"choice": ["safe", "risky"]},
                    default_args={"choice": "safe"},
                )
            )

        branch_targets = self._branch_targets_within_steps(session, player, lookahead=6)
        branch_targets = [item for item in branch_targets if item != player.route_preference_tile_id]
        if branch_targets:
            options.append(
                ActionOption(
                    action="set_route_preference",
                    description="Set route preference for nearby branch",
                    required_args=["target_tile_id"],
                    allowed_values={"target_tile_id": branch_targets},
                    default_args={"target_tile_id": branch_targets[0]},
                )
            )

        target_players = [
            item.player_id
            for item in session.players
            if item.player_id != player.player_id and item.alive and item.alliance_with is None
        ]
        if target_players and player.alliance_with is None:
            options.append(
                ActionOption(
                    action="propose_alliance",
                    description="Create alliance",
                    required_args=["target_player_id"],
                    allowed_values={"target_player_id": target_players},
                    default_args={"target_player_id": target_players[0]},
                )
            )

        incoming = [
            requester_id
            for requester_id, target_id in session.pending_alliances
            if target_id == player.player_id
        ]
        if incoming and player.alliance_with is None:
            options.append(
                ActionOption(
                    action="accept_alliance",
                    description="Accept alliance request",
                    required_args=["requester_player_id"],
                    allowed_values={"requester_player_id": sorted(incoming)},
                    default_args={"requester_player_id": sorted(incoming)[0]},
                )
            )
            options.append(
                ActionOption(
                    action="reject_alliance",
                    description="Reject alliance request",
                    required_args=["requester_player_id"],
                    allowed_values={"requester_player_id": sorted(incoming)},
                    default_args={"requester_player_id": sorted(incoming)[0]},
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
                next_tile_ids=self._next_tile_ids(session, item),
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
            active_tile_id=session.active_tile_id or self._player_tile(session, current_player).tile_id,
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
            current_tile_id=player.current_tile_id,
            route_preference_tile_id=player.route_preference_tile_id,
            property_ids=list(player.property_ids),
            alliance_with=player.alliance_with,
            alive=player.alive,
        )

    def _active_tile(self, session: GameSession, player: Player) -> Tile:
        if session.active_tile_id:
            return self._find_tile(session, session.active_tile_id)
        return self._player_tile(session, player)

    def _player_tile(self, session: GameSession, player: Player) -> Tile:
        if player.current_tile_id:
            return self._find_tile(session, player.current_tile_id)
        index = max(0, min(player.position, len(session.board) - 1))
        tile = session.board[index]
        player.current_tile_id = tile.tile_id
        player.position = tile.tile_index
        return tile

    def _tile_index_by_id(self, session: GameSession, tile_id: str) -> int:
        return self._find_tile(session, tile_id).tile_index

    def _start_tile_id(self, session: GameSession) -> str:
        for item in session.board:
            if item.tile_type == "START":
                return item.tile_id
        return session.board[0].tile_id

    def _next_tile_ids(self, session: GameSession, tile: Tile) -> list[str]:
        if tile.next_tile_ids:
            return [item for item in tile.next_tile_ids if any(t.tile_id == item for t in session.board)]
        ordered = sorted(session.board, key=lambda item: item.tile_index)
        index = next((idx for idx, item in enumerate(ordered) if item.tile_id == tile.tile_id), 0)
        next_index = (index + 1) % len(ordered)
        return [ordered[next_index].tile_id]

    def _choose_next_tile(self, player: Player, candidates: list[str]) -> str:
        if player.route_preference_tile_id and player.route_preference_tile_id in candidates:
            return player.route_preference_tile_id
        return candidates[0]

    def _branch_targets_within_steps(self, session: GameSession, player: Player, lookahead: int = 6) -> list[str]:
        if lookahead <= 0:
            return []
        start_tile = self._player_tile(session, player)
        queue: list[tuple[str, int]] = [(start_tile.tile_id, 0)]
        best_depth: dict[str, int] = {start_tile.tile_id: 0}
        targets: set[str] = set()

        while queue:
            tile_id, depth = queue.pop(0)
            if depth >= lookahead:
                continue
            tile = self._find_tile(session, tile_id)
            next_ids = self._next_tile_ids(session, tile)
            if len(next_ids) > 1:
                targets.update(next_ids)
            for next_id in next_ids:
                next_depth = depth + 1
                if next_depth > lookahead:
                    continue
                previous = best_depth.get(next_id)
                if previous is not None and previous <= next_depth:
                    continue
                best_depth[next_id] = next_depth
                queue.append((next_id, next_depth))
        return sorted(targets)

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
        scores = sorted(
            (
                (self._to_player_snapshot(session, item).net_worth, item.player_id)
                for item in session.players
                if item.alive
            ),
            reverse=True,
        )
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
    try:
        rows = load_runtime_board()
        return [
            Tile(
                tile_id=item["tile_id"],
                tile_index=item["tile_index"],
                tile_type=item["tile_type"],
                tile_subtype=item["tile_subtype"],
                name=item["name"],
                property_price=item.get("property_price"),
                toll=item.get("toll"),
                event_key=item.get("event_key"),
                quiz_key=item.get("quiz_key"),
                next_tile_ids=list(item.get("next_tile_ids") or []),
            )
            for item in rows
        ]
    except Exception:
        return _fallback_default_board()


def _fallback_default_board() -> list[Tile]:
    board = [
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
    for index, tile in enumerate(board):
        tile.next_tile_ids = [board[(index + 1) % len(board)].tile_id]
    return board
