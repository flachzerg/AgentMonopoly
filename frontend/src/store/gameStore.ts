import { create } from "zustand";

import { gamesApi } from "../services/api";
import { GameWsClient, type WsStatus } from "../services/ws";
import { jumpReplayIndex, stepReplayIndex } from "./replayPlayer";
import type {
  DecisionAudit,
  EventRecord,
  GameState,
  ReplayResponse,
  ReplaySummary,
  WsStateSyncPayload,
} from "../types/game";

type GameStore = {
  gameId: string;
  state: GameState | null;
  timeline: EventRecord[];
  replay: ReplayResponse | null;
  replayIndex: number;
  summary: ReplaySummary | null;
  activeAudit: DecisionAudit | null;
  wsStatus: WsStatus;
  wsRetryCount: number;
  isBusy: boolean;
  error: string | null;
  wsClient: GameWsClient | null;
  availableGames: string[];
  setGameId: (gameId: string) => void;
  refreshGameList: () => Promise<void>;
  createAndLoadGame: (maxRounds: number, seed: number) => Promise<void>;
  loadState: () => Promise<void>;
  connectWs: () => void;
  disconnectWs: () => void;
  submitAction: (action: string, args: Record<string, unknown>) => Promise<void>;
  triggerAgent: () => Promise<void>;
  loadReplay: () => Promise<void>;
  loadSummary: () => Promise<void>;
  stepReplay: (direction: "prev" | "next") => void;
  jumpReplayTurn: (turnIndex: number) => void;
  exportSummary: (format: "json" | "markdown") => string;
};

const DEFAULT_PLAYERS = [
  { player_id: "p1", name: "玩家A", is_agent: false },
  { player_id: "p2", name: "Agent-B", is_agent: true },
  { player_id: "p3", name: "Agent-C", is_agent: true },
  { player_id: "p4", name: "Agent-D", is_agent: true },
];

const MAX_TIMELINE_SIZE = 250;

function appendTimeline(
  current: EventRecord[],
  incoming: EventRecord[]
): EventRecord[] {
  const merged = [...current, ...incoming];
  if (merged.length <= MAX_TIMELINE_SIZE) {
    return merged;
  }
  return merged.slice(merged.length - MAX_TIMELINE_SIZE);
}

