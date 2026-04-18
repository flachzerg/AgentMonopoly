import unittest

from app.game_engine import GameManager
from app.schemas import PlayerConfig


class GameEngineTestCase(unittest.TestCase):
    def _new_manager(self) -> GameManager:
        return GameManager()

    def _create_game(self, manager: GameManager, game_id: str, seed: int = 2) -> None:
        manager.create_game(
            game_id=game_id,
            max_rounds=12,
            seed=seed,
            players=[
                PlayerConfig(player_id="p1", name="A", is_agent=False),
                PlayerConfig(player_id="p2", name="B", is_agent=False),
                PlayerConfig(player_id="p3", name="C", is_agent=False),
            ],
        )

    def test_roll_then_enter_decision_phase(self) -> None:
        manager = self._new_manager()
        self._create_game(manager, "g-phase", seed=3)

        before = manager.state("g-phase")
        self.assertEqual(before.current_phase, "ROLL")
        self.assertEqual(before.allowed_actions[0].action, "roll_dice")

        accepted, _, event = manager.apply_action("g-phase", "p1", "roll_dice", {})
        self.assertTrue(accepted)
        self.assertIsNotNone(event)

        after = manager.state("g-phase")
        self.assertEqual(after.current_phase, "DECISION")
        self.assertGreater(len(after.allowed_actions), 0)

    def test_buy_property_and_turn_rotate(self) -> None:
        manager = self._new_manager()
        self._create_game(manager, "g-buy", seed=2)

        manager.apply_action("g-buy", "p1", "roll_dice", {})
        state = manager.state("g-buy")
        self.assertEqual(state.current_phase, "DECISION")
        self.assertIn("buy_property", [item.action for item in state.allowed_actions])

        accepted, _, _ = manager.apply_action("g-buy", "p1", "buy_property", {"tile_id": "T01"})
        self.assertTrue(accepted)

        next_state = manager.state("g-buy")
        owner = next(item.owner_id for item in next_state.board if item.tile_id == "T01")
        self.assertEqual(owner, "p1")
        self.assertEqual(next_state.current_player_id, "p2")
        self.assertEqual(next_state.current_phase, "ROLL")

    def test_bank_withdraw_changes_balance(self) -> None:
        manager = self._new_manager()
        self._create_game(manager, "g-bank", seed=7)

        manager.apply_action("g-bank", "p1", "roll_dice", {})
        state = manager.state("g-bank")
        self.assertIn("bank_withdraw", [item.action for item in state.allowed_actions])

        before = next(item for item in state.players if item.player_id == "p1")
        accepted, _, _ = manager.apply_action("g-bank", "p1", "bank_withdraw", {"amount": 100})
        self.assertTrue(accepted)

        after_state = manager.state("g-bank")
        after = next(item for item in after_state.players if item.player_id == "p1")
        self.assertEqual(after.cash, before.cash + 100)
        self.assertEqual(after.deposit, before.deposit - 100)

    def test_alliance_propose_and_accept(self) -> None:
        manager = self._new_manager()
        self._create_game(manager, "g-ally", seed=2)

        manager.apply_action("g-ally", "p1", "roll_dice", {})
        accepted, _, _ = manager.apply_action("g-ally", "p1", "propose_alliance", {"target_player_id": "p2"})
        self.assertTrue(accepted)

        manager.apply_action("g-ally", "p2", "roll_dice", {})
        state = manager.state("g-ally")
        self.assertIn("accept_alliance", [item.action for item in state.allowed_actions])

        accepted, _, _ = manager.apply_action("g-ally", "p2", "accept_alliance", {"requester_player_id": "p1"})
        self.assertTrue(accepted)

        final_state = manager.state("g-ally")
        p1 = next(item for item in final_state.players if item.player_id == "p1")
        p2 = next(item for item in final_state.players if item.player_id == "p2")
        self.assertEqual(p1.alliance_with, "p2")
        self.assertEqual(p2.alliance_with, "p1")

    def test_property_toll_can_bankrupt_player(self) -> None:
        manager = self._new_manager()
        self._create_game(manager, "g-bankrupt", seed=2)

        session = manager.get_game("g-bankrupt")
        owner = session.players[1]
        owner.player_id = "p2"
        tile = session.board[1]
        tile.owner_id = "p2"
        tile.toll = 400
        owner.property_ids = [tile.tile_id]

        debtor = session.players[0]
        debtor.cash = 10
        debtor.deposit = 0

        manager.apply_action("g-bankrupt", "p1", "roll_dice", {})
        state = manager.state("g-bankrupt")
        p1 = next(item for item in state.players if item.player_id == "p1")
        self.assertFalse(p1.alive)


if __name__ == "__main__":
    unittest.main()
