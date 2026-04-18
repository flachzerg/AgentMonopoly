import json
import unittest

from fastapi.testclient import TestClient
from sqlmodel import delete

from app.db import create_db_and_tables, get_session
from app.main import app
from app.models import Action, Alliance, EventLog, Game, GameSnapshot, IdempotencyRecord, Player, Property


class ApiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        create_db_and_tables()
        cls.client = TestClient(app)

    def setUp(self) -> None:
        with get_session() as session:
            session.exec(delete(IdempotencyRecord))
            session.exec(delete(Action))
            session.exec(delete(EventLog))
            session.exec(delete(GameSnapshot))
            session.exec(delete(Alliance))
            session.exec(delete(Property))
            session.exec(delete(Player))
            session.exec(delete(Game))
            session.commit()

    def test_start_turn_state_replay_flow(self) -> None:
        start_resp = self.client.post(
            "/games/start",
            json={"game_id": "g-int-1", "player_ids": ["p1", "p2", "p3"], "start_cash": 1000},
        )
        self.assertEqual(start_resp.status_code, 200)

        turn_resp = self.client.post(
            "/games/g-int-1/turn",
            json={"player_id": "p1", "action": "pass", "params": {}, "dice_value": 1},
        )
        self.assertEqual(turn_resp.status_code, 200)
        body = turn_resp.json()
        self.assertIn("events", body)
        self.assertGreater(len(body["events"]), 0)

        state_resp = self.client.get("/games/g-int-1/state")
        self.assertEqual(state_resp.status_code, 200)
        self.assertIn("players", state_resp.json())

        replay_resp = self.client.get("/games/g-int-1/replay")
        self.assertEqual(replay_resp.status_code, 200)
        self.assertGreater(replay_resp.json()["count"], 0)

        export_resp = self.client.get("/games/g-int-1/replay/export")
        self.assertEqual(export_resp.status_code, 200)
        lines = [line for line in export_resp.text.splitlines() if line.strip()]
        self.assertGreater(len(lines), 0)
        first = json.loads(lines[0])
        self.assertIn("event_type", first)

    def test_turn_idempotency(self) -> None:
        self.client.post("/games/start", json={"game_id": "g-int-2", "player_ids": ["p1", "p2"]})
        payload = {
            "player_id": "p1",
            "action": "pass",
            "params": {},
            "dice_value": 2,
            "idempotency_key": "k1",
        }
        r1 = self.client.post("/games/g-int-2/turn", json=payload)
        r2 = self.client.post("/games/g-int-2/turn", json=payload)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json(), r2.json())


if __name__ == "__main__":
    unittest.main()
