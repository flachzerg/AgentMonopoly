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
            f"# 模板: {self.key}",
            f"版本: {self.version}",
            f"用途: {self.objective}",
            f"硬约束: {self.risk_notice}",
            "",
            "## 场景现状",
            self.body,
            "",
            "## 动作参数范围",
            json.dumps(options_summary, ensure_ascii=False, sort_keys=True),
            "",
            "## 输出合同",
            json.dumps(turn_input.output_contract.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            "",
            "## 回合输入 JSON",
            json.dumps(turn_input.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            "",
        ]
        return "\n".join(sections)


TEMPLATE_CATALOG: dict[str, list[TemplateVersion]] = {
    "PROPERTY_UNOWNED_TEMPLATE": [
        TemplateVersion(
            key="PROPERTY_UNOWNED_TEMPLATE",
            version="1.0.0",
            objective="描述无人地产格事实信息。",
            risk_notice="动作仅可来自 options，参数必须命中 allowed_values。",
            body=(
                "当前格子类型为 PROPERTY_UNOWNED。输入 JSON 内含地块价格、过路费、玩家现金、玩家总资产、"
                "棋盘快照与其余玩家信息。可选动作通常含 buy_property、skip_buy、pass。"
            ),
            change_note="无人地产模板初版。",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="PROPERTY_UNOWNED_TEMPLATE",
            version="1.1.0",
            objective="描述无人地产格事实信息（字段排序优化版）。",
            risk_notice="必须返回合同字段，且不得输出额外字段。",
            body=(
                "该回合处于 DECISION 阶段，落点为无人地产。输入 JSON 提供地块 id、地块价值、玩家资金、"
                "联盟状态与候选动作列表。模型仅需在候选动作里给出一个动作。"
            ),
            change_note="改为纯现状描述，不含策略指引。",
            updated_on="2026-04-18",
        ),
    ],
    "PROPERTY_SELF_TEMPLATE": [
        TemplateVersion(
            key="PROPERTY_SELF_TEMPLATE",
            version="1.0.0",
            objective="描述己方地产格事实信息。",
            risk_notice="仅可使用当前轮可选动作与允许参数。",
            body=(
                "当前落点为己方地产。输入 JSON 包含本方地产列表、当前资金、全局玩家快照、"
                "以及本轮动作候选项。"
            ),
            change_note="己方地产模板初版。",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="PROPERTY_SELF_TEMPLATE",
            version="1.1.0",
            objective="描述己方地产格事实信息（结构优化版）。",
            risk_notice="输出必须符合 DY-MONO-TURN-OUT/3.1。",
            body=(
                "当前格子由当前玩家持有。输入 JSON 内含玩家状态、棋盘状态、联盟状态与动作候选。"
                "模型只需输出一个合法动作与参数。"
            ),
            change_note="改为纯现状描述，不含策略指引。",
            updated_on="2026-04-18",
        ),
    ],
    "PROPERTY_ALLY_TEMPLATE": [
        TemplateVersion(
            key="PROPERTY_ALLY_TEMPLATE",
            version="1.0.0",
            objective="描述盟友地产格事实信息。",
            risk_notice="动作与参数必须满足 options 约束。",
            body=(
                "当前落点为盟友地产。输入 JSON 给出联盟关系、玩家资产与动作候选项。"
                "该场景不会出现合同外动作。"
            ),
            change_note="盟友地产模板初版。",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="PROPERTY_ALLY_TEMPLATE",
            version="1.1.0",
            objective="描述盟友地产格事实信息（字段精简版）。",
            risk_notice="必须返回 action 与 args，且字段名不可变。",
            body=(
                "当前为盟友地产场景。输入 JSON 含玩家关系、经济状态、动作候选列表。"
                "模型输出仅用于系统执行层。"
            ),
            change_note="改为纯现状描述，不含策略指引。",
            updated_on="2026-04-18",
        ),
    ],
    "PROPERTY_OTHER_TEMPLATE": [
        TemplateVersion(
            key="PROPERTY_OTHER_TEMPLATE",
            version="1.0.0",
            objective="描述他方地产格事实信息。",
            risk_notice="禁止输出 options 外动作或非法参数。",
            body=(
                "当前落点为他方地产，AUTO_SETTLE 已执行。输入 JSON 含结算后资金状态、"
                "玩家快照与动作候选项。"
            ),
            change_note="他方地产模板初版。",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="PROPERTY_OTHER_TEMPLATE",
            version="1.1.0",
            objective="描述他方地产格事实信息（结构优化版）。",
            risk_notice="返回 JSON 必须可被严格 schema 校验通过。",
            body=(
                "该回合场景为 PROPERTY_OTHER。输入 JSON 已给出全部业务事实与动作边界，"
                "模型无需扩展业务规则。"
            ),
            change_note="改为纯现状描述，不含策略指引。",
            updated_on="2026-04-18",
        ),
    ],
    "BANK_TEMPLATE": [
        TemplateVersion(
            key="BANK_TEMPLATE",
            version="1.0.0",
            objective="描述银行格事实信息。",
            risk_notice="若动作含 amount，值必须命中 allowed_values.amount。",
            body=(
                "当前落点为 BANK。输入 JSON 包含现金、存款、动作候选项与参数范围。"
                "可选动作可能含 bank_deposit、bank_withdraw、pass。"
            ),
            change_note="银行模板初版。",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="BANK_TEMPLATE",
            version="1.1.0",
            objective="描述银行格事实信息（字段排序优化版）。",
            risk_notice="只能在合同字段内输出，不得附加解释字段。",
            body=(
                "BANK 场景下，输入 JSON 已给定资金状态、参数上下界与动作候选。"
                "模型仅输出一个合法动作。"
            ),
            change_note="改为纯现状描述，不含策略指引。",
            updated_on="2026-04-18",
        ),
    ],
    "EVENT_TEMPLATE": [
        TemplateVersion(
            key="EVENT_TEMPLATE",
            version="1.0.0",
            objective="描述事件格事实信息。",
            risk_notice="输出字段必须完全匹配 output_contract。",
            body=(
                "当前落点为 EVENT，事件结算已进入状态。输入 JSON 含事件后资金变化、"
                "玩家快照与本轮候选动作。"
            ),
            change_note="事件模板初版。",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="EVENT_TEMPLATE",
            version="1.1.0",
            objective="描述事件格事实信息（结构优化版）。",
            risk_notice="禁止输出合同外字段与非法动作。",
            body=(
                "该回合为 EVENT 场景。输入 JSON 已给出全部状态事实，"
                "模型仅需返回合法动作 JSON。"
            ),
            change_note="改为纯现状描述，不含策略指引。",
            updated_on="2026-04-18",
        ),
    ],
    "EMPTY_TEMPLATE": [
        TemplateVersion(
            key="EMPTY_TEMPLATE",
            version="1.0.0",
            objective="描述空格场景事实信息。",
            risk_notice="动作必须来自 options，参数必须合法。",
            body=(
                "当前落点为 EMPTY。输入 JSON 含玩家状态、全局快照、候选动作与参数边界。"
            ),
            change_note="空格模板初版。",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="EMPTY_TEMPLATE",
            version="1.1.0",
            objective="描述空格场景事实信息（精简版）。",
            risk_notice="仅返回合同字段，不返回附加说明字段。",
            body=(
                "该场景无强制结算逻辑。输入 JSON 提供本轮全部事实信息与动作候选。"
                "模型只输出单一合法动作。"
            ),
            change_note="改为纯现状描述，不含策略指引。",
            updated_on="2026-04-18",
        ),
    ],
    "QUIZ_TEMPLATE": [
        TemplateVersion(
            key="QUIZ_TEMPLATE",
            version="0.1.0",
            objective="描述 QUIZ 占位场景事实信息。",
            risk_notice="MVP 阶段 QUIZ 仍为占位链路，输出必须合同合法。",
            body=(
                "当前场景标记为 QUIZ，占位逻辑已保留。输入 JSON 含候选动作与参数范围。"
            ),
            change_note="新增 QUIZ 占位模板。",
            updated_on="2026-04-18",
        )
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
