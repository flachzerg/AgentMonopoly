import { useEffect, useRef, type FC } from "react";

import type { EventRecord } from "../types/game";
import {
  getEventLabel,
  getEventParticipants,
  getEventSeverity,
  getEventSummary,
} from "../lib/eventPresentation";

type Props = {
  events: EventRecord[];
  title?: string;
  playerNameMap?: Record<string, string>;
  emptyText?: string;
  compact?: boolean;
};

export const EventTimeline: FC<Props> = ({
  events,
  title = "事件时间线",
  playerNameMap = {},
  emptyText = "暂无事件。",
  compact = false,
}) => {
  const latest = [...events].slice(-40);
  const timelineRef = useRef<HTMLDivElement | null>(null);
  const rootClassName = compact ? "event-timeline" : "panel event-timeline";

  useEffect(() => {
    const element = timelineRef.current;
    if (!element) {
      return;
    }
    element.scrollTop = element.scrollHeight;
  }, [latest.length]);

  return (
    <section className={rootClassName}>
      <h2>{title}</h2>
      <div ref={timelineRef} className="timeline">
        {latest.length === 0 ? (
          <p className="muted">{emptyText}</p>
        ) : (
          latest.map((event) => (
            <article
              key={event.event_id}
              className={`timeline-item timeline-item--${getEventSeverity(event)}`}
            >
              <header>
                <span className="event-type">{getEventLabel(event)}</span>
                <span className="event-round">
                  R{event.round_index} T{event.turn_index}
                </span>
              </header>
              <p className="event-players">参与方：{getEventParticipants(event, playerNameMap)}</p>
              <p className="event-summary">{getEventSummary(event, playerNameMap)}</p>
              <details>
                <summary>查看 details</summary>
                <pre>{JSON.stringify(event.payload, null, 2)}</pre>
              </details>
            </article>
          ))
        )}
      </div>
    </section>
  );
};
