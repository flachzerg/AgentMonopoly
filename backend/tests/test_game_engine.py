import unittest

from app.game_engine import (
    get_next_phase,
    initialize_game_state,
    run_game_turn,
    run_turn,
    validate_phase_action,
)
from app.schemas import ActionCommand, ActionType, ErrorCode, Phase, TileType, TurnInputV31


class GameEngineTestCase(unittest.TestCase):
    def test_phase_transition_roll_to_tile_enter(self) -> None:
        self.assertEqual(get_next_phase(Phase.ROLL), Phase.TILE_ENTER)

    def test_illegal_action_for_phase(self) -> None:
        is_valid, error_code = validate_phase_action(Phase.ROLL, ActionType.BUY_PROPERTY)
        self.assertFalse(is_valid)
        self.assertEqual(error_code, ErrorCode.ILLEGAL_ACTION_FOR_PHASE)

    def test_run_turn_roll_with_dice(self) -> None:
        turn_input = TurnInputV31(
            game_id="g1",
            player_id="p1",
            phase=Phase.ROLL,
            command=ActionCommand(action=ActionType.ROLL_DICE),
        )
        output = run_turn(turn_input)
        self.assertTrue(output.output_contract.accepted)
        self.assertEqual(output.next_phase, Phase.TILE_ENTER)
        self.assertTrue(any(e.event_type == "dice.rolled" for e in output.events))

    def test_empty_tile_flow(self) -> None:
        board = [
            {"type": TileType.START, "reward": 200},
            {"type": TileType.EMPTY},
        ]
        state = initialize_game_state("g-empty", ["p1", "p2"], board=board)
        result = run_game_turn(state, "p1", ActionCommand(action=ActionType.PASS), dice_value=1)
        self.assertTrue(any(e.event_type == "empty.entered" for e in result.events))

    def test_bank_deposit_and_withdraw(self) -> None:
        board = [
            {"type": TileType.START, "reward": 200},
            {"type": TileType.BANK},
        ]
        state = initialize_game_state("g-bank", ["p1", "p2"], board=board)
        run_game_turn(
            state,
            "p1",
            ActionCommand(action=ActionType.BANK_DEPOSIT, params={"amount": 100}),
            dice_value=1,
        )
        self.assertEqual(state["players"]["p1"]["deposit"], 100)
        run_game_turn(
            state,
            "p1",
            ActionCommand(action=ActionType.BANK_WITHDRAW, params={"amount": 80}),
            dice_value=0,
        )
        self.assertEqual(state["players"]["p1"]["deposit"], 20)

    def test_event_auto_and_choice(self) -> None:
        board = [
            {"type": TileType.START, "reward": 200},
            {"type": TileType.EVENT, "event_mode": "auto", "delta": 50},
            {"type": TileType.EVENT, "event_mode": "choice", "choices": {"safe": 20, "risky": -60}},
        ]
        state = initialize_game_state("g-event", ["p1", "p2"], board=board)
        base_cash = state["players"]["p1"]["cash"]
        run_game_turn(state, "p1", ActionCommand(action=ActionType.PASS), dice_value=1)
        self.assertEqual(state["players"]["p1"]["cash"], base_cash + 50)
        run_game_turn(
            state,
            "p1",
            ActionCommand(action=ActionType.EVENT_CHOICE, params={"choice": "safe"}),
            dice_value=1,
        )
        self.assertGreaterEqual(state["players"]["p1"]["cash"], base_cash + 70)

    def test_property_unowned_buy_and_self_upgrade(self) -> None:
        board = [
            {"type": TileType.START, "reward": 200},
            {"type": TileType.PROPERTY, "base_price": 150, "upgrade_cost": 100, "toll_base": 60},
        ]
        state = initialize_game_state("g-prop", ["p1", "p2"], board=board)
        run_game_turn(state, "p1", ActionCommand(action=ActionType.BUY_PROPERTY), dice_value=1)
        self.assertEqual(state["board"][1]["owner_id"], "p1")
        run_game_turn(state, "p1", ActionCommand(action=ActionType.UPGRADE_PROPERTY), dice_value=0)
        self.assertEqual(state["board"][1]["level"], 1)

    def test_property_ally_waive_toll(self) -> None:
        board = [
            {"type": TileType.START, "reward": 200},
            {"type": TileType.PROPERTY, "base_price": 150, "upgrade_cost": 100, "toll_base": 60, "owner_id": "p2"},
        ]
        state = initialize_game_state("g-ally", ["p1", "p2"], board=board)
        state["alliances"]["p1"] = "p2"
        state["alliances"]["p2"] = "p1"
        before_cash = state["players"]["p1"]["cash"]
        result = run_game_turn(state, "p1", ActionCommand(action=ActionType.PASS), dice_value=1)
        self.assertTrue(any(e.event_type == "toll.waived" for e in result.events))
        self.assertEqual(state["players"]["p1"]["cash"], before_cash)

    def test_property_toll_with_auction_trail(self) -> None:
        board = [
            {"type": TileType.START, "reward": 200},
            {"type": TileType.PROPERTY, "base_price": 300, "upgrade_cost": 100, "toll_base": 220, "owner_id": "p2"},
            {"type": TileType.PROPERTY, "base_price": 150, "upgrade_cost": 50, "toll_base": 40, "owner_id": "p1"},
        ]
        state = initialize_game_state("g-auction", ["p1", "p2", "p3"], board=board)
        state["players"]["p1"]["cash"] = 20
        state["players"]["p1"]["deposit"] = 10
        state["players"]["p1"]["position"] = 0
        state["players"]["p1"]["properties"] = [2]
        state["players"]["p3"]["cash"] = 500
        result = run_game_turn(state, "p1", ActionCommand(action=ActionType.PASS), dice_value=1)
        event_types = [e.event_type for e in result.events]
        self.assertIn("insolvent.triggered", event_types)
        self.assertIn("auction.sold", event_types)

    def test_property_toll_bankrupt_trail(self) -> None:
        board = [
            {"type": TileType.START, "reward": 200},
            {"type": TileType.PROPERTY, "base_price": 300, "upgrade_cost": 100, "toll_base": 600, "owner_id": "p2"},
        ]
        state = initialize_game_state("g-bankrupt", ["p1", "p2"], board=board)
        state["players"]["p1"]["cash"] = 10
        state["players"]["p1"]["deposit"] = 0
        result = run_game_turn(state, "p1", ActionCommand(action=ActionType.PASS), dice_value=1)
        self.assertTrue(any(e.event_type == "player.bankrupt" for e in result.events))
        self.assertFalse(state["players"]["p1"]["alive"])


if __name__ == "__main__":
    unittest.main()
