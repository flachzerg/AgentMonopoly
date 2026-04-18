import { useEffect, useMemo, useRef, type FC } from "react";

import type { GameState, PlayerSnapshot } from "../types/game";
import { ModelAvatar } from "./ModelAvatar";

type Props = {
  state: GameState;
  player: PlayerSnapshot | null;
  open: boolean;
  onClose: () => void;
  modelId: string | null;
  vendorName: string | null;
};

function keepFocusInside(event: KeyboardEvent, container: HTMLElement): void {
  if (event.key !== "Tab") {
    return;
  }
  const focusables = Array.from(
    container.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
  ).filter((element) => !element.hasAttribute("disabled") && !element.getAttribute("aria-hidden"));

  if (focusables.length === 0) {
    event.preventDefault();
    return;
  }

  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  const active = document.activeElement as HTMLElement | null;

  if (!event.shiftKey && active === last) {
    event.preventDefault();
    first.focus();
  }

  if (event.shiftKey && active === first) {
    event.preventDefault();
    last.focus();
  }
}

export const PlayerDetailModal: FC<Props> = ({ state, player, open, onClose, modelId, vendorName }) => {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  const propertyTiles = useMemo(() => {
    if (!player) {
      return [];
    }
    const ids = new Set(player.property_ids);
    return state.board.filter((tile) => ids.has(tile.tile_id));
  }, [player, state.board]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const panel = panelRef.current;
    closeButtonRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (panel) {
        keepFocusInside(event, panel);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = oldOverflow;
    };
  }, [open, onClose]);

  if (!open || !player) {
    return null;
  }

  return (
    <div className="player-detail-modal" role="dialog" aria-modal="true" aria-label={`${player.name || player.player_id} 资产详情`}>
      <button type="button" className="player-detail-modal__backdrop" aria-label="关闭资产详情弹窗" onClick={onClose} />
      <section ref={panelRef} className="player-detail-modal__panel">
        <header className="player-detail-modal__header">
          <div className="player-identity">
            <ModelAvatar
              officialModelId={modelId}
              displayName={player.name || player.player_id}
              vendorName={vendorName}
              size={36}
            />
            <div className="player-identity__text">
              <strong>{player.name || player.player_id}</strong>
              <span className="tiny-note">ID: {player.player_id}</span>
            </div>
          </div>
          <button ref={closeButtonRef} type="button" className="btn-secondary" onClick={onClose}>
            关闭
          </button>
        </header>

        <div className="player-detail-modal__metrics">
          <div>
            <span>现金</span>
            <strong>{player.cash}</strong>
          </div>
          <div>
            <span>存款</span>
            <strong>{player.deposit}</strong>
          </div>
          <div>
            <span>净值</span>
            <strong>{player.net_worth}</strong>
          </div>
          <div>
            <span>当前位置</span>
            <strong>{state.board.find((tile) => tile.tile_index === player.position)?.name ?? `#${player.position}`}</strong>
          </div>
        </div>

        <section className="player-detail-modal__section">
          <p className="tiny-note">二级摘要</p>
          <p>
            {player.alive
              ? `持有地产 ${player.property_ids.length} 处，当前仍在对局中。`
              : "该玩家已进入破产状态，资产已完成清算。"}
          </p>
        </section>

        <section className="player-detail-modal__section">
          <p className="tiny-note">持有地产</p>
          {propertyTiles.length === 0 ? (
            <p className="muted">暂无地产。</p>
          ) : (
            <ul className="player-detail-modal__property-list">
              {propertyTiles.map((tile) => (
                <li key={tile.tile_id}>
                  <span>{tile.name}</span>
                  <span className="tiny-note">
                    {tile.tile_id} · {tile.tile_type} · toll {tile.toll ?? "-"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <details className="player-detail-modal__raw">
          <summary>查看原始数据</summary>
          <pre>{JSON.stringify(player, null, 2)}</pre>
        </details>
      </section>
    </div>
  );
};
