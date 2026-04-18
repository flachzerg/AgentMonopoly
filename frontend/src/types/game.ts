export type ActionOption = {
  action: string;
  description: string;
  required_args: string[];
  allowed_values: Record<string, unknown[]>;
  default_args: Record<string, unknown>;
};

export type PlayerSnapshot = {
  player_id: string;
  name: string;
  is_agent: boolean;
  cash: number;
  deposit: number;
  net_worth: number;
  position: number;
  property_ids: string[];
  alliance_with: string | null;
  alive: boolean;
};

export type TileState = {
  tile_id: string;
  tile_index: number;
  tile_type: string;
  tile_subtype: string;
  name: string;
  owner_id: string | null;
  property_price: number | null;
  toll: number | null;
};

export type EventRecord = {
  event_id: string;
  ts: string;
  type: string;
  game_id: string;
  round_index: number;
  turn_index: number;
  payload: Record<string, unknown>;
};

export type DecisionAudit = {
  model_tag: string;
  template_key: string;
  template_version: string;
  prompt_hash: string;
  prompt_token_estimate: number;
  attempt_count: number;
  status: "ok" | "fallback";
  failure_codes: string[];
  raw_response_summary: string;
  fallback_reason: string | null;
  final_decision: {
    protocol: string;
    action: string;
    args: Record<string, unknown>;
    thought: string | null;
    strategy_tags: string[];
    candidate_actions: string[];
    confidence: number | null;
  };
};

export type GameState = {
  game_id: string;
  status: "waiting" | "running" | "finished";
  round_index: number;
  turn_index: number;
  max_rounds: number;
  current_player_id: string;
  current_phase: string;
  active_tile_id: string;
  players: PlayerSnapshot[];
  board: TileState[];
  allowed_actions: ActionOption[];
  last_events: EventRecord[];
};

export type ActionResponse = {
  accepted: boolean;
  message: string;
  state: GameState | null;
  event: EventRecord | null;
  audit: DecisionAudit | null;
};

export type ReplayStep = {
  turn_index: number;
  round_index: number;
  phase: string;
  phase_trace: string[];
  state: GameState;
  events: EventRecord[];
  candidate_actions: string[];
  final_action: string | null;
  strategy_tags: string[];
  decision_audit: DecisionAudit | null;
};

export type ReplayResponse = {
  game_id: string;
  total_turns: number;
  steps: ReplayStep[];
};

export type ReplaySummary = {
  game_id: string;
  generated_at: string;
  metrics: Record<string, number>;
  strategy_timeline: Array<Record<string, unknown>>;
  markdown: string;
};

export type WsStateSyncPayload = {
  type: string;
  state?: GameState;
  event?: EventRecord | null;
  audit?: DecisionAudit;
  message?: string;
};

export type CreateGameRequest = {
  game_id: string;
  players: Array<{
    player_id: string;
    name: string;
    is_agent: boolean;
  }>;
  max_rounds: number;
  seed: number;
};
