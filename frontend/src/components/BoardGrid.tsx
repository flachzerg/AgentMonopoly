import type { FC } from "react";

import type { GameState } from "../types/game";

type Props = {
  state: GameState;
};

export const BoardGrid: FC<Props> = ({ state }) => {
  const playersByTile = new Map<number, string[]>();
  for (const player of state.players) {
    const bucket = playersByTile.get(player.position) ?? [];
    bucket.push(player.player_id);
    playersByTile.set(player.position, bucket);
  }

  return (
    <section className="panel board-panel">
      <div className="panel-title-row">
        <h2>棋盘</h2>
        <div className="tiny-note">active tile: {state.active_tile_id}</div>
      </div>
      <div className="board-grid">
        {state.board.map((tile) => {
          const occupied = playersByTile.get(tile.tile_index) ?? [];
          const isActive = tile.tile_id === state.active_tile_id;
          return (
            <article
              className={`tile-card ${isActive ? "tile-active" : ""}`}
              key={tile.tile_id}
            >
              <div className="tile-header">
                <span className="tile-name">{tile.name}</span>
                <span className="tile-subtype">{tile.tile_type}</span>
              </div>
              <div className="tile-meta">#{tile.tile_index}</div>
              {tile.owner_id ? (
                <div className="tile-owner">owner: {tile.owner_id}</div>
              ) : (
                <div className="tile-owner">owner: -</div>
              )}
              <div className="tile-metrics">
                <span>price: {tile.property_price ?? "-"}</span>
                <span>toll: {tile.toll ?? "-"}</span>
              </div>
              <div className="tile-players">
                {occupied.length > 0 ? occupied.join(", ") : "-"}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
};
