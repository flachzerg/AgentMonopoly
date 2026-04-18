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
        self.assertIn(roll.json()["message"], {"waiting_human_roll", "waiting_human_branch_decision", "game_finished"})

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
        self.assertFalse(choose.json()["accepted"])

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
        self.assertIn("recap", summary)
        self.assertIn("prompt_materials", summary)
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

        auto = self.client.post(f"/games/{game_id}/auto-play?max_steps=20")
        self.assertEqual(auto.status_code, 200)
        body = auto.json()
        self.assertGreaterEqual(body["steps"], 0)
        self.assertIn(body["stopped_reason"], {"waiting_human_roll", "waiting_human_branch_decision", "game_finished", "max_steps"})
        if body["stopped_reason"] == "waiting_human_roll":
            self.assertEqual(body["state"]["current_player_id"], "p1")

    def test_strategy_versions_endpoint(self) -> None:
        game_id = f"g-evo-{uuid4().hex[:8]}"
        response = self.client.post(
            "/games",
            json={
                "game_id": game_id,
                "max_rounds": 4,
                "seed": 19,
                "players": [
                    {"player_id": "p1", "name": "Bot-1", "is_agent": True},
                    {"player_id": "p2", "name": "Bot-2", "is_agent": True},
                    {"player_id": "p3", "name": "Bot-3", "is_agent": True},
                    {"player_id": "p4", "name": "Bot-4", "is_agent": True},
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.client.post(f"/games/{game_id}/auto-play?max_steps=200")

        versions = self.client.get("/games/strategy/versions")
        self.assertEqual(versions.status_code, 200)
        body = versions.json()
        self.assertIn("records", body)
        self.assertGreaterEqual(len(body["records"]), 1)

        model_exp = self.client.get("/games/model-experiences?limit=20")
        self.assertEqual(model_exp.status_code, 200)
        model_body = model_exp.json()
        self.assertIn("records", model_body)
        self.assertGreaterEqual(len(model_body["records"]), 1)

    def test_map_options_and_map_asset_passthrough(self) -> None:
        options = self.client.get("/games/map-options")
        self.assertEqual(options.status_code, 200)
        body = options.json()
        self.assertIn("map_assets", body)
        self.assertIn("default_map_asset", body)
        self.assertIn("05_complex_branch", body["map_assets"])

        game_id = f"g-map-{uuid4().hex[:8]}"
        created = self.client.post(
            "/games",
            json={
                "game_id": game_id,
                "max_rounds": 8,
                "seed": 42,
                "map_asset": "05_complex_branch",
                "players": [
                    {"player_id": "p1", "name": "P1", "is_agent": False},
                    {"player_id": "p2", "name": "P2", "is_agent": True},
                ],
            },
        )
        self.assertEqual(created.status_code, 200)
        created_state = created.json()["state"]
        self.assertEqual(created_state["map_asset"], "05_complex_branch")


if __name__ == "__main__":
    unittest.main()
