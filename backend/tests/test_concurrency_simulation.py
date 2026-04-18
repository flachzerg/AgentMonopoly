import concurrent.futures
import unittest

from app.game_engine import initialize_game_state, run_game_turn
from app.schemas import ActionCommand, ActionType


def _run_one_game(game_idx: int) -> dict:
    state = initialize_game_state(
        game_id=f"g-conc-{game_idx}",
        player_ids=["p1", "p2", "p3", "p4"],
    )
    for _ in range(25):
        for pid in list(state["player_order"]):
            run_game_turn(state, pid, ActionCommand(action=ActionType.PASS))
    return {"round_index": state["round_index"], "alive_count": sum(1 for p in state["players"].values() if p["alive"])}


class ConcurrencySimulationTestCase(unittest.TestCase):
    def test_multi_game_parallel(self) -> None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_run_one_game, i) for i in range(16)]
            results = [f.result(timeout=30) for f in futures]
        self.assertEqual(len(results), 16)
        self.assertTrue(all(r["round_index"] >= 2 for r in results))


if __name__ == "__main__":
    unittest.main()
