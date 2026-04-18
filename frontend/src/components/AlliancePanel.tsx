import type { FC } from "react";

import type { GameState } from "../types/game";

type Props = {
  state: GameState;
};

export const AlliancePanel: FC<Props> = ({ state }) => {
  const pairs: Array<[string, string]> = [];
  const seen = new Set<string>();

  for (const player of state.players) {
    if (!player.alliance_with) {
      continue;
    }
    const pairKey = [player.player_id, player.alliance_with].sort().join("|");
    if (seen.has(pairKey)) {
      continue;
    }
    seen.add(pairKey);
    pairs.push([player.player_id, player.alliance_with]);
  }

  return (
    <section className="panel">
      <h2>联盟面板</h2>
      {pairs.length === 0 ? (
        <p className="muted">当前没有联盟。</p>
      ) : (
        <ul className="alliance-list">
          {pairs.map(([a, b]) => (
            <li key={`${a}-${b}`}>
              <span>{a}</span>
              <span className="alliance-link">↔</span>
              <span>{b}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};
