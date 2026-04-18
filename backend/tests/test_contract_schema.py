import unittest

from app.schemas import (
    ActionCommand,
    ActionType,
    Phase,
    TileType,
    TurnInputV31,
    TurnOutputV31,
)


class ContractSchemaTestCase(unittest.TestCase):
    def test_turn_input_v31_keys_snapshot(self) -> None:
        payload = TurnInputV31(
            game_id="g",
            player_id="p",
            phase=Phase.ROLL,
            tile_type=TileType.EMPTY,
            command=ActionCommand(action=ActionType.ROLL_DICE),
        ).model_dump()
        self.assertEqual(
            list(payload.keys()),
            ["protocol_version", "game_id", "player_id", "turn_id", "round_index", "phase", "tile_type", "command"],
        )

    def test_turn_output_contract_fields_snapshot(self) -> None:
        schema = TurnOutputV31.model_json_schema()
        self.assertIn("output_contract", schema["properties"])
        self.assertIn("events", schema["properties"])
        self.assertIn("snapshot", schema["properties"])


if __name__ == "__main__":
    unittest.main()
