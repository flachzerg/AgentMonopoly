from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.schemas import EventRecord, GameState, ReplayExport, ReplayResponse


@dataclass(frozen=True)
class ReplayPromptTemplate:
    key: str = "GLOBAL_REPLAY_CN_TEMPLATE"
    version: str = "1.0.0"
    style: str = "通俗中文，少术语，结论必须有证据回合。"

    def render(self, materials: dict[str, Any]) -> str:
        return "\n".join(
            [
                "# 全局复盘任务",
                "",
                f"- template_key: {self.key}",
                f"- template_version: {self.version}",
                f"- style: {self.style}",
                "",
                "## 输入材料",
                str(materials),
            ]
        )


def _turns_from_events(events: list[EventRecord], limit: int = 12) -> list[int]:
    values = sorted({item.turn_index for item in events if item.turn_index > 0})
    if len(values) <= limit:
        return values
    step = max(len(values) // limit, 1)
    return values[::step][:limit]


def _phase_ranges(total_turns: int) -> dict[str, tuple[int, int]]:
    if total_turns <= 0:
        return {"前期": (0, 0), "中期": (0, 0), "后期": (0, 0)}
    one = max(total_turns // 3, 1)
    two = max((total_turns * 2) // 3, one + 1 if total_turns > 1 else 1)
    return {
        "前期": (1, one),
        "中期": (one + 1, two),
        "后期": (two + 1, total_turns),
    }


def _phase_turns(events: list[EventRecord], start: int, end: int) -> list[int]:
    if start <= 0 or end <= 0 or start > end:
        return []
    values = sorted({item.turn_index for item in events if start <= item.turn_index <= end})
    return values[:6]


def _key_turning_points(events: list[EventRecord]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in events:
        if item.type in {"player.bankrupt", "alliance.created", "auction.sold"}:
            candidates.append(
                {
                    "turn": item.turn_index,
                    "title": item.type,
                    "impact": _event_human_text(item),
                    "evidence_turns": [item.turn_index],
                }
            )
        elif item.type == "action.accepted" and item.payload.get("action") in {"buy_property", "upgrade_property"}:
            candidates.append(
                {
                    "turn": item.turn_index,
                    "title": str(item.payload.get("action")),
                    "impact": _event_human_text(item),
                    "evidence_turns": [item.turn_index],
                }
            )
    candidates.sort(key=lambda row: row["turn"])
    return candidates[:6]


def _event_human_text(event: EventRecord) -> str:
    payload = event.payload
    if event.type == "player.bankrupt":
        return f"{payload.get('player_id')} 在第 {event.turn_index} 手破产，比赛格局直接改变。"
    if event.type == "alliance.created":
        return f"{payload.get('player_id')} 与 {payload.get('target_player_id')} 建立联盟，过路费压力下降。"
    if event.type == "auction.sold":
        return (
            f"{payload.get('from_player_id')} 的 {payload.get('tile_id')} 被 {payload.get('to_player_id')} 拍走，"
            "资产控制权发生转移。"
        )
    if event.type == "action.accepted":
        action = payload.get("action")
        if action == "buy_property":
            return f"{payload.get('player_id')} 买下 {payload.get('tile_id')}，开始建立地产优势。"
        if action == "upgrade_property":
            return f"{payload.get('player_id')} 升级 {payload.get('tile_id')}，后续过路费威胁上升。"
    return f"{event.type} 发生在第 {event.turn_index} 手。"


def _player_profiles(state: GameState) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ranking = sorted(state.players, key=lambda item: item.net_worth, reverse=True)
    top_id = ranking[0].player_id if ranking else ""
    for item in state.players:
        style = "稳健运营"
        if len(item.property_ids) >= 3:
            style = "地产扩张型"
        if item.cash < 350:
            style = "高风险博弈型"
        highlights = [
            f"净资产 {item.net_worth}",
            f"持有地产 {len(item.property_ids)} 处",
            f"现金 {item.cash}，存款 {item.deposit}",
        ]
        issues = []
        if not item.alive:
            issues.append("资金链断裂导致出局")
        if item.cash < 200:
            issues.append("现金过低，抗波动能力弱")
        if item.alliance_with is None:
            issues.append("没有联盟缓冲，防守压力较大")
        if not issues:
            issues.append("整体节奏稳定，无明显短板")
        rows.append(
            {
                "player_id": item.player_id,
                "style": style,
                "highlights": highlights,
                "issues": issues[:3],
                "is_winner": item.player_id == top_id,
            }
        )
    return rows


def _phase_analysis(events: list[EventRecord], replay: ReplayResponse) -> list[dict[str, Any]]:
    ranges = _phase_ranges(replay.total_turns)
    rows: list[dict[str, Any]] = []
    for phase, (start, end) in ranges.items():
        turns = _phase_turns(events, start, end)
        if not turns:
            summary = f"{phase}信息较少，主要是基础移动与常规结算。"
        else:
            summary = f"{phase}主要变化集中在第 {turns[0]} 到第 {turns[-1]} 手。"
        rows.append(
            {
                "phase": phase,
                "summary": summary,
                "evidence_turns": turns,
            }
        )
    return rows


def _next_game_advice(state: GameState) -> list[str]:
    winner = max(state.players, key=lambda item: item.net_worth)
    advice = [
        "前 6 手优先保证现金安全垫，不要连续高价买地。",
        "遇到高过路费区域前，提前把现金和存款结构调顺。",
        "联盟请求只在现金低于 400 时发起，避免过早绑定。",
        f"重点研究 {winner.player_id} 的扩张节奏，把买地窗口前移 1~2 手。",
    ]
    return advice


def build_replay_export(
    game_id: str,
    state: GameState,
    replay: ReplayResponse,
    events: list[EventRecord],
    strategy_timeline: list[dict[str, Any]],
) -> ReplayExport:
    template = ReplayPromptTemplate()
    winner = max(state.players, key=lambda item: item.net_worth) if state.players else None
    key_turns = _turns_from_events(events)
    phase_analysis = _phase_analysis(events, replay)
    turning_points = _key_turning_points(events)
    player_profiles = _player_profiles(state)
    next_game_advice = _next_game_advice(state)
    overview = (
        f"{winner.player_id if winner else '未知玩家'} 赢下本局，关键原因是资产增长更稳定，"
        "并且在关键手没有出现致命现金断档。"
    )

    recap = {
        "overview": overview,
        "phase_analysis": phase_analysis,
        "turning_points": turning_points,
        "player_profiles": player_profiles,
        "next_game_advice": next_game_advice,
    }
    materials = {
        "event_timeline": [
            {
                "type": item.type,
                "turn_index": item.turn_index,
                "round_index": item.round_index,
                "payload": item.payload,
            }
            for item in events[-120:]
        ],
        "strategy_timeline": strategy_timeline[-80:],
        "key_turns": key_turns,
        "result": {
            "status": state.status,
            "winner": winner.player_id if winner else None,
            "players": [
                {
                    "player_id": item.player_id,
                    "net_worth": item.net_worth,
                    "alive": item.alive,
                    "cash": item.cash,
                    "deposit": item.deposit,
                }
                for item in state.players
            ],
        },
    }

    metrics = {
        "total_turns": float(replay.total_turns),
        "key_turn_count": float(len(key_turns)),
        "turning_point_count": float(len(turning_points)),
        "winner_net_worth": float(winner.net_worth if winner else 0),
        "avg_net_worth": float(sum(item.net_worth for item in state.players) / max(len(state.players), 1)),
    }

    markdown = "\n".join(
        [
            f"# 对局复盘 {game_id}",
            "",
            "## 全局结论",
            recap["overview"],
            "",
            "## 分阶段分析",
            *[
                f"- {item['phase']}：{item['summary']}（证据回合：{item['evidence_turns']}）"
                for item in recap["phase_analysis"]
            ],
            "",
            "## 关键转折点",
            *[
                f"- 第 {item['turn']} 手 {item['title']}：{item['impact']}"
                for item in recap["turning_points"]
            ],
            "",
            "## 各玩家表现",
            *[
                f"- {item['player_id']}（{item['style']}）：亮点={item['highlights']}；问题={item['issues']}"
                for item in recap["player_profiles"]
            ],
            "",
            "## 下一局建议",
            *[f"- {item}" for item in recap["next_game_advice"]],
        ]
    )

    return ReplayExport(
        game_id=game_id,
        generated_at=datetime.now(timezone.utc),
        metrics=metrics,
        strategy_timeline=strategy_timeline,
        recap=recap,
        prompt_materials={
            "template_key": template.key,
            "template_version": template.version,
            "template_style": template.style,
            "prompt_preview": template.render(materials),
            "materials": materials,
        },
        markdown=markdown,
    )
