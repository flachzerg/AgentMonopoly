import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ReplayPanel } from "../components/ReplayPanel";
import { useGameStore } from "../store/gameStore";

export default function ReplayPage() {
  const navigate = useNavigate();
  const params = useParams<{ gameId: string }>();
  const routeGameId = params.gameId ?? "";

  const {
    gameId,
    replay,
    replayIndex,
    summary,
    isBusy,
    error,
    setGameId,
    loadState,
    loadReplay,
    loadSummary,
    stepReplay,
    jumpReplayTurn,
    exportSummary,
  } = useGameStore();

  useEffect(() => {
    if (!routeGameId) {
      navigate("/");
      return;
    }
    if (gameId !== routeGameId) {
      setGameId(routeGameId);
    }
    void loadState();
    void loadReplay();
    void loadSummary();
  }, [routeGameId]);

  return (
    <div className="replay-page">
      <section className="panel replay-header">
        <h1>全局复盘</h1>
        <div className="replay-header-actions">
          <button type="button" className="btn-secondary" onClick={() => navigate("/")}>新建对局</button>
          <button type="button" className="btn-secondary" onClick={() => navigate(`/game/${encodeURIComponent(routeGameId)}`)}>
            返回对局
          </button>
        </div>
      </section>

      <section>
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
        {isBusy ? <p className="muted">正在加载复盘数据...</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
      </section>
    </div>
  );
}
