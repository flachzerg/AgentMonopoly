from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.agent_eval import compare_template_versions
from app.prompts.templates import list_template_keys, list_template_versions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build template A/B comparison report")
    parser.add_argument("--games", type=int, default=30)
    parser.add_argument("--max-rounds", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260418)
    parser.add_argument(
        "--templates",
        nargs="*",
        default=["PROPERTY_UNOWNED_TEMPLATE", "BANK_TEMPLATE", "EVENT_TEMPLATE", "EMPTY_TEMPLATE"],
    )
    parser.add_argument("--out-json", default="backend/reports/template_versions_report.json")
    parser.add_argument("--out-md", default="backend/reports/template_versions_report.md")
    return parser.parse_args()


def report_markdown(rows: list[dict]) -> str:
    lines = [
        "# Template Version Comparison",
        "",
        "| template_key | baseline | challenger | delta_win_rate | delta_avg_assets | delta_bankrupt_rate | delta_illegal_rate | delta_fallback_rate |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        delta = row["delta"]
        lines.append(
            "| {template_key} | {baseline_version} | {challenger_version} | {dw:+.4f} | {da:+.2f} | {db:+.4f} | {di:+.4f} | {df:+.4f} |".format(
                template_key=row["template_key"],
                baseline_version=row["baseline_version"],
                challenger_version=row["challenger_version"],
                dw=delta["win_rate"],
                da=delta["avg_total_assets"],
                db=delta["bankrupt_rate"],
                di=delta["illegal_action_rate"],
                df=delta["fallback_rate"],
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    rows: list[dict] = []
    for key in args.templates:
        versions = list_template_versions(key)
        if len(versions) < 2:
            continue
        report = compare_template_versions(
            template_key=key,
            baseline_version=versions[0],
            challenger_version=versions[-1],
            games=args.games,
            max_rounds=args.max_rounds,
            seed=args.seed,
        )
        rows.append(report.model_dump(mode="json"))

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(report_markdown(rows), encoding="utf-8")


if __name__ == "__main__":
    main()
