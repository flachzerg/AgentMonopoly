import json
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


class ApiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def _create_game(self, game_id: str) -> None:
        response = self.client.post(
            "/games",
            json={
                "game_id": game_id,
                "max_rounds": 12,
                "seed": 2,
                "players": [
                    {"player_id": "p1", "name": "Human", "is_agent": False},
                    {"player_id": "p2", "name": "Bot-2", "is_agent": True},
                    {"player_id": "p3", "name": "Bot-3", "is_agent": True},
                    {"player_id": "p4", "name": "Bot-4", "is_agent": True},
                ],
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_v2_state_replay_summary_flow(self) -> None:
        game_id = f"g-int-{uuid4().hex[:8]}"
        self._create_game(game_id)

        roll = self.client.post(
            f"/games/{game_id}/actions",
            json={
                "game_id": game_id,
                "player_id": "p1",
                "action": "roll_dice",
                "args": {},
            },
        )
        self.assertEqual(roll.status_code, 200)
        self.assertTrue(roll.json()["accepted"])

        choose = self.client.post(
            f"/games/{game_id}/actions",
            json={
                "game_id": game_id,
                "player_id": "p1",
                "action": "buy_property",
                "args": {"tile_id": "T01"},
            },
        )
        self.assertEqual(choose.status_code, 200)
        self.assertTrue(choose.json()["accepted"])

        auto = self.client.post(f"/games/{game_id}/auto-play?max_steps=10")
        self.assertEqual(auto.status_code, 200)
        auto_body = auto.json()
        self.assertIn("steps", auto_body)
        self.assertIn("state", auto_body)
        self.assertIn("stopped_reason", auto_body)

        state_resp = self.client.get(f"/games/{game_id}/state")
        self.assertEqual(state_resp.status_code, 200)
        self.assertIn("state", state_resp.json())

        replay_resp = self.client.get(f"/games/{game_id}/replay")
        self.assertEqual(replay_resp.status_code, 200)
        replay_body = replay_resp.json()
        self.assertIn("steps", replay_body)

        summary_resp = self.client.get(f"/games/{game_id}/summary")
        self.assertEqual(summary_resp.status_code, 200)
        summary = summary_resp.json()
        self.assertIn("metrics", summary)
        self.assertIn("markdown", summary)

        export_resp = self.client.get(f"/games/{game_id}/replay/export")
        self.assertEqual(export_resp.status_code, 200)
        lines = [line for line in export_resp.text.splitlines() if line.strip()]
        self.assertGreater(len(lines), 0)
        first = json.loads(lines[0])
        self.assertIn("type", first)

    def test_auto_play_stops_on_human_turn(self) -> None:
        game_id = f"g-auto-{uuid4().hex[:8]}"
        self._create_game(game_id)

        self.client.post(
            f"/games/{game_id}/actions",
            json={"game_id": game_id, "player_id": "p1", "action": "roll_dice", "args": {}},
        )
        self.client.post(
            f"/games/{game_id}/actions",
            json={"game_id": game_id, "player_id": "p1", "action": "pass", "args": {}},
        )

        auto = self.client.post(f"/games/{game_id}/auto-play?max_steps=20")
        self.assertEqual(auto.status_code, 200)
        body = auto.json()
        self.assertGreaterEqual(body["steps"], 1)
        self.assertIn(body["stopped_reason"], {"human_turn", "game_finished", "max_steps"})
        if body["stopped_reason"] == "human_turn":
            self.assertEqual(body["state"]["current_player_id"], "p1")


if __name__ == "__main__":
    unittest.main()
