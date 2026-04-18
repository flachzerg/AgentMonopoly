import { useMemo, useState, type FC } from "react";

import { buildPlayerNameMap } from "../lib/eventPresentation";
import { getGamePlayerProfiles, inferModelTag } from "../lib/modelAvatar";
import type { ReplayResponse, ReplaySummary } from "../types/game";
import { EventTimeline } from "./EventTimeline";
import { ModelAvatar } from "./ModelAvatar";

type Props = {
  replay: ReplayResponse | null;
  replayIndex: number;
  summary: ReplaySummary | null;
  onLoadReplay: () => Promise<void>;
  onLoadSummary: () => Promise<void>;
  onStep: (direction: "prev" | "next") => void;
  onJumpTurn: (turnIndex: number) => void;
  onExportSummary: (format: "json" | "markdown") => string;
};

type RecapPhase = {
  phase: string;
  summary: string;
  evidence_turns: number[];
};

type TurningPoint = {
  turn: number;
  title: string;
  impact: string;
  evidence_turns: number[];
};

type PlayerProfile = {
  player_id: string;
  style: string;
  highlights: string[];
  issues: string[];
  is_winner: boolean;
};

type RecapView = {
  overview: string;
  phase_analysis: RecapPhase[];
  turning_points: TurningPoint[];
  player_profiles: PlayerProfile[];
  next_game_advice: string[];
};

function asRecord(input: unknown): Record<string, unknown> {
  return input && typeof input === "object" ? (input as Record<string, unknown>) : {};
}

function asStringArray(input: unknown): string[] {
  if (!Array.isArray(input)) {
    return [];
  }
  return input.filter((item): item is string => typeof item === "string");
}

function asNumberArray(input: unknown): number[] {
  if (!Array.isArray(input)) {
    return [];
  }
  return input
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item))
    .map((item) => Math.trunc(item));
}

function buildRecapView(summary: ReplaySummary | null): RecapView | null {
  if (!summary) {
    return null;
  }
  const recap = asRecord(summary.recap);
  const phaseAnalysisRaw = Array.isArray(recap.phase_analysis) ? recap.phase_analysis : [];
  const turningPointsRaw = Array.isArray(recap.turning_points) ? recap.turning_points : [];
  const playerProfilesRaw = Array.isArray(recap.player_profiles) ? recap.player_profiles : [];

  const phase_analysis: RecapPhase[] = phaseAnalysisRaw.map((item) => {
    const row = asRecord(item);
    return {
      phase: typeof row.phase === "string" ? row.phase : "未命名阶段",
      summary: typeof row.summary === "string" ? row.summary : "暂无阶段结论",
      evidence_turns: asNumberArray(row.evidence_turns),
    };
  });

  const turning_points: TurningPoint[] = turningPointsRaw.map((item) => {
    const row = asRecord(item);
    return {
      turn: Number.isFinite(Number(row.turn)) ? Math.trunc(Number(row.turn)) : 0,
      title: typeof row.title === "string" ? row.title : "关键事件",
      impact: typeof row.impact === "string" ? row.impact : "暂无影响说明",
      evidence_turns: asNumberArray(row.evidence_turns),
    };
  });

  const player_profiles: PlayerProfile[] = playerProfilesRaw.map((item) => {
    const row = asRecord(item);
    return {
      player_id: typeof row.player_id === "string" ? row.player_id : "unknown",
      style: typeof row.style === "string" ? row.style : "未定义",
      highlights: asStringArray(row.highlights),
      issues: asStringArray(row.issues),
      is_winner: Boolean(row.is_winner),
    };
  });

  return {
    overview: typeof recap.overview === "string" ? recap.overview : "暂无全局结论",
    phase_analysis,
    turning_points,
    player_profiles,
    next_game_advice: asStringArray(recap.next_game_advice),
  };
}

