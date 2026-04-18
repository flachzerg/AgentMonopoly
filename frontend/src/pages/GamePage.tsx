import { useEffect, useMemo, useState } from "react";

import { ActionPanel } from "../components/ActionPanel";
import { AlliancePanel } from "../components/AlliancePanel";
import { AssetPanel } from "../components/AssetPanel";
import { BoardGrid } from "../components/BoardGrid";
import { EventTimeline } from "../components/EventTimeline";
import { PhaseBadge } from "../components/PhaseBadge";
import { ReplayPanel } from "../components/ReplayPanel";
import { useGameStore } from "../store/gameStore";

export default function GamePage() {
  const [maxRoundsInput, setMaxRoundsInput] = useState("20");
  const [seedInput, setSeedInput] = useState("20260418");

  const {
    gameId,
    state,
    timeline,
    replay,
    replayIndex,
    summary,
    activeAudit,
    wsStatus,
    wsRetryCount,
    isBusy,
    error,
    availableGames,
    setGameId,
    refreshGameList,
    createAndLoadGame,
    loadState,
    connectWs,
    disconnectWs,
    submitAction,
    triggerAgent,
    loadReplay,
    loadSummary,
    stepReplay,
    jumpReplayTurn,
    exportSummary,
  } = useGameStore();

  useEffect(() => {
    void refreshGameList();
  }, [refreshGameList]);

  const canOperate = Boolean(state);

  const wsLabel = useMemo(() => {
    if (wsStatus === "connecting") {
      return `connecting(${wsRetryCount})`;
    }
    return wsStatus;
  }, [wsStatus, wsRetryCount]);

  const maxRounds = Number(maxRoundsInput);
  const seed = Number(seedInput);

  return (
    <div className="page-shell">
      <header className="hero">
        <div>
          <h1>AgentMonopoly 对局台</h1>
          <p>服务端状态与事件流是唯一真值，前端只做展示与交互。</p>
        </div>
        <div className="hero-meta">
          <span>WS: {wsLabel}</span>
          {state ? <PhaseBadge phase={state.current_phase} /> : null}
        </div>
      </header>

      <section className="panel control-panel">
        <h2>房间与对局控制</h2>
        <div className="controls-grid">
          <label className="field">
            <span>game_id</span>
            <input
              value={gameId}
              onChange={(event) => setGameId(event.target.value)}
              placeholder="game id"
            />
          </label>
          <label className="field">
            <span>max_rounds</span>
            <input
              value={maxRoundsInput}
              onChange={(event) => setMaxRoundsInput(event.target.value)}
            />
          </label>
          <label className="field">
            <span>seed</span>
            <input
              value={seedInput}
              onChange={(event) => setSeedInput(event.target.value)}
            />
          </label>
        </div>

        <div className="control-buttons">
          <button
            type="button"
            className="btn-primary"
            disabled={isBusy || !Number.isFinite(maxRounds) || !Number.isFinite(seed)}
            onClick={() =>
              createAndLoadGame(
                Number.isFinite(maxRounds) ? maxRounds : 20,
                Number.isFinite(seed) ? seed : 20260418
              )
            }
          >
            创建并进入
          </button>
          <button type="button" className="btn-secondary" disabled={isBusy} onClick={() => loadState()}>
            HTTP 同步
          </button>
          <button type="button" className="btn-secondary" onClick={() => connectWs()}>
            WS 连接
          </button>
          <button type="button" className="btn-secondary" onClick={() => disconnectWs()}>
            WS 断开
          </button>
          <button type="button" className="btn-secondary" onClick={() => refreshGameList()}>
            刷新房间
          </button>
        </div>

        <div className="game-list">
          <span>已存在 game:</span>
          {availableGames.length > 0 ? availableGames.join(", ") : "(空)"}
        </div>

        {state ? (
          <div className="status-strip">
            <span>status: {state.status}</span>
            <span>
              round: {state.round_index}/{state.max_rounds}
            </span>
            <span>turn: {state.turn_index}</span>
            <span>current player: {state.current_player_id}</span>
            <span>phase: {state.current_phase}</span>
          </div>
        ) : null}

        {activeAudit ? (
          <div className="audit-strip">
            <span>model: {activeAudit.model_tag}</span>
            <span>
              template: {activeAudit.template_key}@{activeAudit.template_version}
            </span>
            <span>final action: {activeAudit.final_decision.action}</span>
            <span>fallback: {activeAudit.status === "fallback" ? "yes" : "no"}</span>
          </div>
        ) : null}

        {error ? <p className="error-text">{error}</p> : null}
      </section>

      {canOperate && state ? (
        <main className="main-grid">
          <BoardGrid state={state} />
          <div className="right-stack">
            <ActionPanel
              state={state}
              busy={isBusy}
              onSubmitAction={submitAction}
              onTriggerAgent={triggerAgent}
            />
            <AssetPanel state={state} />
            <AlliancePanel state={state} />
          </div>
        </main>
      ) : (
        <section className="panel">
          <p className="muted">先创建或加载一个 game，随后会显示对局主界面。</p>
        </section>
      )}

      <section className="bottom-grid">
        <EventTimeline events={timeline} />
        <ReplayPanel
          replay={replay}
          replayIndex={replayIndex}
          summary={summary}
          onLoadReplay={loadReplay}
          onLoadSummary={loadSummary}
          onStep={stepReplay}
          onJumpTurn={jumpReplayTurn}
          onExportSummary={exportSummary}
        />
      </section>
    </div>
  );
}
