import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { gamesApi } from "../services/api";
import { useGameStore } from "../store/gameStore";
import type { AgentOptions, CreateGameRequest } from "../types/game";

type PlayerDraft = {
  player_id: string;
  name: string;
  is_agent: boolean;
  model: string;
};

const FALLBACK_MODELS = [
  "qwen/qwen-plus-2025-07-28",
  "qwen/qwen3-max",
  "qwen/qwen3-235b-a22b-2507",
  "qwen/qwen3-coder-plus",
  "deepseek/deepseek-chat-v3.1",
  "deepseek/deepseek-v3.2",
  "moonshotai/kimi-k2-0905",
  "z-ai/glm-5.1",
  "minimax/minimax-m2.7",
  "deepseek/deepseek-r1",
];

function createDefaultPlayers(maxPlayers: number, model: string): PlayerDraft[] {
  return Array.from({ length: maxPlayers }, (_, index) => ({
    player_id: `p${index + 1}`,
    name: index === 0 ? "玩家A" : `Agent-${index + 1}`,
    is_agent: index !== 0,
    model,
  }));
}

export default function SetupPage() {
  const navigate = useNavigate();
  const { createAndLoadGame, isBusy, error, setRoomName } = useGameStore();

  const [roomName, setRoomNameInput] = useState("开放体验房");
  const [maxPlayers, setMaxPlayers] = useState(4);
  const [maxRounds, setMaxRounds] = useState(20);
  const [seed, setSeed] = useState(20260418);
  const [agentOptions, setAgentOptions] = useState<AgentOptions | null>(null);
  const [players, setPlayers] = useState<PlayerDraft[]>([]);

  const models = useMemo(() => {
    if (agentOptions && agentOptions.model_options.length > 0) {
      return agentOptions.model_options;
    }
    return FALLBACK_MODELS;
  }, [agentOptions]);

  const defaultModel = models[0] ?? "qwen/qwen-plus-2025-07-28";

  useEffect(() => {
    void (async () => {
      try {
        const options = await gamesApi.getAgentOptions();
        setAgentOptions(options);
      } catch {
        setAgentOptions(null);
      }
    })();
  }, []);

  useEffect(() => {
    setPlayers((current) => {
      if (current.length === 0) {
        return createDefaultPlayers(maxPlayers, defaultModel);
      }
      if (current.length === maxPlayers) {
        return current;
      }
      if (current.length > maxPlayers) {
        return current.slice(0, maxPlayers);
      }
      const append: PlayerDraft[] = [];
      for (let i = current.length; i < maxPlayers; i += 1) {
        append.push({
          player_id: `p${i + 1}`,
          name: `Agent-${i + 1}`,
          is_agent: true,
          model: defaultModel,
        });
      }
      return [...current, ...append];
    });
  }, [maxPlayers, defaultModel]);

  const onChangePlayer = (idx: number, patch: Partial<PlayerDraft>) => {
    setPlayers((current) => current.map((item, i) => (i === idx ? { ...item, ...patch } : item)));
  };

  const onStartGame = async () => {
    if (players.length < 2) {
      return;
    }
    const payload: CreateGameRequest = {
      game_id: roomName.trim().toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5-_]+/g, "-") || `room-${Date.now()}`,
      room_name: roomName.trim(),
      players: players.map((item) => ({
        player_id: item.player_id,
        name: item.name,
        is_agent: item.is_agent,
        agent_config: item.is_agent
          ? {
              model: item.model,
            }
          : null,
      })),
      max_rounds: maxRounds,
      seed,
    };

    setRoomName(roomName.trim());
    const gameId = await createAndLoadGame(payload);
    if (gameId) {
      navigate(`/game/${encodeURIComponent(gameId)}`);
    }
  };

  return (
    <div className="setup-page">
      <section className="setup-header panel">
        <h1>AgentMonopoly 对局配置</h1>
        <p>先完成房间与玩家配置，点击开始后会进入全新的对局页面。</p>
      </section>

      <section className="panel setup-grid">
        <label className="field">
          <span>房间名称</span>
          <input value={roomName} onChange={(e) => setRoomNameInput(e.target.value)} placeholder="输入房间名称" />
        </label>
        <label className="field">
          <span>最大人数</span>
          <select value={maxPlayers} onChange={(e) => setMaxPlayers(Number(e.target.value))}>
            {[2, 3, 4, 5, 6].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>最大回合</span>
          <input type="number" min={5} max={200} value={maxRounds} onChange={(e) => setMaxRounds(Number(e.target.value))} />
        </label>
        <label className="field">
          <span>随机种子</span>
          <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} />
        </label>
      </section>

      <section className="panel">
        <div className="panel-title-row">
          <h2>玩家与 AI 配置</h2>
          <div className="tiny-note">模型列表校验日期：{agentOptions?.models_checked_at ?? "2026-04-18"}</div>
        </div>

        <div className="player-table-wrap">
          <table className="player-table">
            <thead>
              <tr>
                <th>席位</th>
                <th>玩家名称</th>
                <th>操控方式</th>
                <th>模型</th>
              </tr>
            </thead>
            <tbody>
              {players.map((player, index) => (
                <tr key={player.player_id}>
                  <td>{player.player_id}</td>
                  <td>
                    <input
                      value={player.name}
                      onChange={(e) => onChangePlayer(index, { name: e.target.value })}
                      placeholder="输入玩家名称"
                    />
                  </td>
                  <td>
                    <select
                      value={player.is_agent ? "ai" : "human"}
                      onChange={(e) => onChangePlayer(index, { is_agent: e.target.value === "ai" })}
                    >
                      <option value="human">真人</option>
                      <option value="ai">AI</option>
                    </select>
                  </td>
                  <td>
                    <select
                      disabled={!player.is_agent}
                      value={player.model}
                      onChange={(e) => onChangePlayer(index, { model: e.target.value })}
                    >
                      {models.map((modelId) => (
                        <option key={modelId} value={modelId}>
                          {modelId}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted">当前阶段 API Key 不在页面录入，后续可通过配置文件注入。</p>
      </section>

      <section className="panel setup-footer">
        <button type="button" className="btn-primary" disabled={isBusy} onClick={onStartGame}>
          开始对局
        </button>
        {error ? <p className="error-text">{error}</p> : null}
      </section>
    </div>
  );
}