export const ReplayPanel: FC<Props> = ({
  replay,
  replayIndex,
  summary,
  onLoadReplay,
  onLoadSummary,
  onStep,
  onJumpTurn,
  onExportSummary,
}) => {
  const [jumpInput, setJumpInput] = useState<string>("");
  const [exportText, setExportText] = useState<string>("");
  const recap = useMemo(() => buildRecapView(summary), [summary]);

  const currentStep = useMemo(() => {
    if (!replay || replay.steps.length === 0) {
      return null;
    }
    return replay.steps[Math.min(Math.max(replayIndex, 0), replay.steps.length - 1)];
  }, [replay, replayIndex]);

  const replayPlayerMap = useMemo(() => {
    if (!replay || replay.steps.length === 0) {
      return {} as Record<string, { name: string; is_agent: boolean }>;
    }
    const baseState = replay.steps[Math.max(replay.steps.length - 1, 0)].state;
    return baseState.players.reduce<Record<string, { name: string; is_agent: boolean }>>((acc, player) => {
      acc[player.player_id] = { name: player.name, is_agent: player.is_agent };
      return acc;
    }, {});
  }, [replay]);

  const currentStepPlayerNameMap = useMemo(() => {
    if (!currentStep) {
      return {};
    }
    return buildPlayerNameMap(currentStep.state.players);
  }, [currentStep]);

  const storedProfiles = useMemo(() => {
    const replayGameId = replay?.game_id ?? summary?.game_id ?? "";
    return getGamePlayerProfiles(replayGameId);
  }, [replay?.game_id, summary?.game_id]);

  return (
    <section className="panel replay-panel">
      <div className="panel-title-row">
        <h2>复盘与策略分析</h2>
        <div className="replay-controls-inline">
          <button type="button" className="btn-secondary" onClick={() => onLoadReplay()}>
            拉取 replay
          </button>
          <button type="button" className="btn-secondary" onClick={() => onLoadSummary()}>
            拉取摘要
          </button>
        </div>
      </div>

      {currentStep ? (
        <>
          <div className="replay-controls">
            <button type="button" className="btn-secondary" onClick={() => onStep("prev")}>
              单步后退
            </button>
            <button type="button" className="btn-secondary" onClick={() => onStep("next")}>
              单步前进
            </button>
            <label className="field-inline">
              <span>跳转回合</span>
              <input
                value={jumpInput}
                onChange={(event) => setJumpInput(event.target.value)}
                placeholder="turn index"
              />
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  const value = Number(jumpInput);
                  if (Number.isFinite(value)) {
                    onJumpTurn(value);
                  }
                }}
              >
                跳转
              </button>
            </label>
          </div>

          <div className="compare-grid">
            <article className="replay-event-flow">
              <h3>本手事件流</h3>
              <p className="muted">
                第 {currentStep.turn_index} 手，共 {currentStep.events.length} 条事件。
              </p>
              <EventTimeline
                events={currentStep.events}
                title="语义化事件流"
                playerNameMap={currentStepPlayerNameMap}
                emptyText="该手暂无可展示事件。"
                compact
              />
            </article>
            <article>
              <h3>候选动作</h3>
              <p className="muted">共 {currentStep.candidate_actions.length} 个候选动作。</p>
              <p>{currentStep.candidate_actions.slice(0, 3).join(" / ") || "暂无候选动作"}</p>
              <details>
                <summary>查看原始 JSON</summary>
                <pre>{JSON.stringify(currentStep.candidate_actions, null, 2)}</pre>
              </details>
            </article>
            <article>
              <h3>最终动作</h3>
              <p>{currentStep.final_action ?? "暂无最终动作"}</p>
              <details>
                <summary>查看原始 JSON</summary>
                <pre>{JSON.stringify(currentStep.final_action, null, 2)}</pre>
              </details>
            </article>
            <article>
              <h3>策略标签</h3>
              <p>{currentStep.strategy_tags.join(" / ") || "暂无策略标签"}</p>
              <details>
                <summary>查看原始 JSON</summary>
                <pre>{JSON.stringify(currentStep.strategy_tags, null, 2)}</pre>
              </details>
            </article>
            <article>
              <h3>阶段轨迹</h3>
              <p>{currentStep.phase_trace.join(" -> ") || "暂无阶段轨迹"}</p>
              <details>
                <summary>查看原始 JSON</summary>
                <pre>{JSON.stringify(currentStep.phase_trace, null, 2)}</pre>
              </details>
            </article>
            <article>
              <h3>审计</h3>
              <p>{currentStep.decision_audit?.raw_response_summary ?? "暂无审计摘要"}</p>
              <details>
                <summary>查看原始 JSON</summary>
                <pre>{JSON.stringify(currentStep.decision_audit, null, 2)}</pre>
              </details>
            </article>
          </div>
        </>
      ) : (
        <p className="muted">暂无 replay 数据。</p>
      )}

      {recap ? (
        <div className="recap-cards">
          <article className="recap-card recap-overview">
            <h3>全局结论</h3>
            <p>{recap.overview}</p>
          </article>

          <article className="recap-card">
            <h3>分阶段分析</h3>
            <div className="recap-phase-grid">
              {recap.phase_analysis.map((phase) => (
                <section key={phase.phase} className="recap-subcard">
                  <h4>{phase.phase}</h4>
                  <p>{phase.summary}</p>
                  <div className="turn-chip-row">
                    {phase.evidence_turns.length > 0 ? (
                      phase.evidence_turns.map((turn) => (
                        <button key={`${phase.phase}-${turn}`} type="button" className="turn-chip" onClick={() => onJumpTurn(turn)}>
                          第 {turn} 手
                        </button>
                      ))
                    ) : (
                      <span className="muted">暂无证据回合</span>
                    )}
                  </div>
                </section>
              ))}
            </div>
          </article>

          <article className="recap-card">
            <h3>关键转折点</h3>
            <div className="turning-list">
              {recap.turning_points.length > 0 ? (
                recap.turning_points.map((item, idx) => (
                  <section key={`${item.turn}-${idx}`} className="recap-subcard">
                    <h4>
                      第 {item.turn} 手 · {item.title}
                    </h4>
                    <p>{item.impact}</p>
                    <div className="turn-chip-row">
                      {(item.evidence_turns.length > 0 ? item.evidence_turns : [item.turn]).map((turn) => (
                        <button key={`tp-${idx}-${turn}`} type="button" className="turn-chip" onClick={() => onJumpTurn(turn)}>
                          跳到第 {turn} 手
                        </button>
                      ))}
                    </div>
                  </section>
                ))
              ) : (
                <p className="muted">暂无关键转折点。</p>
              )}
            </div>
          </article>

          <article className="recap-card">
            <h3>各玩家表现</h3>
            <div className="player-profile-grid">
              {recap.player_profiles.map((player) => (
                <section key={player.player_id} className={`recap-subcard ${player.is_winner ? "winner-card" : ""}`}>
                  <div className="player-identity">
                    <ModelAvatar
                      officialModelId={storedProfiles[player.player_id]?.model ?? null}
                      displayName={replayPlayerMap[player.player_id]?.name ?? player.player_id}
                      vendorName={storedProfiles[player.player_id]?.model?.split("/")[0] ?? null}
                      size={28}
                    />
                    <div className="player-identity__text">
                      <h4>
                        {replayPlayerMap[player.player_id]?.name ?? player.player_id}
                        {player.is_winner ? "（胜者）" : ""}
                      </h4>
                      <p className="tiny-note">
                        {replayPlayerMap[player.player_id]?.is_agent ?? true
                          ? `AI · ${inferModelTag({
                              modelId: storedProfiles[player.player_id]?.model ?? null,
                              displayName: replayPlayerMap[player.player_id]?.name ?? player.player_id,
                              vendorName: storedProfiles[player.player_id]?.model?.split("/")[0] ?? null,
                              isAgent: replayPlayerMap[player.player_id]?.is_agent ?? true,
                            })}`
                          : "真人 · human"}
                      </p>
                    </div>
                  </div>
                  <p className="muted">风格：{player.style}</p>
                  <p className="recap-list-title">亮点</p>
                  <ul>
                    {player.highlights.map((item) => (
                      <li key={`${player.player_id}-h-${item}`}>{item}</li>
                    ))}
                  </ul>
                  <p className="recap-list-title">可改进点</p>
                  <ul>
                    {player.issues.map((item) => (
                      <li key={`${player.player_id}-i-${item}`}>{item}</li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          </article>

          <article className="recap-card">
            <h3>下一局建议</h3>
            <ol className="advice-list">
              {recap.next_game_advice.map((item, index) => (
                <li key={`advice-${index}`}>{item}</li>
              ))}
            </ol>
          </article>
        </div>
      ) : null}

      {summary ? (
        <details className="summary-panel">
          <summary>查看原始 Markdown / JSON</summary>
          <h4>Markdown</h4>
          <pre>{summary.markdown}</pre>
          <h4>JSON</h4>
          <pre>{JSON.stringify(summary, null, 2)}</pre>
        </details>
      ) : null}

      <div className="summary-export">
        <button
          type="button"
          className="btn-secondary"
          onClick={() => setExportText(onExportSummary("markdown"))}
        >
          导出 Markdown
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => setExportText(onExportSummary("json"))}
        >
          导出 JSON
        </button>
      </div>
      <textarea value={exportText} readOnly rows={8} placeholder="导出内容会显示在这里" />
    </section>
  );
};
