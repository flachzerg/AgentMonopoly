import { useEffect, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ActionPanel } from "../components/ActionPanel";
import { AgentStreamPanel } from "../components/AgentStreamPanel";
import { BoardGrid } from "../components/BoardGrid";
import { DecisionCenter } from "../components/DecisionCenter";
import { EventTimeline } from "../components/EventTimeline";
import { ModelAvatar } from "../components/ModelAvatar";
import { PhaseBadge } from "../components/PhaseBadge";
import { TaskDockWidgets } from "../components/TaskDockWidgets";
import { buildPlayerNameMap } from "../lib/eventPresentation";
import { getGamePlayerProfiles, inferModelTag } from "../lib/modelAvatar";
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
    activeContext,
    wsStatus,
    wsRetryCount,
    isBusy,
    error,
    setGameId,
    loadState,
    connectWs,
    disconnectWs,
    submitAction,
    autoPlayAgents,
  } = useGameStore();

  useEffect(() => {
    if (!routeGameId) {
      navigate("/setup");
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
      return;
    }
    if (!state || isBusy) {
      return;
    }
    if (state.status === "running" && !state.waiting_for_human) {
      void autoPlayAgents(64);
    }
  }, [state?.status, state?.turn_index, state?.current_player_id, state?.waiting_for_human, isBusy]);

  const wsLabel = useMemo(() => {
    if (wsStatus === "connecting") {
      return `connecting(${wsRetryCount})`;
    }
    return wsStatus;
  }, [wsStatus, wsRetryCount]);

  const stageHint = useMemo(() => {
    if (!state) {
      return "";
    }
    if (state.waiting_for_human) {
      if (state.human_wait_reason === "roll_dice") {
        return "等待真人掷骰";
      }
      if (state.human_wait_reason === "branch_decision") {
        return "等待真人分支决策";
      }
    }
    if (state.current_phase === "DECISION") {
      return "系统决策处理中";
    }
    return "系统自动推进中";
  }, [state]);

  const storedProfiles = useMemo(() => {
    if (!state) {
      return {};
    }
    return getGamePlayerProfiles(state.game_id);
  }, [state?.game_id]);

  const currentPlayerMeta = useMemo(() => {
    if (!state) {
      return null;
    }
    const fromState = state.players.find((player) => player.player_id === state.current_player_id);
    const fromStorage = storedProfiles[state.current_player_id];
    const displayName = fromState?.name || fromStorage?.name || state.current_player_id;
    const isAgent = fromState?.is_agent ?? fromStorage?.is_agent ?? true;
    const modelId = fromStorage?.model ?? null;
    const vendorName = modelId?.split("/")[0] ?? null;
    const modelTag = inferModelTag({
      modelId,
      displayName,
      vendorName,
      isAgent,
    });

    return {
      playerId: state.current_player_id,
      displayName,
      isAgent,
      modelId,
      vendorName,
      modelTag,
    };
  }, [state, storedProfiles]);

  const playerNameMap = useMemo(() => {
    if (!state) {
      return {};
    }
    return buildPlayerNameMap(state.players);
  }, [state]);

  const handleReconnect = (): void => {
    connectWs();
    void loadState();
  };

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
          <p className="stage-hint">{stageHint}</p>
          <div className="status-strip">
            <span>game: {state.game_id}</span>
            <span>status: {state.status}</span>
            <span>
              round: {state.round_index}/{state.max_rounds}
            </span>
            <span>turn: {state.turn_index}</span>
            {currentPlayerMeta ? (
              <span className="status-player">
                <ModelAvatar
                  officialModelId={currentPlayerMeta.modelId}
                  displayName={currentPlayerMeta.displayName}
                  vendorName={currentPlayerMeta.vendorName}
                  size={24}
                  variant="bare"
                />
                <span>
                  current: {currentPlayerMeta.displayName} ({currentPlayerMeta.playerId})
                </span>
                <span className="tiny-note">{currentPlayerMeta.isAgent ? `AI · ${currentPlayerMeta.modelTag}` : "真人 · human"}</span>
              </span>
            ) : null}
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
          <DecisionCenter
            state={state}
            timeline={timeline}
            activeAudit={activeAudit}
            activeContext={activeContext}
            wsStatus={wsStatus}
            error={error}
          />
          <BoardGrid state={state} />
        </div>
        <div className="battle-right">
          <EventTimeline events={timeline} playerNameMap={playerNameMap} />
          <AgentStreamPanel entries={agentStream} />
        </div>
      </section>

      <section className="battle-action panel taskbar-panel">
        <div className="battle-action-row">
          <ActionPanel
            state={state}
            busy={isBusy}
            wsStatus={wsStatus}
            error={error}
            onSubmitAction={submitAction}
            onOpenReplay={() => navigate(`/replay/${encodeURIComponent(state.game_id)}`)}
            onReconnect={handleReconnect}
          />
        </div>
        <TaskDockWidgets state={state} />
        <div className="battle-action-aux">
          <button type="button" className="btn-secondary" onClick={() => navigate(`/replay/${encodeURIComponent(state.game_id)}`)}>
            查看复盘页
          </button>
          <button type="button" className="btn-secondary" onClick={() => navigate("/setup")}>
            回到配置页
          </button>
          {error ? <p className="error-text">{error}</p> : null}
        </div>
      </section>
    </div>
  );
}
