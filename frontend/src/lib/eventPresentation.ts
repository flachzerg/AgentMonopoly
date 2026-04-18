import type { EventRecord, PlayerSnapshot } from "../types/game";

export type EventSeverity = "normal" | "risk";

type EventMeta = {
  label: string;
};

const EVENT_TYPE_META: Record<string, EventMeta> = {
  "game.started": { label: "对局开始" },
  "game.finished": { label: "对局结束" },
  "turn.logged": { label: "回合记录" },
  "dice.rolled": { label: "掷骰前进" },
  "settlement.applied": { label: "落点结算" },
  "action.accepted": { label: "动作已执行" },
  "action.rejected": { label: "动作被拒绝" },
  "alliance.proposed": { label: "发起联盟" },
  "alliance.created": { label: "联盟达成" },
  "alliance.rejected": { label: "联盟被拒" },
  "auction.sold": { label: "拍卖成交" },
  "player.bankrupt": { label: "玩家破产" },
  "quiz.placeholder": { label: "问答占位" },
};

const ACTION_LABELS: Record<string, string> = {
  roll_dice: "掷骰子",
  buy_property: "买入地产",
  skip_buy: "跳过买入",
  upgrade_property: "升级地产",
  bank_deposit: "存入银行",
  bank_withdraw: "提取存款",
  event_choice: "事件选择",
  propose_alliance: "发起联盟",
  accept_alliance: "同意联盟",
  reject_alliance: "拒绝联盟",
  pass: "跳过",
};

const SETTLEMENT_TYPE_LABELS: Record<string, string> = {
  toll_waived_by_alliance: "联盟免租",
  toll_paid: "支付通行费",
  event_choice_waiting: "等待事件抉择",
  event_delta: "事件资金变化",
  bank_enter: "进入银行",
  no_effect: "无额外效果",
};

function asRecord(input: unknown): Record<string, unknown> {
  return input && typeof input === "object" ? (input as Record<string, unknown>) : {};
}

function pickString(record: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }
  }
  return null;
}

function pickNumber(record: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = Number(record[key]);
    if (Number.isFinite(value)) {
      return value;
    }
  }
  return null;
}

function formatPlayer(playerId: string, playerNameMap: Record<string, string>): string {
  return playerNameMap[playerId] ?? playerId;
}

