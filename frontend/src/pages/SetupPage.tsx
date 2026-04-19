import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ModelAvatar } from "../components/ModelAvatar";
import { DEFAULT_AGENT_MODEL, FALLBACK_MODELS } from "../constants/agentModels";
import { saveGamePlayerProfiles } from "../lib/modelAvatar";
import { gamesApi } from "../services/api";
import { useGameStore } from "../store/gameStore";
import type { AgentOptions, CreateGameRequest, MapOptions } from "../types/game";

type PlayerDraft = {
  player_id: string;
  name: string;
  is_agent: boolean;
  model: string;
};

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
  const [mapOptions, setMapOptions] = useState<MapOptions | null>(null);
  const [mapAsset, setMapAsset] = useState("default");
  const [formError, setFormError] = useState<string>("");
  const [agentOptions, setAgentOptions] = useState<AgentOptions | null>(null);
  const [players, setPlayers] = useState<PlayerDraft[]>([]);
  const [showIntroModal, setShowIntroModal] = useState(true);
  const [showApiKeyModal, setShowApiKeyModal] = useState(false);

  const models = useMemo(() => {
    if (agentOptions && agentOptions.model_options.length > 0) {
      return agentOptions.model_options;
    }
    if (agentOptions?.default_model) {
      return [agentOptions.default_model];
    }
    return FALLBACK_MODELS;
  }, [agentOptions]);

  const defaultModel = agentOptions?.default_model ?? models[0] ?? DEFAULT_AGENT_MODEL;
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
        if (agentOpts.provider === "openai-compatible" && agentOpts.has_api_key === false) {
          setShowApiKeyModal(true);
        }
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
      const validModels = new Set(models);
      if (current.length === 0) {
        return createDefaultPlayers(maxPlayers, defaultModel);
      }
      if (current.length === maxPlayers) {
        const normalized = current.map((item) => {
          if (!item.is_agent) {
            return item;
          }
          if (!item.model || !validModels.has(item.model)) {
            return { ...item, model: defaultModel };
          }
          return item;
        });
        const changed = normalized.some((item, idx) => item.model !== current[idx].model);
        return changed ? normalized : current;
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

  const onCloseIntro = () => {
    setShowIntroModal(false);
  };

  const onStartGame = async () => {
    if (agentOptions?.provider === "openai-compatible" && agentOptions.has_api_key === false) {
      setFormError("缺少模型 API Key：请先在 backend/config/agent_options.placeholder.json 填入自己的 key，然后重启后端。");
      setShowApiKeyModal(true);
      return;
    }
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
      seed: 20260418,
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
      <div className="setup-watermark setup-watermark--openai" aria-hidden="true">
        OpenAI
      </div>
      <div className="setup-watermark setup-watermark--anthropic" aria-hidden="true">
        Anthropic
      </div>
      <div className="setup-watermark setup-watermark--qwen" aria-hidden="true">
        Qwen
      </div>
      <div className="setup-watermark setup-watermark--deepseek" aria-hidden="true">
        DeepSeek
      </div>
      {showIntroModal ? (
        <div className="setup-intro-backdrop" role="dialog" aria-modal="true" aria-labelledby="setup-intro-title">
          <section className="setup-intro-modal">
            <button className="setup-intro-close" type="button" aria-label="关闭欢迎弹窗" onClick={onCloseIntro}>
              ×
            </button>
            <div className="setup-intro-kicker">AI STRATEGY MAP</div>
            <h2 id="setup-intro-title">欢迎来到 Agent Monopoly</h2>
            <p className="setup-intro-lead">
              这是一场多模型策略博弈。你可以配置地图、回合与玩家席位，让真人和 AI 在同一规则下竞争、协作、承担风险并积累经验。
            </p>
            <div className="setup-intro-routes">
              <div>
                <strong>01</strong>
                <span>选择地图与回合，确定本局约束。</span>
              </div>
              <div>
                <strong>02</strong>
                <span>安排真人或 AI 席位，对比不同模型的策略差异。</span>
              </div>
              <div>
                <strong>03</strong>
                <span>进入对局后观察决策、事件与收益变化，结束后查看复盘。</span>
              </div>
            </div>
          </section>
        </div>
      ) : null}
      {showApiKeyModal ? (
        <div className="setup-intro-backdrop" role="dialog" aria-modal="true" aria-labelledby="setup-apikey-title">
          <section className="setup-intro-modal">
            <button
              className="setup-intro-close"
              type="button"
              aria-label="关闭 API Key 弹窗"
              onClick={() => setShowApiKeyModal(false)}
            >
              ×
            </button>
            <div className="setup-intro-kicker">DEEPSEEK KEY REQUIRED</div>
            <h2 id="setup-apikey-title">需要先填入 DeepSeek 密钥</h2>
            <p className="setup-intro-lead">
              当前仓库采用“前端可选不同厂商型号用于展示与头像，但后端真实调用固定走 DeepSeek”。为了让对局能真实调用模型，请先把你的 key 写到占位符配置文件里。
            </p>
            <div className="setup-intro-routes">
              <div>
                <strong>01</strong>
                <span>打开 `backend/config/agent_options.placeholder.json`</span>
              </div>
              <div>
                <strong>02</strong>
                <span>把 `api_key` 填成你的 DeepSeek key（例如 `sk-...`）</span>
              </div>
              <div>
                <strong>03</strong>
                <span>重启后端（`bash scripts/dev_restart.sh restart`）再开始对局</span>
              </div>
            </div>
          </section>
        </div>
      ) : null}
      <form
        className="panel setup-command-panel"
        onSubmit={(event) => {
          event.preventDefault();
          void onStartGame();
        }}
      >
        <header className="setup-command-header">
          <div className="setup-map-head">
            <div>
              <p className="eyebrow">AgentMonopoly</p>
              <h1>开局控制台</h1>
              <p>30 秒完成房间配置，直接进入对局。你只负责关键决策，流程由系统自动推进。</p>
            </div>
            <div className="setup-map-meta" aria-hidden="true">
              <span>AI STRATEGY SETUP</span>
              <span>v1.0</span>
            </div>
          </div>
          <div className="setup-hero-stats">
            <span>
              <strong>{maxPlayers}</strong>
              当前席位
            </span>
            <span>
              <strong>{maxRounds}</strong>
              回合上限
            </span>
            <span>
              <strong>{mapAssetLabel}</strong>
              地图主题
            </span>
          </div>
        </header>

        <div className="setup-command-body">
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
                <span>地图主题</span>
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
                  <div className="seat-card__header">
                    <span className="seat-card__badge">P{index + 1}</span>
                    <ModelAvatar
                      officialModelId={player.model}
                      displayName={player.name}
                      vendorName={player.model.split("/")[0]}
                      size={34}
                    />
                    <div className="player-identity__text">
                      <p className="seat-card__title">{player.name || "未命名玩家"}</p>
                      <p className="tiny-note">{player.is_agent ? "AI" : "真人 · human"}</p>
                    </div>
                  </div>
                  <div className={player.is_agent ? "seat-card__controls" : "seat-card__controls seat-card__controls--human"}>
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
                    {player.is_agent ? (
                      <label className="field seat-card__model-field">
                        <span>模型 ID</span>
                        <select value={player.model} onChange={(e) => onChangePlayer(index, { model: e.target.value })}>
                          {models.map((modelId) => (
                            <option key={modelId} value={modelId}>
                              {modelId}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
            <p className="muted">当前阶段 API Key 不在页面录入，后续可通过配置文件注入。</p>
          </section>
        </div>

        <section className="setup-footer">
          <button type="submit" className="btn-primary" disabled={isBusy}>
            开始对局
          </button>
          {formError ? <p className="error-text">{formError}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}
        </section>
      </form>
    </div>
  );
}
