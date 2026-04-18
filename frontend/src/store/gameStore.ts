import { create } from "zustand";

import { gamesApi } from "../services/api";
import { GameWsClient, type WsStatus } from "../services/ws";
import { jumpReplayIndex, stepReplayIndex } from "./replayPlayer";
import type {
  AgentContextPacket,
  CreateGameRequest,
  DecisionAudit,
  EventRecord,
  GameState,
  ReplayResponse,
  ReplaySummary,
  WsStateSyncPayload,
} from "../types/game";

type AgentStreamEntry = {
  id: string;
  ts: string;
  playerId: string;
  playerName: string;
  avatar: string;
  action: string;
  modelTag: string;
  status: "streaming" | "ok" | "fallback";
  thought: string;
};

type GameStore = {
  gameId: string;
  roomName: string;
  state: GameState | null;
  timeline: EventRecord[];
  replay: ReplayResponse | null;
  replayIndex: number;
  summary: ReplaySummary | null;
  activeAudit: DecisionAudit | null;
  activeContext: AgentContextPacket | null;
  agentStream: AgentStreamEntry[];
  wsStatus: WsStatus;
  wsRetryCount: number;
  isBusy: boolean;
  error: string | null;
  wsClient: GameWsClient | null;
  availableGames: string[];
  setGameId: (gameId: string) => void;
  setRoomName: (roomName: string) => void;
  refreshGameList: () => Promise<void>;
  createAndLoadGame: (payload: CreateGameRequest) => Promise<string | null>;
  loadState: () => Promise<void>;
  connectWs: () => void;
  disconnectWs: () => void;
  submitAction: (action: string, args: Record<string, unknown>) => Promise<void>;
  triggerAgent: () => Promise<void>;
  autoPlayAgents: (maxSteps?: number) => Promise<void>;
  loadReplay: () => Promise<void>;
  loadSummary: () => Promise<void>;
  stepReplay: (direction: "prev" | "next") => void;
  jumpReplayTurn: (turnIndex: number) => void;
  exportSummary: (format: "json" | "markdown") => string;
};

const MAX_TIMELINE_SIZE = 250;
const MAX_AGENT_STREAM = 80;
const AVATARS = ["🤖", "🦊", "🐼", "🐯", "🐧", "🦁", "🐨", "🦄"];

function appendTimeline(current: EventRecord[], incoming: EventRecord[]): EventRecord[] {
  const seen = new Set(current.map((item) => item.event_id));
  const merged = [...current];
  for (const item of incoming) {
    if (seen.has(item.event_id)) {
      continue;
    }
    seen.add(item.event_id);
    merged.push(item);
  }
  if (merged.length <= MAX_TIMELINE_SIZE) {
    return merged;
  }
  return merged.slice(merged.length - MAX_TIMELINE_SIZE);
}

function avatarForPlayer(playerId: string): string {
  let hash = 0;
  for (const char of playerId) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  return AVATARS[hash % AVATARS.length];
}

function appendAgentStream(current: AgentStreamEntry[], audit: DecisionAudit | null | undefined): AgentStreamEntry[] {
  if (!audit) {
    return current;
  }
  const thought = audit.final_decision.thought ?? "";
  const thoughtMatchIndex =
    thought.length > 0
      ? current.findIndex(
          (item) => item.thought === thought && (item.status === "streaming" || item.status === "ok") && !item.action
        )
      : -1;
  if (thoughtMatchIndex >= 0) {
    const next = [...current];
    next[thoughtMatchIndex] = {
      ...next[thoughtMatchIndex],
      ts: new Date().toISOString(),
      action: audit.final_decision.action,
      modelTag: audit.model_tag,
      status: audit.status,
    };
    return next;
  }
  const existingIndex = current.findIndex((item) => item.id === `audit:${audit.prompt_hash}`);
  if (existingIndex >= 0) {
    const next = [...current];
    next[existingIndex] = {
      ...next[existingIndex],
      ts: new Date().toISOString(),
      action: audit.final_decision.action,
      modelTag: audit.model_tag,
      status: audit.status,
      thought: thought || next[existingIndex].thought,
    };
    return next;
  }
  const entry: AgentStreamEntry = {
    id: `audit:${audit.prompt_hash}`,
    ts: new Date().toISOString(),
    playerId: "agent",
    playerName: "Agent",
    avatar: avatarForPlayer("agent"),
    action: audit.final_decision.action,
    modelTag: audit.model_tag,
    status: audit.status,
    thought: thought || audit.raw_response_summary,
  };
  const merged = [...current, entry];
  if (merged.length <= MAX_AGENT_STREAM) {
    return merged;
  }
  return merged.slice(merged.length - MAX_AGENT_STREAM);
}

