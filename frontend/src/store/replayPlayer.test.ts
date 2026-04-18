import { describe, expect, it } from "vitest";

import { jumpReplayIndex, replayCurrentTurn, stepReplayIndex } from "./replayPlayer";
import type { ReplayResponse } from "../types/game";

function buildReplay(): ReplayResponse {
  return {
    game_id: "g-1",
    total_turns: 3,
    steps: [
      {
        turn_index: 1,
        round_index: 1,
        phase: "LOG",
        phase_trace: ["ROLL", "TILE_ENTER", "AUTO_SETTLE", "DECISION", "EXECUTE", "LOG"],
        state: {
          game_id: "g-1",
          status: "running",
          round_index: 1,
          turn_index: 1,
          max_rounds: 20,
          current_player_id: "p1",
          current_phase: "ROLL",
          active_tile_id: "T00",
          players: [],
          board: [],
          allowed_actions: [],
          last_events: [],
        },
        events: [],
        candidate_actions: ["pass"],
        final_action: "pass",
        strategy_tags: ["conservative"],
        decision_audit: null,
      },
      {
        turn_index: 2,
        round_index: 1,
        phase: "LOG",
        phase_trace: ["ROLL", "TILE_ENTER", "AUTO_SETTLE", "DECISION", "EXECUTE", "LOG"],
        state: {
          game_id: "g-1",
          status: "running",
          round_index: 1,
          turn_index: 2,
          max_rounds: 20,
          current_player_id: "p2",
          current_phase: "ROLL",
          active_tile_id: "T01",
          players: [],
          board: [],
          allowed_actions: [],
          last_events: [],
        },
        events: [],
        candidate_actions: ["buy_property", "skip_buy"],
        final_action: "buy_property",
        strategy_tags: ["expansion"],
        decision_audit: null,
      },
      {
        turn_index: 3,
        round_index: 1,
        phase: "LOG",
        phase_trace: ["ROLL", "TILE_ENTER", "AUTO_SETTLE", "DECISION", "EXECUTE", "LOG"],
        state: {
          game_id: "g-1",
          status: "running",
          round_index: 1,
          turn_index: 3,
          max_rounds: 20,
          current_player_id: "p3",
          current_phase: "ROLL",
          active_tile_id: "T02",
          players: [],
          board: [],
          allowed_actions: [],
          last_events: [],
        },
        events: [],
        candidate_actions: ["pass"],
        final_action: "pass",
        strategy_tags: ["cash_priority"],
        decision_audit: null,
      },
    ],
  };
}

describe("replayPlayer", () => {
  it("steps with bounds", () => {
    const replay = buildReplay();
    expect(stepReplayIndex(replay, 0, "prev")).toBe(0);
    expect(stepReplayIndex(replay, 0, "next")).toBe(1);
    expect(stepReplayIndex(replay, 2, "next")).toBe(2);
  });

  it("jumps by turn index", () => {
    const replay = buildReplay();
    expect(jumpReplayIndex(replay, 2, 0)).toBe(1);
    expect(jumpReplayIndex(replay, 99, 1)).toBe(1);
  });

  it("returns current turn", () => {
    const replay = buildReplay();
    expect(replayCurrentTurn(replay, 1)).toBe(2);
    expect(replayCurrentTurn(replay, 99)).toBe(3);
  });
});
