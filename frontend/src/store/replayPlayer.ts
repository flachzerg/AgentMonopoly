import type { ReplayResponse } from "../types/game";

export function stepReplayIndex(
  replay: ReplayResponse | null,
  currentIndex: number,
  direction: "prev" | "next"
): number {
  if (!replay || replay.steps.length === 0) {
    return currentIndex;
  }
  const delta = direction === "next" ? 1 : -1;
  return clamp(currentIndex + delta, 0, replay.steps.length - 1);
}

export function jumpReplayIndex(
  replay: ReplayResponse | null,
  turnIndex: number,
  fallbackIndex: number
): number {
  if (!replay || replay.steps.length === 0) {
    return fallbackIndex;
  }
  const target = replay.steps.findIndex((step) => step.turn_index === turnIndex);
  return target >= 0 ? target : fallbackIndex;
}

export function replayCurrentTurn(replay: ReplayResponse | null, currentIndex: number): number {
  if (!replay || replay.steps.length === 0) {
    return 0;
  }
  const index = clamp(currentIndex, 0, replay.steps.length - 1);
  return replay.steps[index].turn_index;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}
