import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ReplayPanel } from "../components/ReplayPanel";
import { useGameStore } from "../store/gameStore";

export default function ReplayPage() {
  const navigate = useNavigate();
  const params = useParams<{ gameId: string }>();
  const routeGameId = params.gameId ?? "";

  const { gameId, replay, summary, isBusy, error, setGameId, loadState, loadReplay, loadSummary } = useGameStore();

  useEffect(() => {
    if (!routeGameId) {
      navigate("/setup");
      return;
    }
    if (gameId !== routeGameId) {
      setGameId(routeGameId);
    }
    void loadState();
    void loadReplay();
    void loadSummary();
  }, [gameId, loadReplay, loadState, loadSummary, navigate, routeGameId, setGameId]);

  return (
    <div className="replay-page">
      <ReplayPanel
        replay={replay}
        summary={summary}
        isBusy={isBusy}
        error={error}
        onNewGame={() => navigate("/setup")}
        onBackToGame={() => navigate(`/game/${encodeURIComponent(routeGameId)}`)}
      />
    </div>
  );
}
