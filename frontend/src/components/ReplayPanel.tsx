import { useMemo, type FC } from "react";

import { getGamePlayerProfiles, inferModelTag } from "../lib/modelAvatar";
import type { PlayerSnapshot, ReplayResponse, ReplaySummary, ReplayStep } from "../types/game";
import { ModelAvatar } from "./ModelAvatar";

type Props = {
  replay: ReplayResponse | null;
  summary: ReplaySummary | null;
  isBusy?: boolean;
  error?: string | null;
  onNewGame: () => void;
  onBackToGame: () => void;
};

type PlayerProfile = {
  player_id: string;
  style: string;
  highlights: string[];
  issues: string[];
  is_winner: boolean;
};

type RecapView = {
  overview: string;
  player_profiles: PlayerProfile[];
};

type RankedPlayer = {
  player: PlayerSnapshot;
  rank: number;
  cashDelta: number;
  netWorthDelta: number;
  profile: PlayerProfile | null;
  color: string;
};

const chartColors = ["#1f5f99", "#0f766e", "#b45309", "#7c3aed", "#b91c1c", "#64748b"];
const initialCash = 2000;
const initialNetWorth = 2500;

function asRecord(input: unknown): Record<string, unknown> {
  return input && typeof input === "object" ? (input as Record<string, unknown>) : {};
}

function asStringArray(input: unknown): string[] {
  if (!Array.isArray(input)) {
    return [];
  }
  return input.filter((item): item is string => typeof item === "string");
}

function buildRecapView(summary: ReplaySummary | null): RecapView | null {
  if (!summary) {
    return null;
  }

  const recap = asRecord(summary.recap);
  const playerProfilesRaw = Array.isArray(recap.player_profiles) ? recap.player_profiles : [];
  const player_profiles: PlayerProfile[] = playerProfilesRaw.map((item) => {
    const row = asRecord(item);
    return {
      player_id: typeof row.player_id === "string" ? row.player_id : "unknown",
      style: typeof row.style === "string" ? row.style : "未定义",
      highlights: asStringArray(row.highlights),
      issues: asStringArray(row.issues),
      is_winner: Boolean(row.is_winner),
    };
  });

  return {
    overview: typeof recap.overview === "string" ? recap.overview : "暂无全局结论。",
    player_profiles,
  };
}

function findPlayer(step: ReplayStep | undefined, playerId: string): PlayerSnapshot | null {
  return step?.state.players.find((item) => item.player_id === playerId) ?? null;
}

function formatMoney(value: number): string {
  return Number.isFinite(value) ? Math.round(value).toLocaleString("zh-CN") : "0";
}

function buildRankedPlayers(replay: ReplayResponse | null, recap: RecapView | null): RankedPlayer[] {
  const latestStep = replay && replay.steps.length > 0 ? replay.steps[replay.steps.length - 1] : undefined;
  if (!latestStep) {
    return [];
  }

  const profileMap = new Map((recap?.player_profiles ?? []).map((item) => [item.player_id, item]));

  return [...latestStep.state.players]
    .sort((a, b) => b.net_worth - a.net_worth)
    .map((player, index) => {
      return {
        player,
        rank: index + 1,
        cashDelta: player.cash - initialCash,
        netWorthDelta: player.net_worth - initialNetWorth,
        profile: profileMap.get(player.player_id) ?? null,
        color: chartColors[index % chartColors.length],
      };
    });
}

function buildTrendText(replay: ReplayResponse | null, recap: RecapView | null, rankedPlayers: RankedPlayer[]): string {
  if (!replay || replay.steps.length === 0 || rankedPlayers.length === 0) {
    return "复盘数据尚未载入。页面会基于行动日志、AI 决策痕迹与时间轴生成全局判断，并展示现金曲线和玩家点评。";
  }

  const leader = rankedPlayers[0];
  const lastStep = replay.steps[replay.steps.length - 1];
  const totalEvents = replay.steps.reduce((total, step) => total + step.events.length, 0);
  const aliveCount = rankedPlayers.filter((item) => item.player.alive).length;
  const strongestCash = [...rankedPlayers].sort((a, b) => b.player.cash - a.player.cash)[0];
  const overview = recap?.overview && recap.overview !== "暂无全局结论。" ? recap.overview : "本局节奏由现金曲线和关键行动共同推动，玩家之间的差距主要体现在资金稳定性、地产数量与后段承压能力。";

  return `本局共推进 ${replay.steps.length} 手，记录 ${totalEvents} 条关键动作，最后停在第 ${lastStep?.state.round_index ?? 0} 轮第 ${lastStep?.state.turn_index ?? 0} 手。${overview} 最终 ${leader.player.name} 以总资产 ${formatMoney(leader.player.net_worth)} 排名第一，${strongestCash.player.name} 的现金余量最高，仍在场玩家 ${aliveCount} 人。整体看，前段以位置推进和资产布局为主，中段开始出现现金分化，后段排名变化更多取决于是否能维持可行动资金。`;
}

