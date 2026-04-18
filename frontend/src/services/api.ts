import type {
  ActionResponse,
  AgentOptions,
  AutoPlayResponse,
  CreateGameResponse,
  CreateGameRequest,
  GameState,
  ReplayResponse,
  ReplaySummary,
} from "../types/game";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${message}`);
  }
  return (await response.json()) as T;
}

export const gamesApi = {
  listGames: async (): Promise<string[]> => {
    const data = await request<{ games: string[] }>("/games");
    return data.games;
  },

  createGame: async (payload: CreateGameRequest): Promise<CreateGameResponse> => {
    return request<CreateGameResponse>("/games", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getState: async (gameId: string): Promise<GameState> => {
    const data = await request<{ state: GameState }>(`/games/${gameId}/state`);
    return data.state;
  },

  submitAction: async (
    gameId: string,
    playerId: string,
    action: string,
    args: Record<string, unknown>
  ): Promise<ActionResponse> =>
    request<ActionResponse>(`/games/${gameId}/actions`, {
      method: "POST",
      body: JSON.stringify({
        game_id: gameId,
        player_id: playerId,
        action,
        args,
      }),
    }),

  triggerAgent: async (gameId: string, playerId: string): Promise<ActionResponse> =>
    request<ActionResponse>(`/games/${gameId}/agent/${playerId}/act`, {
      method: "POST",
    }),

  autoPlayAgents: async (gameId: string, maxSteps = 16): Promise<AutoPlayResponse> =>
    request<AutoPlayResponse>(`/games/${gameId}/auto-play?max_steps=${maxSteps}`, {
      method: "POST",
    }),

  getReplay: async (gameId: string): Promise<ReplayResponse> =>
    request<ReplayResponse>(`/games/${gameId}/replay`),

  getSummary: async (gameId: string): Promise<ReplaySummary> =>
    request<ReplaySummary>(`/games/${gameId}/summary`),

  getAgentOptions: async (): Promise<AgentOptions> =>
    request<AgentOptions>("/games/agent-options"),
};

export function wsUrlForGame(gameId: string): string {
  const raw = (import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000").replace(/\/$/, "");
  return `${raw}/games/${gameId}/ws`;
}
