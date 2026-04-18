import { useEffect, useMemo, useState, type FC } from "react";

import type { AgentContextPacket, DecisionAudit, EventRecord, GameState } from "../types/game";

type Props = {
  state: GameState;
  timeline: EventRecord[];
  activeAudit: DecisionAudit | null;
  activeContext: AgentContextPacket | null;
  wsStatus: "idle" | "connecting" | "online" | "offline";
  error: string | null;
};

type DecisionHistoryItem = {
  key: string;
  turn: number;
  title: string;
  actor: string;
  summary: string;
  reasoning: string;
  status: string;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function pickString(source: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }
  }
  return null;
}

function pickActionTitle(eventType: string, payload: Record<string, unknown>): string {
  return pickString(payload, ["action", "action_type", "decision", "type"]) ?? eventType;
}

function pickSummary(payload: Record<string, unknown>): string {
  return (
    pickString(payload, ["summary", "message", "desc", "description", "reason", "result"]) ??
    "当前事件没有额外摘要，系统正在推进下一步。"
  );
}

function buildHistory(state: GameState, timeline: EventRecord[], activeAudit: DecisionAudit | null): DecisionHistoryItem[] {
  const nameMap = state.players.reduce<Record<string, string>>((acc, player) => {
    acc[player.player_id] = player.name || player.player_id;
    return acc;
  }, {});

  const items: DecisionHistoryItem[] = [];

  if (activeAudit) {
    items.push({
      key: `audit-${state.turn_index}-${state.current_player_id}`,
      turn: state.turn_index,
      title: activeAudit.final_decision.action || "决策执行",
      actor: nameMap[state.current_player_id] ?? state.current_player_id,
      summary: activeAudit.raw_response_summary || "当前决策摘要缺失，等待系统补充。",
      reasoning:
        activeAudit.final_decision.thought ||
        (activeAudit.final_decision.strategy_tags.length > 0
          ? `策略标签：${activeAudit.final_decision.strategy_tags.join(" / ")}`
          : "当前决策没有额外思考记录。"),
      status: activeAudit.status,
    });
  }

  const latestEvents = [...timeline].slice(-40).reverse();
  for (const event of latestEvents) {
    const payload = asRecord(event.payload);
    const actorId = pickString(payload, ["player_id", "acting_player_id", "actor", "current_player_id"]);
    const actor = actorId ? nameMap[actorId] ?? actorId : nameMap[state.current_player_id] ?? state.current_player_id;
    const reasoning =
      pickString(payload, ["reasoning_short", "reasoning", "basis", "decision_basis"]) ??
      "当前事件没有显式决策依据，按系统默认规则执行。";

    items.push({
      key: event.event_id,
      turn: event.turn_index,
      title: pickActionTitle(event.type, payload),
      actor,
      summary: pickSummary(payload),
      reasoning,
      status: event.type,
    });
  }

  if (items.length === 0) {
    items.push({
      key: "fallback-current",
      turn: state.turn_index,
      title: "等待下一步动作",
      actor: nameMap[state.current_player_id] ?? state.current_player_id,
      summary: "当前暂无可展示历史动作，系统会在新事件到达后自动刷新。",
      reasoning: "暂无决策依据。",
      status: state.status,
    });
  }

  return items;
}

function getExecutionState(state: GameState, wsStatus: Props["wsStatus"], error: string | null): "running" | "paused" | "error" {
  if (error || wsStatus === "offline") {
    return "error";
  }
  if (state.status === "running" && !state.waiting_for_human) {
    return "running";
  }
  return "paused";
}

export const DecisionCenter: FC<Props> = ({ state, timeline, activeAudit, activeContext, wsStatus, error }) => {
  const history = useMemo(() => buildHistory(state, timeline, activeAudit), [state, timeline, activeAudit]);
  const [historyIndex, setHistoryIndex] = useState(0);

  useEffect(() => {
    setHistoryIndex(0);
  }, [history.length, state.turn_index, state.current_player_id]);

  const active = history[Math.min(historyIndex, Math.max(history.length - 1, 0))] ?? history[0];
  const executionState = getExecutionState(state, wsStatus, error);

  return (
    <section className="panel decision-center" aria-label="中央决策台">
      <div className="decision-center__head">
        <p className="tiny-note">中央决策台</p>
        <div className="decision-center__history-nav" role="group" aria-label="历史动作切换">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setHistoryIndex((current) => Math.min(current + 1, history.length - 1))}
            disabled={historyIndex >= history.length - 1}
          >
            上一条
          </button>
          <span>
            {history.length === 0 ? "0 / 0" : `${historyIndex + 1} / ${history.length}`}
          </span>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setHistoryIndex((current) => Math.max(current - 1, 0))}
            disabled={historyIndex <= 0}
          >
            下一条
          </button>
        </div>
      </div>

      <div className="decision-center__primary">
        <div>
          <p className="tiny-note">当前玩家</p>
          <strong>{active?.actor ?? state.current_player_id}</strong>
        </div>
        <div>
          <p className="tiny-note">当前动作</p>
          <strong>{active?.title ?? "等待动作"}</strong>
        </div>
        <div>
          <p className="tiny-note">执行状态</p>
          <span className={`decision-center__status decision-center__status--${executionState}`}>{executionState}</span>
        </div>
      </div>

      <div className="decision-center__summary">
        <p className="tiny-note">动作摘要</p>
        <p>{active?.summary ?? "暂无摘要"}</p>
      </div>

      <div className="decision-center__reasoning">
        <p className="tiny-note">最近决策依据</p>
        <p>{active?.reasoning ?? "暂无决策依据"}</p>
      </div>

      <details className="decision-center__raw">
        <summary>查看深层上下文</summary>
        <pre>
{JSON.stringify(
  {
    turn: active?.turn ?? state.turn_index,
    rawStatus: active?.status ?? state.status,
    wsStatus,
    error,
    audit: activeAudit,
    agent_context: activeContext,
  },
  null,
  2,
)}
        </pre>
      </details>
    </section>
  );
};