function buildPlayerComment(item: RankedPlayer): string {
  const propertyCount = item.player.property_ids.length;
  const cashMove = item.cashDelta >= 0 ? `现金增加 ${formatMoney(item.cashDelta)}` : `现金减少 ${formatMoney(Math.abs(item.cashDelta))}`;
  const worthMove = item.netWorthDelta >= 0 ? `总资产增加 ${formatMoney(item.netWorthDelta)}` : `总资产减少 ${formatMoney(Math.abs(item.netWorthDelta))}`;
  const style = item.profile?.style && item.profile.style !== "未定义" ? `行为风格偏向${item.profile.style}。` : "行为风格暂未形成稳定标签。";
  const highlight = item.profile?.highlights[0] ? `主要亮点是${item.profile.highlights[0]}。` : "主要表现来自资金与位置变化。";
  const issue = item.profile?.issues[0] ? `下一局需要注意${item.profile.issues[0]}。` : "下一局应继续优化现金安全线与资产节奏。";

  return `${style}${cashMove}，${worthMove}，持有 ${propertyCount} 处地产。${highlight}${issue}`;
}

function CashTrendChart({ replay, rankedPlayers }: { replay: ReplayResponse | null; rankedPlayers: RankedPlayer[] }) {
  const steps = replay?.steps ?? [];
  const width = 1640;
  const height = 220;
  const padding = { top: 16, right: 34, bottom: 32, left: 52 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const cashSeries = rankedPlayers.map((ranked) => [
    initialCash,
    ...steps.map((step) => findPlayer(step, ranked.player.player_id)?.cash ?? ranked.player.cash),
  ]);
  const pointCount = steps.length + 1;
  const leaderCash = rankedPlayers[0]?.player.cash ?? initialCash;
  const minValue = 0;
  const maxValue = Math.max(leaderCash, 1);
  const range = Math.max(maxValue - minValue, 1);
  const xFor = (index: number) => padding.left + (pointCount <= 1 ? chartWidth / 2 : (index / (pointCount - 1)) * chartWidth);
  const yFor = (value: number) => padding.top + chartHeight - ((value - minValue) / range) * chartHeight;
  const guideValues = [maxValue, minValue + range / 2, minValue];

  if (steps.length === 0 || rankedPlayers.length === 0) {
    return <p className="replay-empty-note">暂无现金曲线数据。</p>;
  }

  return (
    <div className="cash-chart-wrap" role="img" aria-label="玩家现金变化折线图">
      <svg className="cash-chart" viewBox={`0 0 ${width} ${height}`}>
        {guideValues.map((value) => {
          const y = yFor(value);
          return (
            <g key={`guide-${value}`}>
              <line x1={padding.left} x2={width - padding.right} y1={y} y2={y} className="cash-chart__guide" />
              <text x={padding.left - 12} y={y + 4} textAnchor="end" className="cash-chart__axis-label">
                {formatMoney(value)}
              </text>
            </g>
          );
        })}
        <line x1={padding.left} x2={padding.left} y1={padding.top} y2={height - padding.bottom} className="cash-chart__axis" />
        <line x1={padding.left} x2={width - padding.right} y1={height - padding.bottom} y2={height - padding.bottom} className="cash-chart__axis" />
        {rankedPlayers.map((ranked, seriesIndex) => {
          const points = cashSeries[seriesIndex].map((cash, index) => `${xFor(index)},${yFor(cash)}`).join(" ");
          return <polyline key={ranked.player.player_id} points={points} fill="none" stroke={ranked.color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />;
        })}
        {Array.from({ length: pointCount }, (_item, index) => {
          const labelStep = pointCount <= 21 ? 1 : Math.ceil(pointCount / 10);
          if (index !== 0 && index !== pointCount - 1 && index % labelStep !== 0) {
            return null;
          }
          const textAnchor = index === 0 ? "start" : index === pointCount - 1 ? "end" : "middle";
          return (
            <g key={`x-${index}`}>
              <line x1={xFor(index)} x2={xFor(index)} y1={height - padding.bottom} y2={height - padding.bottom + 5} className="cash-chart__tick" />
              <text x={xFor(index)} y={height - 14} textAnchor={textAnchor} className="cash-chart__axis-label cash-chart__axis-label--x">
                {`第${index}手`}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="cash-chart-legend">
        {rankedPlayers.map((ranked) => (
          <span key={`legend-${ranked.player.player_id}`}>
            <i style={{ background: ranked.color }} />
            {ranked.player.name}
          </span>
        ))}
      </div>
    </div>
  );
}

export const ReplayPanel: FC<Props> = ({ replay, summary, isBusy = false, error = null, onNewGame, onBackToGame }) => {
  const recap = useMemo(() => buildRecapView(summary), [summary]);
  const rankedPlayers = useMemo(() => buildRankedPlayers(replay, recap), [replay, recap]);
  const storedProfiles = useMemo(() => getGamePlayerProfiles(replay?.game_id ?? summary?.game_id ?? ""), [replay?.game_id, summary?.game_id]);
  const trendText = useMemo(() => buildTrendText(replay, recap, rankedPlayers), [replay, recap, rankedPlayers]);
  const gameId = replay?.game_id ?? summary?.game_id ?? "未命名对局";

  return (
    <section className="panel replay-panel replay-report">
      <header className="replay-report__hero">
        <div className="replay-report__title-block">
          <p className="poster-kicker">GLOBAL GAME REPORT</p>
          <h1>全局复盘</h1>
          <p className="replay-report__subtitle">{gameId} · 以行动日志、AI 决策痕迹与时间轴生成最终判断</p>
        </div>
        <div className="replay-report__actions">
          <button type="button" className="btn-secondary replay-report__button" onClick={onNewGame}>
            新建对局
          </button>
          <button type="button" className="btn-secondary replay-report__button replay-report__button--primary" onClick={onBackToGame}>
            返回对局
          </button>
        </div>
      </header>

      {isBusy ? <p className="replay-status-note">正在加载复盘数据...</p> : null}
      {error ? <p className="error-text replay-status-note">{error}</p> : null}

      <section className="replay-report__section replay-report__summary">
        <div className="replay-section-heading">
          <span>01</span>
          <h2>全局趋势总结</h2>
        </div>
        <p>{trendText}</p>
      </section>

      <section className="replay-report__section">
        <div className="replay-section-heading">
          <span>02</span>
          <h2>现金变化</h2>
        </div>
        <CashTrendChart replay={replay} rankedPlayers={rankedPlayers} />
      </section>

      <section className="replay-report__section replay-report__players">
        <div className="replay-section-heading">
          <span>03</span>
          <h2>玩家点评</h2>
        </div>
        <div className="replay-player-list">
          {rankedPlayers.length > 0 ? (
            rankedPlayers.map((ranked) => {
              const stored = storedProfiles[ranked.player.player_id];
              const modelTag = inferModelTag({
                modelId: stored?.model ?? null,
                displayName: ranked.player.name,
                vendorName: stored?.model?.split("/")[0] ?? null,
                isAgent: ranked.player.is_agent,
              });
              return (
                <article key={ranked.player.player_id} className="replay-player-row">
                  <div className="replay-player-rank">NO.{ranked.rank}</div>
                  <ModelAvatar
                    officialModelId={stored?.model ?? null}
                    displayName={ranked.player.name}
                    vendorName={stored?.model?.split("/")[0] ?? null}
                    size={28}
                  />
                  <div className="replay-player-main">
                    <div className="replay-player-title">
                      <h3>{ranked.player.name}</h3>
                      <span>{ranked.player.is_agent ? `AI · ${modelTag}` : "真人 · human"}</span>
                    </div>
                    <p>{buildPlayerComment(ranked)}</p>
                  </div>
                  <div className="replay-player-metrics">
                    <span>总资产 {formatMoney(ranked.player.net_worth)}</span>
                    <span>现金 {formatMoney(ranked.player.cash)}</span>
                    <span>地产 {ranked.player.property_ids.length}</span>
                  </div>
                </article>
              );
            })
          ) : (
            <p className="replay-empty-note">暂无玩家表现数据。</p>
          )}
        </div>
      </section>
    </section>
  );
};
