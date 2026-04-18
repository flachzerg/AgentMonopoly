from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.schemas import (
    ActionOption,
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
    "bank_deposit",
    "bank_withdraw",
    "propose_alliance",
    "accept_alliance",
    "reject_alliance",
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
            players=[
                Player(
                    player_id=item.player_id,
                    name=item.name,
                    is_agent=item.is_agent,
                )
                for item in players
            ],
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
                {
                    "player_id": player_id,
                    "action": action,
                    "reason": "action_not_allowed",
                },
            )
            return False, "action not allowed", None

        option = next(item for item in session.allowed_actions if item.action == action)
        if not self._validate_args(option, args):
            self._append_event(
                session,
                "action.rejected",
                {
                    "player_id": player_id,
                    "action": action,
                    "reason": "invalid_args",
                    "args": args,
                },
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
            {
                "turn_index": session.turn_index,
                "round_index": session.round_index,
            },
        )

        alive_players = [item for item in session.players if item.alive]
        if session.round_index >= session.max_rounds or len(alive_players) <= 1:
            session.status = "finished"
            session.current_phase = "LOG"
            session.allowed_actions = []
            self._append_event(
                session,
                "game.finished",
                {
                    "winner": self._winner_id(session),
                    "round_index": session.round_index,
                },
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

    def _execute_action(
        self,
        session: GameSession,
        player: Player,
        action: str,
        args: dict[str, Any],
    ) -> EventRecord | None:
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
            return self._append_event(
                session,
                "action.accepted",
                {"player_id": player.player_id, "action": action},
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
                {
                    "player_id": player.player_id,
                    "target_player_id": target.player_id,
                },
            )

        return self._append_event(
            session,
            "action.accepted",
            {"player_id": player.player_id, "action": "pass"},
        )

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
        settle_event = self._auto_settle(session, player, tile)
        session.current_phase = "DECISION"
        session.allowed_actions = self._allowed_actions(session)
        return settle_event

    def _auto_settle(self, session: GameSession, player: Player, tile: Tile) -> EventRecord:
        if tile.tile_type == "PROPERTY" and tile.owner_id and tile.owner_id != player.player_id:
            if player.alliance_with == tile.owner_id:
                return self._append_event(
                    session,
                    "settlement.applied",
                    {
                        "player_id": player.player_id,
                        "tile_id": tile.tile_id,
                        "type": "toll_waived_by_alliance",
                    },
                )
            toll = tile.toll or 0
            owner = self._find_player(session, tile.owner_id)
            remaining = self._pay_amount(player, toll)
            owner.cash += (toll - remaining)
            if remaining > 0:
                player.alive = False
                return self._append_event(
                    session,
                    "player.bankrupt",
                    {
                        "player_id": player.player_id,
                        "debt": remaining,
                        "tile_id": tile.tile_id,
                    },
                )
            return self._append_event(
                session,
                "settlement.applied",
                {
                    "player_id": player.player_id,
                    "tile_id": tile.tile_id,
                    "type": "toll_paid",
                    "amount": toll,
                    "owner_id": owner.player_id,
                },
            )

        if tile.tile_type == "EVENT":
            delta = session.rng.choice([-200, -100, 100, 200, 300])
            player.cash = max(0, player.cash + delta)
            return self._append_event(
                session,
                "settlement.applied",
                {
                    "player_id": player.player_id,
                    "tile_id": tile.tile_id,
                    "type": "event_delta",
                    "delta": delta,
                },
            )

        if tile.tile_type == "BANK":
            return self._append_event(
                session,
                "settlement.applied",
                {
                    "player_id": player.player_id,
                    "tile_id": tile.tile_id,
                    "type": "bank_enter",
                },
            )

        if tile.tile_type == "QUIZ":
            return self._append_event(
                session,
                "quiz.placeholder",
                {
                    "player_id": player.player_id,
                    "tile_id": tile.tile_id,
                    "status": "reserved",
                },
            )

        return self._append_event(
            session,
            "settlement.applied",
            {
                "player_id": player.player_id,
                "tile_id": tile.tile_id,
                "type": "no_effect",
            },
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

        target_players = [
            item.player_id
            for item in session.players
            if item.player_id != player.player_id and item.alive and item.alliance_with is None
        ]
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
            if key not in merged:
                continue
            if merged[key] not in allowed:
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
            status=session.status,
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
    rows = [
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
    return rows
