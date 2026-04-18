import json

from sqlmodel import select

from app.db import get_session
from app.models import EventLog
from app.schemas import EventEnvelope


class ReplayService:
    def append_events(self, game_id: str, events: list[EventEnvelope]) -> None:
        with get_session() as session:
            for event in events:
                session.add(
                    EventLog(
                        game_id=game_id,
                        round_index=event.round_index,
                        turn_id=event.turn_id,
                        event_type=event.event_type,
                        payload_json=json.dumps(event.model_dump(), ensure_ascii=False),
                        ts=event.ts,
                    )
                )
            session.commit()

    def get_events(
        self,
        game_id: str,
        start_round: int | None = None,
        end_round: int | None = None,
        event_type: str | None = None,
    ) -> list[EventEnvelope]:
        with get_session() as session:
            stmt = select(EventLog).where(EventLog.game_id == game_id)
            if start_round is not None:
                stmt = stmt.where(EventLog.round_index >= start_round)
            if end_round is not None:
                stmt = stmt.where(EventLog.round_index <= end_round)
            if event_type:
                stmt = stmt.where(EventLog.event_type == event_type)
            stmt = stmt.order_by(EventLog.id)  # type: ignore[arg-type]
            rows = session.exec(stmt).all()
            return [EventEnvelope(**json.loads(row.payload_json)) for row in rows]

    def get_events_since(self, game_id: str, since_ts: float) -> list[EventEnvelope]:
        with get_session() as session:
            stmt = (
                select(EventLog)
                .where(EventLog.game_id == game_id)
                .where(EventLog.ts > since_ts)
                .order_by(EventLog.id)  # type: ignore[arg-type]
            )
            rows = session.exec(stmt).all()
            return [EventEnvelope(**json.loads(row.payload_json)) for row in rows]

    def export_events_jsonl(
        self,
        game_id: str,
        start_round: int | None = None,
        end_round: int | None = None,
        event_type: str | None = None,
    ) -> str:
        events = self.get_events(
            game_id=game_id,
            start_round=start_round,
            end_round=end_round,
            event_type=event_type,
        )
        return "\n".join(json.dumps(event.model_dump(), ensure_ascii=False) for event in events)


replay_service = ReplayService()
