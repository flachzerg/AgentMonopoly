from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


class ReplaySummaryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_replay_and_summary_endpoints(self) -> None:
        game_id = f"replay-{uuid4().hex[:8]}"
        create_payload = {
            "game_id": game_id,
            "max_rounds": 6,
            "seed": 123,
            "players": [
                {"player_id": "p1", "name": "A", "is_agent": True},
                {"player_id": "p2", "name": "B", "is_agent": True},
                {"player_id": "p3", "name": "C", "is_agent": True},
                {"player_id": "p4", "name": "D", "is_agent": True},
            ],
        }
        create_response = self.client.post("/games", json=create_payload)
        self.assertEqual(create_response.status_code, 200)

        roll_response = self.client.post(
            f"/games/{game_id}/actions",
            json={
                "game_id": game_id,
                "player_id": "p1",
                "action": "roll_dice",
                "args": {},
            },
        )
        self.assertEqual(roll_response.status_code, 200)
        self.assertTrue(roll_response.json()["accepted"])

        act_response = self.client.post(f"/games/{game_id}/agent/p1/act")
        self.assertEqual(act_response.status_code, 200)

        replay_response = self.client.get(f"/games/{game_id}/replay")
        self.assertEqual(replay_response.status_code, 200)
        replay = replay_response.json()
        self.assertGreaterEqual(replay["total_turns"], 1)
        self.assertIn("phase_trace", replay["steps"][0])
        self.assertIn("candidate_actions", replay["steps"][0])
        self.assertIn("final_action", replay["steps"][0])

        summary_response = self.client.get(f"/games/{game_id}/summary")
        self.assertEqual(summary_response.status_code, 200)
        summary = summary_response.json()
        self.assertIn("metrics", summary)
        self.assertIn("strategy_timeline", summary)
        self.assertIn("markdown", summary)
        self.assertIn("fallback_ratio", summary["metrics"])


if __name__ == "__main__":
    unittest.main()
