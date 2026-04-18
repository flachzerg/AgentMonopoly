import concurrent.futures
import time

from app.game_engine import initialize_game_state, run_game_turn
from app.schemas import ActionCommand, ActionType


def simulate_game(game_idx: int, rounds: int = 30) -> dict:
    state = initialize_game_state(
        game_id=f"load-{game_idx}",
        player_ids=["p1", "p2", "p3", "p4"],
    )
    start = time.perf_counter()
    for _ in range(rounds):
        for pid in state["player_order"]:
            run_game_turn(state, pid, ActionCommand(action=ActionType.PASS))
    latency_ms = (time.perf_counter() - start) * 1000
    return {"game_id": state["game_id"], "latency_ms": latency_ms}


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
