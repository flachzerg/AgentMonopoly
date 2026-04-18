import { useMemo, useState, type FC } from "react";

import type { ReplayResponse, ReplaySummary } from "../types/game";

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

  const currentStep = useMemo(() => {
    if (!replay || replay.steps.length === 0) {
      return null;
    }
    return replay.steps[Math.min(Math.max(replayIndex, 0), replay.steps.length - 1)];
  }, [replay, replayIndex]);

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
            <article>
              <h3>候选动作</h3>
              <pre>{JSON.stringify(currentStep.candidate_actions, null, 2)}</pre>
            </article>
            <article>
              <h3>最终动作</h3>
              <pre>{JSON.stringify(currentStep.final_action, null, 2)}</pre>
            </article>
            <article>
              <h3>策略标签</h3>
              <pre>{JSON.stringify(currentStep.strategy_tags, null, 2)}</pre>
            </article>
            <article>
              <h3>阶段轨迹</h3>
              <pre>{JSON.stringify(currentStep.phase_trace, null, 2)}</pre>
            </article>
            <article>
              <h3>审计</h3>
              <pre>{JSON.stringify(currentStep.decision_audit, null, 2)}</pre>
            </article>
          </div>
        </>
      ) : (
        <p className="muted">暂无 replay 数据。</p>
      )}

      {summary ? (
        <div className="summary-panel">
          <h3>对局摘要</h3>
          <pre>{summary.markdown}</pre>
        </div>
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
