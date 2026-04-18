export interface ModelAvatarDescriptor {
  readonly src: string | null;
  readonly fallback: string;
  readonly accent: string;
  readonly background: string;
}

interface AvatarRule {
  readonly key: string;
  readonly src: string;
  readonly accent: string;
  readonly background: string;
  readonly patterns: readonly RegExp[];
}

export type StoredPlayerProfile = {
  player_id: string;
  name: string;
  is_agent: boolean;
  model?: string | null;
};

const PLAYER_PROFILE_STORAGE_KEY = "am-player-profiles-v1";

const avatarRules: readonly AvatarRule[] = [
  {
    key: "deepseek",
    src: "/avatars/deepseek.png",
    accent: "#3854f3",
    background: "linear-gradient(135deg, rgba(56, 84, 243, 0.18), rgba(56, 84, 243, 0.02))",
    patterns: [/deepseek/iu],
  },
  {
    key: "seed",
    src: "/avatars/seed.png",
    accent: "#0f766e",
    background: "linear-gradient(135deg, rgba(15, 118, 110, 0.18), rgba(15, 118, 110, 0.02))",
    patterns: [/seed/iu, /bytedance/iu],
  },
  {
    key: "qwen",
    src: "/avatars/qwen.png",
    accent: "#ff7a00",
    background: "linear-gradient(135deg, rgba(255, 122, 0, 0.18), rgba(255, 122, 0, 0.02))",
    patterns: [/qwen/iu],
  },
  {
    key: "kimi",
    src: "/avatars/kimi.jpeg",
    accent: "#1667d9",
    background: "linear-gradient(135deg, rgba(22, 103, 217, 0.18), rgba(22, 103, 217, 0.02))",
    patterns: [/kimi/iu, /moonshot/iu],
  },
  {
    key: "glm",
    src: "/avatars/glm.webp",
    accent: "#3f3cbb",
    background: "linear-gradient(135deg, rgba(63, 60, 187, 0.18), rgba(63, 60, 187, 0.02))",
    patterns: [/glm/iu, /\bz\.ai\b/iu, /z-ai/iu],
  },
  {
    key: "minimax",
    src: "/avatars/minimax.png",
    accent: "#be185d",
    background: "linear-gradient(135deg, rgba(190, 24, 93, 0.18), rgba(190, 24, 93, 0.02))",
    patterns: [/minimax/iu],
  },
  {
    key: "gemini",
    src: "/avatars/gemini.png",
    accent: "#7c3aed",
    background: "linear-gradient(135deg, rgba(124, 58, 237, 0.18), rgba(124, 58, 237, 0.02))",
    patterns: [/gemini/iu, /google/iu],
  },
  {
    key: "grok",
    src: "/avatars/grok.webp",
    accent: "#111827",
    background: "linear-gradient(135deg, rgba(17, 24, 39, 0.18), rgba(17, 24, 39, 0.02))",
    patterns: [/grok/iu, /\bxai\b/iu, /x-ai/iu],
  },
  {
    key: "claude",
    src: "/avatars/claude.jpeg",
    accent: "#92400e",
    background: "linear-gradient(135deg, rgba(146, 64, 14, 0.18), rgba(146, 64, 14, 0.02))",
    patterns: [/claude/iu, /anthropic/iu],
  },
  {
    key: "gpt",
    src: "/avatars/gpt.png",
    accent: "#047857",
    background: "linear-gradient(135deg, rgba(4, 120, 87, 0.18), rgba(4, 120, 87, 0.02))",
    patterns: [/gpt/iu, /openai/iu, /chatgpt/iu],
  },
] as const;

function pickFallbackLabel(displayName: string | null | undefined): string {
  if (displayName === undefined || displayName === null || displayName.trim().length === 0) {
    return "AI";
  }

  const asciiMatch = displayName.match(/[A-Za-z]{1,3}/u);
  if (asciiMatch !== null) {
    return asciiMatch[0].slice(0, 3).toUpperCase();
  }

  return displayName.trim().slice(0, 2).toUpperCase();
}

function safeParseStorage(raw: string | null): Record<string, StoredPlayerProfile[]> {
  if (!raw) {
    return {};
  }
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, StoredPlayerProfile[]>) : {};
  } catch {
    return {};
  }
}

export function saveGamePlayerProfiles(gameId: string, players: StoredPlayerProfile[]): void {
  if (!gameId || typeof window === "undefined") {
    return;
  }
  const current = safeParseStorage(window.localStorage.getItem(PLAYER_PROFILE_STORAGE_KEY));
  current[gameId] = players;
  window.localStorage.setItem(PLAYER_PROFILE_STORAGE_KEY, JSON.stringify(current));
}

export function getGamePlayerProfiles(gameId: string): Record<string, StoredPlayerProfile> {
  if (!gameId || typeof window === "undefined") {
    return {};
  }
  const current = safeParseStorage(window.localStorage.getItem(PLAYER_PROFILE_STORAGE_KEY));
  const list = current[gameId] ?? [];
  return list.reduce<Record<string, StoredPlayerProfile>>((acc, item) => {
    acc[item.player_id] = item;
    return acc;
  }, {});
}

export function inferModelTag(input: {
  modelId?: string | null;
  displayName?: string | null;
  vendorName?: string | null;
  isAgent?: boolean;
}): string {
  if (input.isAgent === false) {
    return "human";
  }

  if (input.modelId && input.modelId.trim().length > 0) {
    return input.modelId;
  }

  const searchable = [input.displayName ?? "", input.vendorName ?? ""].join(" ");
  const matchedRule = avatarRules.find((rule) => rule.patterns.some((pattern) => pattern.test(searchable)));
  return matchedRule?.key ?? "unknown-model";
}

export function resolveModelAvatar(input: {
  readonly officialModelId?: string | null | undefined;
  readonly displayName?: string | null | undefined;
  readonly vendorName?: string | null | undefined;
}): ModelAvatarDescriptor {
  const searchable = [input.officialModelId ?? "", input.displayName ?? "", input.vendorName ?? ""].join(" ");

  const matchedRule = avatarRules.find((rule) => rule.patterns.some((pattern) => pattern.test(searchable)));

  if (matchedRule !== undefined) {
    return {
      src: matchedRule.src,
      fallback: pickFallbackLabel(input.displayName),
      accent: matchedRule.accent,
      background: matchedRule.background,
    };
  }

  return {
    src: null,
    fallback: pickFallbackLabel(input.displayName),
    accent: "#1667d9",
    background: "linear-gradient(135deg, rgba(22, 103, 217, 0.18), rgba(22, 103, 217, 0.02))",
  };
}
