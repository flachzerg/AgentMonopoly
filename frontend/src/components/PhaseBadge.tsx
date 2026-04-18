import type { FC } from "react";

const PHASE_LABELS: Record<string, string> = {
  ROLL: "ROLL",
  TILE_ENTER: "TILE_ENTER",
  AUTO_SETTLE: "AUTO_SETTLE",
  DECISION: "DECISION",
  EXECUTE: "EXECUTE",
  LOG: "LOG",
};

export const PhaseBadge: FC<{ phase: string }> = ({ phase }) => {
  const label = PHASE_LABELS[phase] ?? phase;
  const kind = phase.toLowerCase();
  return <span className={`phase-badge phase-${kind}`}>{label}</span>;
};
