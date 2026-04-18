from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.agent_eval import BatchConfig, EvaluationProfile, run_profile_eval
from app.prompts.templates import list_template_keys, list_template_versions


def default_baseline_overrides() -> dict[str, str]:
    rows: dict[str, str] = {}
    for key in list_template_keys():
        versions = list_template_versions(key)
        if versions:
            rows[key] = versions[0]
    return rows


def build_default_profiles() -> list[EvaluationProfile]:
    return [
        EvaluationProfile(name="baseline", template_overrides={}),
        EvaluationProfile(name="property_v1_1", template_overrides={"PROPERTY_UNOWNED_TEMPLATE": "1.1.0"}),
        EvaluationProfile(name="bank_v1_1", template_overrides={"BANK_TEMPLATE": "1.1.0"}),
        EvaluationProfile(name="event_v1_1", template_overrides={"EVENT_TEMPLATE": "1.1.0"}),
    ]


def report_markdown(rows: list[dict[str, float | str]]) -> str:
    lines = [
        "# Batch Evaluation Report",
        "",
        "| profile | games | win_rate | avg_total_assets | bankrupt_rate | illegal_action_rate | fallback_rate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {profile} | {games} | {win_rate:.4f} | {avg_total_assets:.2f} | {bankrupt_rate:.4f} | {illegal_action_rate:.4f} | {fallback_rate:.4f} |".format(
                **row
            )
        )
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run batch AI matches and output metrics")
    parser.add_argument("--games", type=int, default=40)
    parser.add_argument("--max-rounds", type=int, default=24)
    parser.add_argument("--seed", type=int, default=20260418)
    parser.add_argument("--out-json", default="backend/reports/batch_eval.json")
    parser.add_argument("--out-md", default="backend/reports/batch_eval.md")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = BatchConfig(games=args.games, max_rounds=args.max_rounds, seed=args.seed)
    baseline = default_baseline_overrides()
    profiles = build_default_profiles()

    rows: list[dict[str, float | str]] = []
    for profile in profiles:
        result = run_profile_eval(profile, baseline_overrides=baseline, config=cfg)
        rows.append(result.model_dump(mode="json"))

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(report_markdown(rows), encoding="utf-8")


if __name__ == "__main__":
    main()