function upsertThoughtDelta(current: AgentStreamEntry[], payload: WsStateSyncPayload): AgentStreamEntry[] {
  if (!payload.player_id || typeof payload.turn_index !== "number" || !payload.delta) {
    return current;
  }
  const id = `thought:${payload.player_id}:${payload.turn_index}`;
  const playerId = payload.player_id;
  const playerName = payload.player_name || payload.player_id;
  const index = current.findIndex((item) => item.id === id);
  if (index >= 0) {
    const next = [...current];
    next[index] = {
      ...next[index],
      ts: payload.ts || new Date().toISOString(),
      thought: `${next[index].thought}${payload.delta}`,
      status: "streaming",
    };
    return next;
  }
  const entry: AgentStreamEntry = {
    id,
    ts: payload.ts || new Date().toISOString(),
    playerId,
    playerName,
    avatar: avatarForPlayer(playerId),
    action: "",
    modelTag: "",
    status: "streaming",
    thought: payload.delta,
  };
  const merged = [...current, entry];
  return merged.length <= MAX_AGENT_STREAM ? merged : merged.slice(merged.length - MAX_AGENT_STREAM);
}

function completeThought(current: AgentStreamEntry[], payload: WsStateSyncPayload): AgentStreamEntry[] {
  if (!payload.player_id || typeof payload.turn_index !== "number") {
    return current;
  }
  const id = `thought:${payload.player_id}:${payload.turn_index}`;
  const index = current.findIndex((item) => item.id === id);
  if (index < 0) {
    return current;
  }
  const next = [...current];
  next[index] = {
    ...next[index],
    ts: payload.ts || new Date().toISOString(),
    thought: payload.full_text || next[index].thought,
    status: "ok",
  };
  return next;
}

export const useGameStore = create<GameStore>((set, get) => ({
  gameId: "",
  roomName: "",
  state: null,
  timeline: [],
  replay: null,
  replayIndex: 0,
  summary: null,
  activeAudit: null,
  activeContext: null,
  agentStream: [],
  wsStatus: "idle",
  wsRetryCount: 0,
  isBusy: false,
  error: null,
  wsClient: null,
  availableGames: [],

  setGameId: (gameId) => {
    set({ gameId, error: null });
  },

  setRoomName: (roomName) => {
    set({ roomName, error: null });
  },

  refreshGameList: async () => {
    try {
      const games = await gamesApi.listGames();
      set({ availableGames: games });
    } catch (error) {
      set({ error: `games list failed: ${String(error)}` });
    }
  },

  createAndLoadGame: async (payload) => {
    set({ isBusy: true, error: null });
    try {
      const created = await gamesApi.createGame(payload);
      set({
        gameId: created.game_id,
        roomName: payload.room_name ?? created.game_id,
        state: created.state,
        timeline: created.state.last_events,
        replay: null,
        replayIndex: 0,
        summary: null,
        activeAudit: null,
        activeContext: null,
        agentStream: [],
      });
      await get().refreshGameList();
      get().connectWs();
      return created.game_id;
    } catch (error) {
      set({ error: `create game failed: ${String(error)}` });
      return null;
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
        if (payload.type === "agent.thought.delta") {
          set((current) => ({
            agentStream: upsertThoughtDelta(current.agentStream, payload),
          }));
          return;
        }
        if (payload.type === "agent.thought.done") {
          set((current) => ({
            agentStream: completeThought(current.agentStream, payload),
          }));
          return;
        }
        set((current) => {
          const incomingEvents = payload.event ? [payload.event] : [];
          const nextTimeline = appendTimeline(current.timeline, incomingEvents);
          return {
            state: payload.state ?? current.state,
            timeline: nextTimeline,
            activeAudit: payload.audit ?? current.activeAudit,
            activeContext: payload.agent_context ?? current.activeContext,
            agentStream: appendAgentStream(current.agentStream, payload.audit),
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
      const result = await gamesApi.submitAction(currentState.game_id, currentState.current_player_id, action, args);
      set((current) => {
        const incomingEvents = result.event ? [result.event] : [];
        return {
          state: result.state ?? current.state,
          timeline: appendTimeline(current.timeline, incomingEvents),
          activeAudit: result.audit ?? current.activeAudit,
          agentStream: appendAgentStream(current.agentStream, result.audit),
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
      const result = await gamesApi.triggerAgent(currentState.game_id, currentState.current_player_id);
      set((current) => {
        const incomingEvents = result.event ? [result.event] : [];
        return {
          state: result.state ?? current.state,
          timeline: appendTimeline(current.timeline, incomingEvents),
          activeAudit: result.audit ?? current.activeAudit,
          agentStream: appendAgentStream(current.agentStream, result.audit),
          error: result.accepted ? null : result.message,
        };
      });
    } catch (error) {
      set({ error: `agent action failed: ${String(error)}` });
    } finally {
      set({ isBusy: false });
    }
  },

  autoPlayAgents: async (maxSteps = 16) => {
    const currentState = get().state;
    if (!currentState) {
      set({ error: "state 未加载" });
      return;
    }

    set({ isBusy: true, error: null });
    try {
      const result = await gamesApi.autoPlayAgents(currentState.game_id, maxSteps);
      const latestAudit = result.audits.length > 0 ? result.audits[result.audits.length - 1] : null;
      set((current) => {
        let nextStream = current.agentStream;
        for (const audit of result.audits) {
          nextStream = appendAgentStream(nextStream, audit);
        }
        return {
          state: result.state,
          timeline: appendTimeline(current.timeline, result.state.last_events),
          activeAudit: latestAudit ?? current.activeAudit,
          agentStream: nextStream,
          error: result.steps > 0 || result.stopped_reason === "human_turn" ? null : result.stopped_reason,
        };
      });
    } catch (error) {
      set({ error: `auto play failed: ${String(error)}` });
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
