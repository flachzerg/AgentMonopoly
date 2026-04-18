from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from app.schemas import TurnInput


@dataclass(frozen=True)
class TemplateVersion:
    key: str
    version: str
    objective: str
    risk_notice: str
    body: str
    change_note: str
    updated_on: str

    def render(self, turn_input: TurnInput) -> str:
        options_summary = {
            item.action: {
                "required_args": item.required_args,
                "allowed_values": item.allowed_values,
                "default_args": item.default_args,
            }
            for item in turn_input.options
        }
        sections = [
            "# Agent Context Packet v2",
            "",
            "## 1) System Prompt (Fixed)",
            "你在大富翁对局中做单步决策，必须仅返回 JSON 且动作必须来自合法动作列表。",
            "",
            "## 2) Static Map (Fixed)",
            json.dumps(turn_input.static_map.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            "",
            "## 3) Dynamic State (Per Turn)",
            json.dumps(turn_input.dynamic_state.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            "",
            "## 4) Recent Actions Review (Last 3 Turns)",
            json.dumps([item.model_dump(mode="json") for item in turn_input.recent_actions_3turns], ensure_ascii=False, sort_keys=True),
            "",
            "## 5) Memory",
            json.dumps(turn_input.memory_context.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            "",
            "## 6) Fixed Runtime Context",
            json.dumps(
                {
                    "protocol": turn_input.protocol,
                    "turn_meta": turn_input.turn_meta.model_dump(mode="json"),
                    "tile_context": turn_input.tile_context.model_dump(mode="json"),
                    "player_state": turn_input.player_state.model_dump(mode="json"),
                    "players_snapshot": [item.model_dump(mode="json") for item in turn_input.players_snapshot],
                    "board_snapshot": turn_input.board_snapshot.model_dump(mode="json"),
                    "history_records": turn_input.history_records,
                    "memory_summary": turn_input.memory_summary,
                    "model_experience_summary": turn_input.model_experience_summary,
                    "strategy_profile": (
                        turn_input.strategy_profile.model_dump(mode="json") if turn_input.strategy_profile else None
                    ),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "",
            "## 7) Legal Actions",
            json.dumps(options_summary, ensure_ascii=False, sort_keys=True),
            "",
            "## 8) Output Contract",
            json.dumps(turn_input.output_contract.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            "",
            "## Turn Input JSON",
            json.dumps(turn_input.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            "",
        ]
        return "\n".join(sections)


COMMON_OBJECTIVE = "模板仅描述事实输入，不提供策略引导。"
COMMON_RISK_NOTICE = "动作必须来自 options，参数必须匹配 allowed_values，输出仅允许合同字段。"
COMMON_BODY = "全局状态、当前玩家状态、历史执行记录的结构在所有格子模板中保持一致。"


def _two_versions(key: str, updated_on: str) -> list[TemplateVersion]:
    return [
        TemplateVersion(
            key=key,
            version="1.0.0",
            objective=COMMON_OBJECTIVE,
            risk_notice=COMMON_RISK_NOTICE,
            body=COMMON_BODY,
            change_note="状态输入模板初版。",
            updated_on=updated_on,
        ),
        TemplateVersion(
            key=key,
            version="1.1.0",
            objective=COMMON_OBJECTIVE,
            risk_notice=COMMON_RISK_NOTICE,
            body=COMMON_BODY,
            change_note="统一为状态模板，格子差异仅体现在动作与参数。",
            updated_on=updated_on,
        ),
    ]


TEMPLATE_CATALOG: dict[str, list[TemplateVersion]] = {
    "PROPERTY_UNOWNED_TEMPLATE": _two_versions("PROPERTY_UNOWNED_TEMPLATE", "2026-04-18"),
    "PROPERTY_SELF_TEMPLATE": _two_versions("PROPERTY_SELF_TEMPLATE", "2026-04-18"),
    "PROPERTY_ALLY_TEMPLATE": _two_versions("PROPERTY_ALLY_TEMPLATE", "2026-04-18"),
    "PROPERTY_OTHER_TEMPLATE": _two_versions("PROPERTY_OTHER_TEMPLATE", "2026-04-18"),
    "BANK_TEMPLATE": _two_versions("BANK_TEMPLATE", "2026-04-18"),
    "EVENT_TEMPLATE": _two_versions("EVENT_TEMPLATE", "2026-04-18"),
    "EMPTY_TEMPLATE": _two_versions("EMPTY_TEMPLATE", "2026-04-18"),
    "QUIZ_TEMPLATE": [
        TemplateVersion(
            key="QUIZ_TEMPLATE",
            version="0.1.0",
            objective=COMMON_OBJECTIVE,
            risk_notice=COMMON_RISK_NOTICE,
            body=COMMON_BODY,
            change_note="QUIZ 占位模板。",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="QUIZ_TEMPLATE",
            version="0.2.0",
            objective=COMMON_OBJECTIVE,
            risk_notice=COMMON_RISK_NOTICE,
            body=COMMON_BODY,
            change_note="统一为状态模板，格子差异仅体现在动作与参数。",
            updated_on="2026-04-18",
        ),
    ],
}


def list_template_keys() -> list[str]:
    return sorted(TEMPLATE_CATALOG.keys())


def list_template_versions(template_key: str) -> list[str]:
    return [item.version for item in TEMPLATE_CATALOG.get(template_key, [])]


def get_template(template_key: str, version: str | None = None) -> TemplateVersion:
    versions = TEMPLATE_CATALOG.get(template_key)
    if not versions:
        raise KeyError(f"unknown template_key: {template_key}")
    if version is None:
        return versions[-1]
    for item in versions:
        if item.version == version:
            return item
    raise KeyError(f"unknown template version: {template_key}:{version}")


def get_template_changelog() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key, versions in TEMPLATE_CATALOG.items():
        for item in versions:
            rows.append(
                {
                    "template_key": key,
                    "version": item.version,
                    "change_note": item.change_note,
                    "updated_on": item.updated_on,
                }
            )
    rows.sort(key=lambda r: (r["template_key"], r["version"]))
    return rows


def changelog_markdown() -> str:
    lines = [
        "# 提示词模板变更记录",
        "",
        f"生成日期: {date.today().isoformat()}",
        "",
        "| 模板 | 版本 | 日期 | 变更 |",
        "|---|---|---|---|",
    ]
    for row in get_template_changelog():
        lines.append(
            f"| {row['template_key']} | {row['version']} | {row['updated_on']} | {row['change_note']} |"
        )
    lines.append("")
    return "\n".join(lines)
