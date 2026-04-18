from __future__ import annotations

import json
import unittest

from app.agent_runtime import (
    AgentRuntime,
    ModelTimeoutError,
    OutputParseError,
    TurnBuildInput,
    parse_turn_output,
)
from app.schemas import (
    ActionOption,
    BoardSnapshot,
    BoardTileSnapshot,
    OutputContract,
    PlayerSnapshot,
    TileContext,
    TurnMeta,
)


class StubModel:
    def __init__(self, replies: list[str | Exception], model_tag: str = "stub-model") -> None:
        self.replies = replies
        self.calls = 0
        self.model_tag = model_tag

    def generate(self, prompt: str, output_contract: OutputContract, timeout_sec: float) -> str:
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        if isinstance(reply, Exception):
            raise reply
        return reply


class AgentRuntimeTests(unittest.TestCase):
    def _build_payload(self) -> TurnBuildInput:
        turn_meta = TurnMeta(
            game_id="g1",
            round_index=2,
            turn_index=3,
            current_player_id="p1",
            tile_subtype="PROPERTY_UNOWNED",
        )
        tile_context = TileContext(
            tile_id="T01",
            tile_index=1,
            tile_type="PROPERTY",
            tile_subtype="PROPERTY_UNOWNED",
            property_price=200,
            toll=40,
        )
        player = PlayerSnapshot(
            player_id="p1",
            name="A",
            is_agent=True,
            cash=2000,
            deposit=500,
            net_worth=2500,
            position=1,
            property_ids=[],
            alliance_with=None,
            alive=True,
        )
        players = [
            player,
            PlayerSnapshot(
                player_id="p2",
                name="B",
                is_agent=True,
                cash=1800,
                deposit=300,
                net_worth=2100,
                position=4,
                property_ids=[],
                alliance_with=None,
                alive=True,
            ),
        ]
        board = BoardSnapshot(
            track_length=2,
            tiles=[
                BoardTileSnapshot(
                    tile_id="T00",
                    tile_index=0,
                    tile_type="START",
                    tile_subtype="START",
                ),
                BoardTileSnapshot(
                    tile_id="T01",
                    tile_index=1,
                    tile_type="PROPERTY",
                    tile_subtype="PROPERTY",
                    property_price=200,
                    toll=40,
                ),
            ],
        )
        options = [
            ActionOption(
                action="buy_property",
                description="Buy",
                required_args=["tile_id"],
                allowed_values={"tile_id": ["T01"]},
                default_args={"tile_id": "T01"},
            ),
            ActionOption(action="skip_buy", description="Skip"),
            ActionOption(action="pass", description="Pass"),
        ]
        return TurnBuildInput(
            turn_meta=turn_meta,
            tile_context=tile_context,
            player_state=player,
            players_snapshot=players,
            board_snapshot=board,
            options=options,
        )

    def test_build_turn_input_has_required_fields(self) -> None:
        runtime = AgentRuntime(model=StubModel(["{}"]))
        turn_input = runtime.build_turn_input(self._build_payload())
        self.assertEqual(turn_input.protocol, "DY-MONO-TURN-IN/3.1")
        self.assertEqual(turn_input.output_contract.protocol, "DY-MONO-TURN-OUT/3.1")
        self.assertTrue(turn_input.output_contract.json_only)
        self.assertEqual(turn_input.turn_meta.chain[0], "ROLL")
        self.assertEqual(turn_input.turn_meta.chain[-1], "LOG")

    def test_parse_output_rejects_extra_fields(self) -> None:
        with self.assertRaises(OutputParseError):
            parse_turn_output(
                raw=json.dumps(
                    {
                        "protocol": "DY-MONO-TURN-OUT/3.1",
                        "action": "pass",
                        "args": {},
                        "illegal_field": 1,
                    }
                ),
                output_contract=OutputContract(),
                options=[ActionOption(action="pass", description="Pass")],
            )

    def test_timeout_retry_and_fallback(self) -> None:
        model = StubModel([ModelTimeoutError("t1"), ModelTimeoutError("t2"), ModelTimeoutError("t3")])
        runtime = AgentRuntime(model=model)
        turn_input = runtime.build_turn_input(self._build_payload())

        envelope = runtime.decide(turn_input)

        self.assertEqual(envelope.audit.status, "fallback")
        self.assertIn("timeout", envelope.audit.failure_codes)
        self.assertEqual(envelope.decision.action, "pass")
        self.assertGreaterEqual(envelope.audit.attempt_count, 1)

    def test_illegal_action_downgrade(self) -> None:
        bad = json.dumps(
            {
                "protocol": "DY-MONO-TURN-OUT/3.1",
                "action": "hack_server",
                "args": {},
                "thought": "bad",
            }
        )
        runtime = AgentRuntime(model=StubModel([bad]))
        turn_input = runtime.build_turn_input(self._build_payload())

        envelope = runtime.decide(turn_input)

        self.assertEqual(envelope.audit.status, "fallback")
        self.assertIn("illegal_action", envelope.audit.failure_codes)
        self.assertEqual(envelope.decision.action, "pass")

    def test_audit_contains_hash_tag_and_final_decision(self) -> None:
        ok = json.dumps(
            {
                "protocol": "DY-MONO-TURN-OUT/3.1",
                "action": "buy_property",
                "args": {"tile_id": "T01"},
                "thought": "buy",
                "strategy_tags": ["expansion"],
                "candidate_actions": ["buy_property", "skip_buy", "pass"],
                "confidence": 0.8,
            }
        )
        runtime = AgentRuntime(model=StubModel([ok], model_tag="stub-v2"))
        turn_input = runtime.build_turn_input(self._build_payload())

        envelope = runtime.decide(turn_input)

        self.assertEqual(envelope.audit.status, "ok")
        self.assertEqual(envelope.audit.model_tag, "stub-v2")
        self.assertTrue(envelope.audit.prompt_hash)
        self.assertEqual(envelope.audit.final_decision.action, "buy_property")


if __name__ == "__main__":
    unittest.main()
