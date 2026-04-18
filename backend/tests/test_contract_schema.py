import unittest

from app.schemas import ActionRequest, ActionResponse, CreateGameRequest, ReplayResponse


class ContractSchemaTestCase(unittest.TestCase):
    def test_action_request_keys_snapshot(self) -> None:
        payload = ActionRequest(
            game_id="g",
            player_id="p",
            action="pass",
            args={},
        ).model_dump()
        self.assertEqual(list(payload.keys()), ["game_id", "player_id", "action", "args"])

    def test_action_response_contract_fields(self) -> None:
        schema = ActionResponse.model_json_schema()
        self.assertIn("accepted", schema["properties"])
        self.assertIn("message", schema["properties"])
        self.assertIn("state", schema["properties"])
        self.assertIn("event", schema["properties"])
        self.assertIn("audit", schema["properties"])

    def test_create_game_contract_fields(self) -> None:
        schema = CreateGameRequest.model_json_schema()
        self.assertIn("game_id", schema["properties"])
        self.assertIn("players", schema["properties"])
        self.assertIn("max_rounds", schema["properties"])
        self.assertIn("seed", schema["properties"])

    def test_replay_contract_fields(self) -> None:
        schema = ReplayResponse.model_json_schema()
        self.assertIn("game_id", schema["properties"])
        self.assertIn("total_turns", schema["properties"])
        self.assertIn("steps", schema["properties"])


if __name__ == "__main__":
    unittest.main()
