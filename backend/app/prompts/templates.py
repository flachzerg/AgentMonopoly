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
            f"# Template: {self.key}",
            f"version: {self.version}",
            f"objective: {self.objective}",
            f"risk_notice: {self.risk_notice}",
            "",
            "## Rules",
            self.body,
            "",
            "## Parameter Range",
            json.dumps(options_summary, ensure_ascii=False, sort_keys=True),
            "",
            "## Output Contract",
            json.dumps(turn_input.output_contract.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            "",
            "## Turn Input JSON",
            json.dumps(turn_input.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            "",
        ]
        return "\n".join(sections)


TEMPLATE_CATALOG: dict[str, list[TemplateVersion]] = {
    "PROPERTY_UNOWNED_TEMPLATE": [
        TemplateVersion(
            key="PROPERTY_UNOWNED_TEMPLATE",
            version="1.0.0",
            objective="Choose buy_property or skip_buy with expected value and cash safety in mind.",
            risk_notice="Never emit action outside options.allowed_values and never invent tile_id.",
            body="At unowned property tiles, prioritize long-term toll yield but keep liquidity for near-term risks.",
            change_note="Initial stable prompt for unowned property decision.",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="PROPERTY_UNOWNED_TEMPLATE",
            version="1.1.0",
            objective="Optimize buy decision using expected pass-by traffic and liquidity threshold.",
            risk_notice="If uncertainty is high, choose skip_buy instead of overspending.",
            body="Use conservative capital floor at 30% of net liquid assets when deciding buy_property.",
            change_note="Added explicit liquidity floor and uncertainty policy.",
            updated_on="2026-04-18",
        ),
    ],
    "PROPERTY_SELF_TEMPLATE": [
        TemplateVersion(
            key="PROPERTY_SELF_TEMPLATE",
            version="1.0.0",
            objective="At own property tiles, avoid unnecessary risk and keep strategic posture.",
            risk_notice="Do not emit economic actions that are not in options.",
            body="Most turns should choose pass unless alliance management action has immediate value.",
            change_note="Initial version.",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="PROPERTY_SELF_TEMPLATE",
            version="1.1.0",
            objective="At own property, optionally strengthen alliance if matchup advantage exists.",
            risk_notice="Never break output contract fields.",
            body="Prefer pass, but propose_alliance can be selected when it lowers near-term toll risk.",
            change_note="Alliance hint added.",
            updated_on="2026-04-18",
        ),
    ],
    "PROPERTY_ALLY_TEMPLATE": [
        TemplateVersion(
            key="PROPERTY_ALLY_TEMPLATE",
            version="1.0.0",
            objective="At ally property tiles, maintain cooperative value and avoid conflict actions.",
            risk_notice="Respect only available actions.",
            body="Default action is pass; alliance maintenance can be selected only when available.",
            change_note="Initial version.",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="PROPERTY_ALLY_TEMPLATE",
            version="1.1.0",
            objective="Maintain alliance advantage while preserving cash flexibility.",
            risk_notice="When options are ambiguous, choose pass.",
            body="Prefer pass unless alliance action directly boosts expected survival probability.",
            change_note="Improved ambiguity policy.",
            updated_on="2026-04-18",
        ),
    ],
    "PROPERTY_OTHER_TEMPLATE": [
        TemplateVersion(
            key="PROPERTY_OTHER_TEMPLATE",
            version="1.0.0",
            objective="At opponent property tiles after auto settlement, avoid compounding risk.",
            risk_notice="No speculative outputs; choose from options only.",
            body="Prioritize liquidity-preserving action and avoid overcommitment.",
            change_note="Initial version.",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="PROPERTY_OTHER_TEMPLATE",
            version="1.1.0",
            objective="Post-toll decision should prefer defensive actions under low cash.",
            risk_notice="Fallback-friendly behavior is required if confidence is low.",
            body="Choose pass in low confidence states; avoid risky alliance churn.",
            change_note="Defensive guidance strengthened.",
            updated_on="2026-04-18",
        ),
    ],
    "BANK_TEMPLATE": [
        TemplateVersion(
            key="BANK_TEMPLATE",
            version="1.0.0",
            objective="Choose bank_deposit, bank_withdraw, or pass to optimize liquidity and resilience.",
            risk_notice="amount must stay inside allowed_values.amount.",
            body="Deposit when idle cash is high; withdraw when short-term payments likely exceed cash.",
            change_note="Initial bank policy.",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="BANK_TEMPLATE",
            version="1.1.0",
            objective="Balance liquidity runway with growth opportunities using dynamic cash buffer.",
            risk_notice="Never invent amount; use provided numeric range only.",
            body="Target cash buffer equals expected toll exposure of next two turns.",
            change_note="Dynamic buffer rule added.",
            updated_on="2026-04-18",
        ),
    ],
    "EVENT_TEMPLATE": [
        TemplateVersion(
            key="EVENT_TEMPLATE",
            version="1.0.0",
            objective="After event settlement, adapt next action to volatility and current cash position.",
            risk_notice="Do not emit hidden fields.",
            body="Use conservative action when event volatility is high.",
            change_note="Initial event prompt.",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="EVENT_TEMPLATE",
            version="1.1.0",
            objective="Convert event outcome into immediate risk-aware action.",
            risk_notice="If action confidence is below 0.5, prefer pass.",
            body="Capture event upside when safe, otherwise lock defensive stance.",
            change_note="Confidence policy added.",
            updated_on="2026-04-18",
        ),
    ],
    "EMPTY_TEMPLATE": [
        TemplateVersion(
            key="EMPTY_TEMPLATE",
            version="1.0.0",
            objective="At empty tile, select low-risk utility action.",
            risk_notice="No action beyond options list.",
            body="Default to pass, only propose alliance if clear strategic edge.",
            change_note="Initial empty-tile baseline.",
            updated_on="2026-04-18",
        ),
        TemplateVersion(
            key="EMPTY_TEMPLATE",
            version="1.1.0",
            objective="Use empty turns for alliance timing and risk shaping.",
            risk_notice="Keep outputs minimal and contract-compliant.",
            body="Prefer pass unless alliance can reduce near-term toll burden.",
            change_note="Alliance timing hint added.",
            updated_on="2026-04-18",
        ),
    ],
    "QUIZ_TEMPLATE": [
        TemplateVersion(
            key="QUIZ_TEMPLATE",
            version="0.1.0",
            objective="Reserved slot for quiz chain integration.",
            risk_notice="MVP route keeps quiz as placeholder and should return pass-safe outputs.",
            body="Quiz runtime is not fully enabled yet; preserve contract and choose safe action.",
            change_note="Placeholder template for future quiz flow.",
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
        "# Prompt Template Changelog",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        "| Template | Version | Date | Change |",
        "|---|---|---|---|",
    ]
    for row in get_template_changelog():
        lines.append(
            f"| {row['template_key']} | {row['version']} | {row['updated_on']} | {row['change_note']} |"
        )
    lines.append("")
    return "\n".join(lines)