export const useGameStore = create<GameStore>((set, get) => ({
  gameId: "demo-room",
  state: null,
  timeline: [],
  replay: null,
  replayIndex: 0,
  summary: null,
  activeAudit: null,
  wsStatus: "idle",
  wsRetryCount: 0,
  isBusy: false,
  error: null,
  wsClient: null,
  availableGames: [],

  setGameId: (gameId) => {
    set({ gameId, error: null });
  },

  refreshGameList: async () => {
    try {
      const games = await gamesApi.listGames();
      set({ availableGames: games });
    } catch (error) {
      set({ error: `games list failed: ${String(error)}` });
    }
  },

  createAndLoadGame: async (maxRounds, seed) => {
    const gameId = get().gameId.trim();
    if (!gameId) {
      set({ error: "gameId 不能为空" });
      return;
    }

    set({ isBusy: true, error: null });
    try {
      const state = await gamesApi.createGame({
        game_id: gameId,
        players: DEFAULT_PLAYERS,
        max_rounds: maxRounds,
        seed,
      });
      set({
        state,
        timeline: state.last_events,
        replay: null,
        replayIndex: 0,
        summary: null,
        activeAudit: null,
      });
      await get().refreshGameList();
      get().connectWs();
    } catch (error) {
      set({ error: `create game failed: ${String(error)}` });
    } finally {
      set({ isBusy: false });
    }
  },

  loadState: async () => {
    const gameId = get().gameId;
    if (!gameId) {
      return;
    }
    set({ isBusy: true, error: null });
    try {
      const state = await gamesApi.getState(gameId);
      set({
        state,
        timeline: state.last_events,
      });
    } catch (error) {
      set({ error: `load state failed: ${String(error)}` });
    } finally {
      set({ isBusy: false });
    }
  },

  connectWs: () => {
    const { gameId, wsClient } = get();
    if (!gameId) {
      set({ error: "gameId 不能为空" });
      return;
    }
    wsClient?.disconnect();

    const client = new GameWsClient(gameId, {
      onStatus: (status, retryCount) => {
        set({ wsStatus: status, wsRetryCount: retryCount });
      },
      onError: (message) => {
        set({ error: message });
      },
      onMessage: (payload: WsStateSyncPayload) => {
        if (payload.type === "error") {
          set({ error: payload.message ?? "ws error" });
          return;
        }
        set((current) => {
          const incomingEvents = payload.event ? [payload.event] : [];
          const nextTimeline = appendTimeline(current.timeline, incomingEvents);
          return {
            state: payload.state ?? current.state,
            timeline: nextTimeline,
            activeAudit: payload.audit ?? current.activeAudit,
          };
        });
      },
    });

    set({ wsClient: client, error: null });
    client.connect();
  },

  disconnectWs: () => {
    const wsClient = get().wsClient;
    wsClient?.disconnect();
    set({ wsClient: null, wsStatus: "idle", wsRetryCount: 0 });
  },

  submitAction: async (action, args) => {
    const currentState = get().state;
    if (!currentState) {
      set({ error: "state 未加载" });
      return;
    }

    set({ isBusy: true, error: null });
    try {
      const result = await gamesApi.submitAction(
        currentState.game_id,
        currentState.current_player_id,
        action,
        args
      );
      set((current) => {
        const incomingEvents = result.event ? [result.event] : [];
        return {
          state: result.state ?? current.state,
          timeline: appendTimeline(current.timeline, incomingEvents),
          activeAudit: result.audit ?? current.activeAudit,
          error: result.accepted ? null : result.message,
        };
      });
    } catch (error) {
      set({ error: `submit action failed: ${String(error)}` });
    } finally {
      set({ isBusy: false });
    }
  },

  triggerAgent: async () => {
    const currentState = get().state;
    if (!currentState) {
      set({ error: "state 未加载" });
      return;
    }

    set({ isBusy: true, error: null });
    try {
      const result = await gamesApi.triggerAgent(
        currentState.game_id,
        currentState.current_player_id
      );
      set((current) => {
        const incomingEvents = result.event ? [result.event] : [];
        return {
          state: result.state ?? current.state,
          timeline: appendTimeline(current.timeline, incomingEvents),
          activeAudit: result.audit ?? current.activeAudit,
          error: result.accepted ? null : result.message,
        };
      });
    } catch (error) {
      set({ error: `agent action failed: ${String(error)}` });
    } finally {
      set({ isBusy: false });
    }
  },

  loadReplay: async () => {
    const gameId = get().gameId;
    if (!gameId) {
      return;
    }
    set({ isBusy: true, error: null });
    try {
      const replay = await gamesApi.getReplay(gameId);
      set({ replay, replayIndex: Math.max(replay.steps.length - 1, 0) });
    } catch (error) {
      set({ error: `load replay failed: ${String(error)}` });
    } finally {
      set({ isBusy: false });
    }
  },

  loadSummary: async () => {
    const gameId = get().gameId;
    if (!gameId) {
      return;
    }
    set({ isBusy: true, error: null });
    try {
      const summary = await gamesApi.getSummary(gameId);
      set({ summary });
    } catch (error) {
      set({ error: `load summary failed: ${String(error)}` });
    } finally {
      set({ isBusy: false });
    }
  },

  stepReplay: (direction) => {
    set((current) => {
      const nextIndex = stepReplayIndex(current.replay, current.replayIndex, direction);
      if (!current.replay || current.replay.steps.length === 0 || nextIndex === current.replayIndex) {
        return current;
      }
      return {
        replayIndex: nextIndex,
        state: current.replay.steps[nextIndex].state,
      };
    });
  },

  jumpReplayTurn: (turnIndex) => {
    set((current) => {
      const nextIndex = jumpReplayIndex(current.replay, turnIndex, current.replayIndex);
      if (!current.replay || current.replay.steps.length === 0 || nextIndex === current.replayIndex) {
        return current;
      }
      return {
        replayIndex: nextIndex,
        state: current.replay.steps[nextIndex].state,
      };
    });
  },

  exportSummary: (format) => {
    const storeState = get();
    if (!storeState.summary) {
      return "";
    }
    if (format === "markdown") {
      return storeState.summary.markdown;
    }
    return JSON.stringify(storeState.summary, null, 2);
  },
}));
