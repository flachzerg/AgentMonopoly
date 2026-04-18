import type { FC } from "react";

import type { GameState } from "../types/game";

type Props = {
  state: GameState;
};

export const AssetPanel: FC<Props> = ({ state }) => {
  return (
    <section className="panel">
      <h2>资产面板</h2>
      <table className="asset-table">
        <thead>
          <tr>
            <th>玩家</th>
            <th>cash</th>
            <th>deposit</th>
            <th>net</th>
            <th>地产</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          {state.players.map((player) => (
            <tr key={player.player_id}>
              <td>{player.player_id}</td>
              <td>{player.cash}</td>
              <td>{player.deposit}</td>
              <td>{player.net_worth}</td>
              <td>{player.property_ids.length}</td>
              <td>{player.alive ? "alive" : "bankrupt"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
};
