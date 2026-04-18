import concurrent.futures
import unittest

from app.game_engine import GameManager
from app.schemas import PlayerConfig


def _run_one_game(game_idx: int) -> dict:
    manager = GameManager()
    game_id = f"g-conc-{game_idx}"
    manager.create_game(
        game_id=game_id,
        max_rounds=20,
        seed=game_idx + 11,
        players=[
            PlayerConfig(player_id="p1", name="A", is_agent=True),
            PlayerConfig(player_id="p2", name="B", is_agent=True),
            PlayerConfig(player_id="p3", name="C", is_agent=True),
            PlayerConfig(player_id="p4", name="D", is_agent=True),
        ],
    )

    for _ in range(120):
        state = manager.state(game_id)
        if state.status == "finished":
            break
        current = state.current_player_id
        if state.current_phase == "ROLL":
            manager.apply_action(game_id, current, "roll_dice", {})
            continue

        state = manager.state(game_id)
        if state.current_phase == "DECISION":
            if not state.allowed_actions:
                continue
            manager.apply_action(game_id, current, state.allowed_actions[0].action, {})

    result = manager.state(game_id)
    alive = sum(1 for item in result.players if item.alive)
    return {"round_index": result.round_index, "alive_count": alive}


class ConcurrencySimulationTestCase(unittest.TestCase):
    def test_multi_game_parallel(self) -> None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_run_one_game, i) for i in range(16)]
            results = [f.result(timeout=30) for f in futures]
        self.assertEqual(len(results), 16)
        self.assertTrue(all(r["round_index"] >= 2 for r in results))


if __name__ == "__main__":
    unittest.main()
