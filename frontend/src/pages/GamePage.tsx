import { useEffect, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ActionPanel } from "../components/ActionPanel";
import { AgentStreamPanel } from "../components/AgentStreamPanel";
import { AlliancePanel } from "../components/AlliancePanel";
import { AssetPanel } from "../components/AssetPanel";
import { BoardGrid } from "../components/BoardGrid";
import { EventTimeline } from "../components/EventTimeline";
import { PhaseBadge } from "../components/PhaseBadge";
import { useGameStore } from "../store/gameStore";

export default function GamePage() {
  const navigate = useNavigate();
  const params = useParams<{ gameId: string }>();
  const routeGameId = params.gameId ?? "";

  const {
    roomName,
    gameId,
    state,
    timeline,
    agentStream,
    activeAudit,
    wsStatus,
    wsRetryCount,
    isBusy,
    error,
    setGameId,
    loadState,
    connectWs,
    disconnectWs,
    submitAction,
    triggerAgent,
    autoPlayAgents,
  } = useGameStore();

  useEffect(() => {
    if (!routeGameId) {
      navigate("/");
      return;
    }
    if (gameId !== routeGameId) {
      setGameId(routeGameId);
      void loadState();
    }
    connectWs();
    return () => {
      disconnectWs();
    };
  }, [routeGameId]);

  useEffect(() => {
    if (state?.status === "finished") {
      navigate(`/replay/${encodeURIComponent(state.game_id)}`);
    }
  }, [state?.status]);

  const wsLabel = useMemo(() => {
    if (wsStatus === "connecting") {
      return `connecting(${wsRetryCount})`;
    }
    return wsStatus;
  }, [wsStatus, wsRetryCount]);

  if (!state) {
    return (
      <div className="panel game-empty">
        <h2>正在加载对局...</h2>
        {error ? <p className="error-text">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="battle-page">
      <section className="battle-global panel">
        <div className="battle-global-main">
          <h1>{roomName || state.game_id}</h1>
          <div className="status-strip">
            <span>game: {state.game_id}</span>
            <span>status: {state.status}</span>
            <span>
              round: {state.round_index}/{state.max_rounds}
            </span>
            <span>turn: {state.turn_index}</span>
            <span>current player: {state.current_player_id}</span>
            <span>WS: {wsLabel}</span>
          </div>
        </div>
        <div className="battle-global-side">
          <PhaseBadge phase={state.current_phase} />
          {activeAudit ? (
            <div className="tiny-note">
              {activeAudit.model_tag} {"=>"} {activeAudit.final_decision.action}
            </div>
          ) : null}
        </div>
      </section>

      <section className="battle-main">
        <div className="battle-left">
          <BoardGrid state={state} />
          <AssetPanel state={state} />
          <AlliancePanel state={state} />
        </div>
        <div className="battle-right">
          <EventTimeline events={timeline} />
          <AgentStreamPanel entries={agentStream} />
        </div>
      </section>

      <section className="battle-action panel">
        <div className="battle-action-row">
          <ActionPanel
            state={state}
            busy={isBusy}
            onSubmitAction={submitAction}
            onTriggerAgent={triggerAgent}
            onAutoPlayAgents={autoPlayAgents}
          />
        </div>
        <div className="battle-action-aux">
          <button type="button" className="btn-secondary" onClick={() => navigate(`/replay/${encodeURIComponent(state.game_id)}`)}>
            查看复盘页
          </button>
          {error ? <p className="error-text">{error}</p> : null}
        </div>
      </section>
    </div>
  );
}
