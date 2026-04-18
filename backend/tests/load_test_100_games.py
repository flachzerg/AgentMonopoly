import concurrent.futures
import time

from app.game_engine import GameManager
from app.schemas import PlayerConfig


def simulate_game(game_idx: int, rounds: int = 30) -> dict:
    manager = GameManager()
    game_id = f"load-{game_idx}"
    manager.create_game(
        game_id=game_id,
        max_rounds=rounds,
        seed=20260418 + game_idx,
        players=[
            PlayerConfig(player_id="p1", name="A", is_agent=True),
            PlayerConfig(player_id="p2", name="B", is_agent=True),
            PlayerConfig(player_id="p3", name="C", is_agent=True),
            PlayerConfig(player_id="p4", name="D", is_agent=True),
        ],
    )

    start = time.perf_counter()
    for _ in range(rounds * 8):
        state = manager.state(game_id)
        if state.status == "finished":
            break
        current = state.current_player_id
        if state.current_phase == "ROLL":
            manager.apply_action(game_id, current, "roll_dice", {})
        else:
            manager.apply_action(game_id, current, "pass", {})

    latency_ms = (time.perf_counter() - start) * 1000
    return {"game_id": game_id, "latency_ms": latency_ms}


def main() -> None:
    total_games = 100
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(simulate_game, i) for i in range(total_games)]
        results = [f.result() for f in futures]

    latencies = sorted([r["latency_ms"] for r in results])
    p95 = latencies[int(len(latencies) * 0.95) - 1]
    avg = sum(latencies) / len(latencies)
    print(f"simulated_games={total_games}")
    print(f"avg_latency_ms={avg:.2f}")
    print(f"p95_latency_ms={p95:.2f}")


if __name__ == "__main__":
    main()
