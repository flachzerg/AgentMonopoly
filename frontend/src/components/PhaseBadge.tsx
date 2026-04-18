import type { FC } from "react";

const PHASE_LABELS: Record<string, string> = {
  ROLL: "等待掷骰",
  TILE_ENTER: "到达格子",
  AUTO_SETTLE: "自动结算",
  DECISION: "策略判断",
  EXECUTE: "执行动作",
  LOG: "记录中",
};

export const PhaseBadge: FC<{ phase: string }> = ({ phase }) => {
  const label = PHASE_LABELS[phase] ?? phase;
  const kind = phase.toLowerCase();
  return <span className={`phase-badge phase-${kind}`}>{label}</span>;
};
