import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ModelAvatar } from "../components/ModelAvatar";
import { SetupPreviewPanel } from "../components/SetupPreviewPanel";
import { inferModelTag, saveGamePlayerProfiles } from "../lib/modelAvatar";
import { gamesApi } from "../services/api";
import { useGameStore } from "../store/gameStore";
import type { AgentOptions, CreateGameRequest, MapOptions } from "../types/game";

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

const MAP_ASSET_LABELS: Record<string, string> = {
  default: "default · 经典城市场景",
  theme2: "theme2 · 霓虹夜行场景",
  "01_basic_loop": "01_basic_loop · 16格基础环形",
  "02_basic_branch": "02_basic_branch · 18格基础分支",
  "03_large_loop": "03_large_loop · 24格大型环形",
  "04_large_branch": "04_large_branch · 28格大型分支",
  "05_complex_branch": "05_complex_branch · 36格复杂分支",
  "06_bezier_showcase": "06_bezier_showcase · 贝塞尔演示图",
};

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
  const [mapOptions, setMapOptions] = useState<MapOptions | null>(null);
  const [mapAsset, setMapAsset] = useState("default");
  const [formError, setFormError] = useState<string>("");
  const [agentOptions, setAgentOptions] = useState<AgentOptions | null>(null);
  const [players, setPlayers] = useState<PlayerDraft[]>([]);

  const models = useMemo(() => {
    if (agentOptions && agentOptions.model_options.length > 0) {
      return agentOptions.model_options;
    }
    return FALLBACK_MODELS;
  }, [agentOptions]);

  const defaultModel = models[0] ?? "qwen/qwen-plus-2025-07-28";
  const availableMapAssets = mapOptions?.map_assets?.length ? mapOptions.map_assets : ["default", "theme2"];

  const mapAssetLabel = useMemo(() => {
    return MAP_ASSET_LABELS[mapAsset] ?? mapAsset;
  }, [mapAsset]);

  useEffect(() => {
    void (async () => {
      try {
        const [agentOpts, mapOpts] = await Promise.all([gamesApi.getAgentOptions(), gamesApi.getMapOptions()]);
        setAgentOptions(agentOpts);
        setMapOptions(mapOpts);
        const defaultAsset = mapOpts.default_map_asset || "default";
        const storedAsset = localStorage.getItem("am-map-theme") || "";
        const preferredAsset = (storedAsset && mapOpts.map_assets.includes(storedAsset) ? storedAsset : defaultAsset).trim();
        if (preferredAsset) {
          setMapAsset(preferredAsset);
        }
      } catch {
        setAgentOptions(null);
        setMapOptions(null);
      }
    })();
  }, []);

  useEffect(() => {
    if (availableMapAssets.length === 0) {
      return;
    }
    if (!availableMapAssets.includes(mapAsset)) {
      setMapAsset(availableMapAssets[0]);
    }
  }, [availableMapAssets, mapAsset]);

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
    const normalizedName = roomName.trim();
    if (normalizedName.length < 2) {
      setFormError("房间名称至少需要 2 个字符。");
      return;
    }
    if (maxPlayers < 2 || maxPlayers > 6) {
      setFormError("玩家人数必须在 2 到 6 之间。");
      return;
    }
    if (maxRounds < 5 || maxRounds > 200) {
      setFormError("回合上限必须在 5 到 200 之间。");
      return;
    }
    if (players.length < 2) {
      setFormError("至少需要 2 名玩家。");
      return;
    }
    const hasEmptyName = players.some((item) => item.name.trim().length === 0);
    if (hasEmptyName) {
      setFormError("玩家名称不能为空。");
      return;
    }
    setFormError("");
    const payload: CreateGameRequest = {
      game_id: normalizedName.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5-_]+/g, "-") || `room-${Date.now()}`,
      room_name: normalizedName,
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
      map_asset: mapAsset,
    };

    saveGamePlayerProfiles(
      payload.game_id,
      players.map((item) => ({
        player_id: item.player_id,
        name: item.name,
        is_agent: item.is_agent,
        model: item.is_agent ? item.model : null,
      })),
    );

    setRoomName(normalizedName);
    localStorage.setItem("am-map-theme", mapAsset);
    const gameId = await createAndLoadGame(payload);
    if (gameId) {
      if (gameId !== payload.game_id) {
        saveGamePlayerProfiles(
          gameId,
          players.map((item) => ({
            player_id: item.player_id,
            name: item.name,
            is_agent: item.is_agent,
            model: item.is_agent ? item.model : null,
          })),
        );
      }
      navigate(`/game/${encodeURIComponent(gameId)}`);
    }
  };

  return (
    <div className="setup-page">
      <section className="setup-header panel hero-panel">
        <p className="eyebrow">AgentMonopoly</p>
        <h1>开局控制台</h1>
        <p>30 秒完成房间配置，直接进入对局。你只负责关键决策，流程由系统自动推进。</p>
        <div className="setup-hero-stats">
          <div>
            <strong>{maxPlayers}</strong>
            <span>当前席位</span>
          </div>
          <div>
            <strong>{maxRounds}</strong>
            <span>回合上限</span>
          </div>
          <div>
            <strong>{mapAssetLabel}</strong>
            <span>地图主题</span>
          </div>
        </div>
      </section>

      <div className="create-layout setup-create-layout">
        <form
          className="panel form-stack setup-form-stack"
          onSubmit={(event) => {
            event.preventDefault();
            void onStartGame();
          }}
        >
          <section className="form-section">
            <div className="panel-title-row">
              <h2>房间参数</h2>
            </div>

            <div className="setup-grid setup-core-grid">
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
              <label className="field">
                <span>地图主题（仅 UI 与参数透传）</span>
                <select value={mapAsset} onChange={(e) => setMapAsset(e.target.value)}>
                  {availableMapAssets.map((asset) => (
                    <option key={asset} value={asset}>
                      {MAP_ASSET_LABELS[asset] ?? asset}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </section>

          <section className="form-section">
            <div className="panel-title-row">
              <h2>玩家与 AI 配置</h2>
              <div className="tiny-note">模型列表校验日期：{agentOptions?.models_checked_at ?? "2026-04-18"}</div>
            </div>

            <div className="seat-list setup-seat-list">
              {players.map((player, index) => (
                <article key={player.player_id} className="seat-card">
                  <div className="player-identity player-identity--editor">
                    <ModelAvatar
                      officialModelId={player.model}
                      displayName={player.name}
                      vendorName={player.model.split("/")[0]}
                      size={34}
                    />
                    <div className="player-identity__text">
                      <p className="seat-card__title">{player.player_id} 号席位</p>
                      <p className="tiny-note">{player.name || "未命名玩家"}</p>
                      <p className="tiny-note">
                        {player.is_agent
                          ? `AI · ${inferModelTag({
                              modelId: player.model,
                              displayName: player.name,
                              vendorName: player.model.split("/")[0],
                              isAgent: true,
                            })}`
                          : "真人 · human"}
                      </p>
                    </div>
                  </div>
                  <label className="field">
                    <span>玩家名称</span>
                    <input
                      value={player.name}
                      onChange={(e) => onChangePlayer(index, { name: e.target.value })}
                      placeholder="输入玩家名称"
                    />
                  </label>
                  <label className="field">
                    <span>操控方式</span>
                    <select
                      value={player.is_agent ? "ai" : "human"}
                      onChange={(e) => onChangePlayer(index, { is_agent: e.target.value === "ai" })}
                    >
                      <option value="human">真人</option>
                      <option value="ai">AI</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>模型 ID</span>
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
                  </label>
                </article>
              ))}
            </div>
            <p className="muted">当前阶段 API Key 不在页面录入，后续可通过配置文件注入。</p>
          </section>

          <section className="setup-footer">
            <button type="submit" className="btn-primary" disabled={isBusy}>
              开始对局
            </button>
            {formError ? <p className="error-text">{formError}</p> : null}
            {error ? <p className="error-text">{error}</p> : null}
          </section>
        </form>

        <SetupPreviewPanel
          roomName={roomName}
          maxPlayers={maxPlayers}
          maxRounds={maxRounds}
          mapAsset={mapAsset}
          mapAssetLabel={mapAssetLabel}
          players={players}
        />
      </div>
    </div>
  );
}
