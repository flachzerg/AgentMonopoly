import { ModelAvatar } from "./ModelAvatar";
import { inferModelTag } from "../lib/modelAvatar";

type PreviewPlayer = {
  player_id: string;
  name: string;
  is_agent: boolean;
  model: string;
};

type SetupPreviewPanelProps = {
  roomName: string;
  maxPlayers: number;
  maxRounds: number;
  mapAsset: string;
  mapAssetLabel: string;
  players: PreviewPlayer[];
};

export function SetupPreviewPanel({ roomName, maxPlayers, maxRounds, mapAsset, mapAssetLabel, players }: SetupPreviewPanelProps) {
  const normalizedRoomName = roomName.trim() || "未命名房间";
  const resolvedLabel = mapAssetLabel.trim() ? mapAssetLabel : mapAsset;

  return (
    <aside className="panel preview-stack">
      <div className="section-heading">
        <p className="eyebrow">即时预览</p>
        <h2>对局预览</h2>
      </div>

      <div className="preview-block">
        <p className="preview-label">房间名称</p>
        <p className="preview-value">{normalizedRoomName}</p>
      </div>

      <div className="preview-block">
        <p className="preview-label">人数 / 回合</p>
        <p className="preview-value">
          {maxPlayers} 人 · {maxRounds} 回合
        </p>
      </div>

      <div className="preview-block">
        <p className="preview-label">地图主题</p>
        <p className="preview-value">{resolvedLabel}</p>
      </div>

      <div className="preview-block">
        <p className="preview-label">玩家配置</p>
        <div className="preview-model-list">
          {players.map((player, index) => (
            <div key={player.player_id} className="preview-model">
              <div className="player-identity">
                <ModelAvatar
                  officialModelId={player.model}
                  displayName={player.name}
                  vendorName={player.model.split("/")[0]}
                  size={30}
                />
                <div className="player-identity__text">
                  <span className="preview-model__seat">{index + 1} 号位 · {player.player_id}</span>
                  <span className="preview-model__name">{player.name.trim() || "未命名玩家"}</span>
                  <span className="preview-model__meta">
                    {player.is_agent
                      ? `AI · ${inferModelTag({
                          modelId: player.model,
                          displayName: player.name,
                          vendorName: player.model.split("/")[0],
                          isAgent: true,
                        })}`
                      : "真人 · human"}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
