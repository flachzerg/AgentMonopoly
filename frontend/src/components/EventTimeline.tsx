import type { FC } from "react";

import type { EventRecord } from "../types/game";

type Props = {
  events: EventRecord[];
};

export const EventTimeline: FC<Props> = ({ events }) => {
  const latest = [...events].slice(-40).reverse();
  return (
    <section className="panel">
      <h2>事件时间线</h2>
      <div className="timeline">
        {latest.length === 0 ? (
          <p className="muted">暂无事件。</p>
        ) : (
          latest.map((event) => (
            <article key={event.event_id} className="timeline-item">
              <header>
                <span className="event-type">{event.type}</span>
                <span className="event-round">
                  R{event.round_index} T{event.turn_index}
                </span>
              </header>
              <pre>{JSON.stringify(event.payload, null, 2)}</pre>
            </article>
          ))
        )}
      </div>
    </section>
  );
};
