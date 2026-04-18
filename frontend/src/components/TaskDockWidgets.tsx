import { useId, useMemo, useState, type FC } from "react";

import { getGamePlayerProfiles, inferModelTag } from "../lib/modelAvatar";
import type { GameState } from "../types/game";
import { ModelAvatar } from "./ModelAvatar";
import { PlayerDetailModal } from "./PlayerDetailModal";

type Props = {
  state: GameState;
};

function buildAlliancePairs(state: GameState): Array<[string, string]> {
  const pairs: Array<[string, string]> = [];
  const seen = new Set<string>();
  for (const player of state.players) {
    if (!player.alliance_with) {
      continue;
    }
    const key = [player.player_id, player.alliance_with].sort().join("|");
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    pairs.push([player.player_id, player.alliance_with]);
  }
  return pairs;
}

export const TaskDockWidgets: FC<Props> = ({ state }) => {
  const [assetPinned, setAssetPinned] = useState(false);
  const [assetHover, setAssetHover] = useState(false);
  const [alliancePinned, setAlliancePinned] = useState(false);
  const [allianceHover, setAllianceHover] = useState(false);
  const [selectedPlayerId, setSelectedPlayerId] = useState<string | null>(null);

  const alliancePairs = buildAlliancePairs(state);
  const storedProfiles = getGamePlayerProfiles(state.game_id);
  const assetOpen = assetPinned || assetHover;
  const allianceOpen = alliancePinned || allianceHover;
  const assetPopupId = useId();
  const alliancePopupId = useId();

  const selectedPlayer = useMemo(() => {
    if (!selectedPlayerId) {
      return null;
    }
    return state.players.find((item) => item.player_id === selectedPlayerId) ?? null;
  }, [selectedPlayerId, state.players]);

  return (
    <>
      <div className="task-dock-widgets" role="toolbar" aria-label="任务悬浮面板">
        <div
          className={`dock-widget ${assetOpen ? "open" : ""}`}
          onMouseEnter={() => setAssetHover(true)}
          onMouseLeave={() => setAssetHover(false)}
        >
          <button
            type="button"
            className="dock-toggle"
            onClick={() => setAssetPinned((v) => !v)}
            aria-expanded={assetOpen}
            aria-controls={assetPopupId}
            aria-pressed={assetPinned}
            aria-label="切换资产面板"
          >
            资产面板
            <span className="dock-pin-state" aria-live="polite">
              {assetPinned ? "已固定" : "临时"}
            </span>
          </button>
          <div id={assetPopupId} className="dock-popup" role="dialog" aria-label="资产面板内容">
            <p className="tiny-note">主信息：玩家资产概览，可点击玩家查看详情。</p>
            <table className="asset-table compact">
              <thead>
                <tr>
                  <th>玩家</th>
                  <th>现金</th>
                  <th>存款</th>
                  <th>净值</th>
                  <th>地产</th>
                </tr>
              </thead>
              <tbody>
                {state.players.map((player) => (
                  <tr key={player.player_id} className="asset-row">
                    <td>
                      <button
                        type="button"
                        className="asset-player-trigger"
                        onClick={() => setSelectedPlayerId(player.player_id)}
                        aria-label={`查看 ${player.name || player.player_id} 的资产详情`}
                      >
                        <div className="player-identity player-identity--compact">
                          <ModelAvatar
                            officialModelId={storedProfiles[player.player_id]?.model ?? null}
                            displayName={player.name}
                            vendorName={storedProfiles[player.player_id]?.model?.split("/")[0] ?? null}
                            size={24}
                            variant="bare"
                          />
                          <div className="player-identity__text">
                            <span>{player.name || player.player_id}</span>
                            <span className="tiny-note">
                              {player.is_agent
                                ? `AI · ${inferModelTag({
                                    modelId: storedProfiles[player.player_id]?.model ?? null,
                                    displayName: player.name,
                                    vendorName: storedProfiles[player.player_id]?.model?.split("/")[0] ?? null,
                                    isAgent: player.is_agent,
                                  })}`
                                : "真人 · human"}
                            </span>
                          </div>
                        </div>
                      </button>
                    </td>
                    <td>{player.cash}</td>
                    <td>{player.deposit}</td>
                    <td>{player.net_worth}</td>
                    <td>{player.property_ids.length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <details>
              <summary>查看原始数据</summary>
              <pre>{JSON.stringify(state.players, null, 2)}</pre>
            </details>
          </div>
        </div>

        <div
          className={`dock-widget ${allianceOpen ? "open" : ""}`}
          onMouseEnter={() => setAllianceHover(true)}
          onMouseLeave={() => setAllianceHover(false)}
        >
          <button
            type="button"
            className="dock-toggle"
            onClick={() => setAlliancePinned((v) => !v)}
            aria-expanded={allianceOpen}
            aria-controls={alliancePopupId}
            aria-pressed={alliancePinned}
            aria-label="切换联盟面板"
          >
            联盟面板
            <span className="dock-pin-state" aria-live="polite">
              {alliancePinned ? "已固定" : "临时"}
            </span>
          </button>
          <div id={alliancePopupId} className="dock-popup" role="dialog" aria-label="联盟面板内容">
            <p className="tiny-note">主信息：当前联盟关系。</p>
            {alliancePairs.length === 0 ? (
              <p className="muted">当前没有联盟关系。</p>
            ) : (
              <ul className="alliance-list compact">
                {alliancePairs.map(([a, b]) => (
                  <li key={`${a}-${b}`}>
                    <span>{state.players.find((item) => item.player_id === a)?.name || a}</span>
                    <span className="alliance-link">↔</span>
                    <span>{state.players.find((item) => item.player_id === b)?.name || b}</span>
                  </li>
                ))}
              </ul>
            )}
            <details>
              <summary>查看原始数据</summary>
              <pre>{JSON.stringify(alliancePairs, null, 2)}</pre>
            </details>
          </div>
        </div>
      </div>

      <PlayerDetailModal
        state={state}
        player={selectedPlayer}
        open={Boolean(selectedPlayer)}
        onClose={() => setSelectedPlayerId(null)}
        modelId={selectedPlayer ? storedProfiles[selectedPlayer.player_id]?.model ?? null : null}
        vendorName={selectedPlayer ? storedProfiles[selectedPlayer.player_id]?.model?.split("/")[0] ?? null : null}
      />
    </>
  );
};