function formatMoney(value: number): string {
  const abs = Math.abs(value);
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${abs}`;
}

function summarizeSettlement(payload: Record<string, unknown>): string {
  const settlementType = pickString(payload, ["type"]);
  if (settlementType === "toll_paid") {
    const amount = pickNumber(payload, ["amount"]) ?? 0;
    const owner = pickString(payload, ["owner_id"]) ?? "未知方";
    return `支付通行费 ${amount} 给 ${owner}。`;
  }
  if (settlementType === "event_delta") {
    const delta = pickNumber(payload, ["delta"]) ?? 0;
    return `触发事件结算，资金变化 ${formatMoney(delta)}。`;
  }
  if (settlementType === "event_choice_waiting") {
    return "触发事件点，等待玩家完成选项。";
  }
  if (settlementType === "toll_waived_by_alliance") {
    return "因联盟关系免除通行费。";
  }
  if (settlementType === "bank_enter") {
    return "到达银行格，可进行存取款。";
  }
  return "落点结算完成。";
}

export function getEventLabel(event: EventRecord): string {
  const payload = asRecord(event.payload);
  if (event.type === "action.accepted") {
    const action = pickString(payload, ["action"]);
    return action ? ACTION_LABELS[action] ?? `动作执行：${action}` : EVENT_TYPE_META[event.type].label;
  }
  if (event.type === "settlement.applied") {
    const subtype = pickString(payload, ["type"]);
    return subtype ? SETTLEMENT_TYPE_LABELS[subtype] ?? `落点结算：${subtype}` : EVENT_TYPE_META[event.type].label;
  }
  return EVENT_TYPE_META[event.type]?.label ?? event.type;
}

export function getEventParticipants(event: EventRecord, playerNameMap: Record<string, string>): string {
  const payload = asRecord(event.payload);
  const playerIds = new Set<string>();
  const keys = ["player_id", "target_player_id", "requester_player_id", "owner_id", "from_player_id", "to_player_id"];
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.length > 0) {
      playerIds.add(value);
    }
  }
  if (playerIds.size === 0) {
    return "系统";
  }
  return [...playerIds].map((id) => formatPlayer(id, playerNameMap)).join(" / ");
}

export function getEventSummary(event: EventRecord, playerNameMap: Record<string, string>): string {
  const payload = asRecord(event.payload);
  if (event.type === "dice.rolled") {
    const dice = pickNumber(payload, ["dice"]) ?? 0;
    const pos = pickNumber(payload, ["position"]) ?? 0;
    const passedStart = Boolean(payload.passed_start);
    return `掷出 ${dice} 点，移动到格位 ${pos}${passedStart ? "，并经过起点获得奖励" : ""}。`;
  }
  if (event.type === "action.accepted") {
    const action = pickString(payload, ["action"]) ?? "unknown";
    const actor = pickString(payload, ["player_id"]);
    return `${actor ? `${formatPlayer(actor, playerNameMap)}执行` : "执行"}${ACTION_LABELS[action] ?? action}。`;
  }
  if (event.type === "action.rejected") {
    const action = pickString(payload, ["action"]) ?? "unknown";
    const reason = pickString(payload, ["reason"]) ?? "unknown";
    return `动作 ${ACTION_LABELS[action] ?? action} 被拒绝，原因：${reason}。`;
  }
  if (event.type === "settlement.applied") {
    return summarizeSettlement(payload);
  }
  if (event.type === "alliance.created") {
    return "双方建立联盟，后续结算可能触发联盟规则。";
  }
  if (event.type === "alliance.proposed") {
    return "发起联盟邀请，等待目标玩家回应。";
  }
  if (event.type === "alliance.rejected") {
    return "联盟邀请被拒绝，本回合继续独立行动。";
  }
  if (event.type === "auction.sold") {
    const tileId = pickString(payload, ["tile_id"]) ?? "未知地产";
    const price = pickNumber(payload, ["price"]) ?? 0;
    return `债务拍卖成交，${tileId} 以 ${price} 转让。`;
  }
  if (event.type === "player.bankrupt") {
    const debt = pickNumber(payload, ["debt"]) ?? 0;
    return `资金链断裂，玩家破产，未清偿债务 ${debt}。`;
  }
  if (event.type === "game.finished") {
    const winner = pickString(payload, ["winner"]);
    return winner ? `对局结束，胜者：${formatPlayer(winner, playerNameMap)}。` : "对局结束。";
  }
  if (event.type === "turn.logged") {
    return "本手日志已写入复盘。";
  }
  if (event.type === "game.started") {
    return "对局初始化完成，进入首手。";
  }
  return "事件已记录。";
}

export function getEventSeverity(event: EventRecord): EventSeverity {
  const payload = asRecord(event.payload);
  const eventType = event.type.toLowerCase();
  const payloadType = String(payload.type ?? "").toLowerCase();

  if (eventType.includes("bankrupt")) {
    return "risk";
  }
  if (eventType.includes("jail") || payloadType.includes("jail")) {
    return "risk";
  }
  if (eventType.includes("tax") || payloadType.includes("tax")) {
    return "risk";
  }
  if (event.type === "settlement.applied" && payloadType === "toll_paid") {
    const amount = pickNumber(payload, ["amount"]) ?? 0;
    if (amount >= 300) {
      return "risk";
    }
  }
  if (event.type === "settlement.applied" && payloadType === "event_delta") {
    const delta = pickNumber(payload, ["delta"]) ?? 0;
    if (delta <= -150) {
      return "risk";
    }
  }
  return "normal";
}

export function buildPlayerNameMap(players: PlayerSnapshot[]): Record<string, string> {
  return players.reduce<Record<string, string>>((acc, player) => {
    acc[player.player_id] = player.name || player.player_id;
    return acc;
  }, {});
}

export const EVENT_TYPE_LABEL_TABLE = EVENT_TYPE_META;
