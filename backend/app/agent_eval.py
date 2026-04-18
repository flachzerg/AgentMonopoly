from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from app.agent_runtime import AgentRuntime, HeuristicDecisionModel, TurnBuildInput
from app.game_engine import GameManager
from app.prompts import PromptABRouter
from app.schemas import BoardSnapshot, EvaluationResult, PlayerConfig, TemplateABReport


@dataclass(frozen=True)
class EvaluationProfile:
    name: str
    template_overrides: dict[str, str]


@dataclass(frozen=True)
class BatchConfig:
    games: int = 30
    max_rounds: int = 20
    seed: int = 20260418


def run_profile_eval(
    profile: EvaluationProfile,
    baseline_overrides: dict[str, str] | None = None,
    config: BatchConfig | None = None,
) -> EvaluationResult:
    cfg = config or BatchConfig()
    baseline_overrides = baseline_overrides or {}

    target_runtime = AgentRuntime(
        model=HeuristicDecisionModel(model_tag=f"heuristic:{profile.name}"),
        router=PromptABRouter(overrides=profile.template_overrides),
    )
    baseline_runtime = AgentRuntime(
        model=HeuristicDecisionModel(model_tag="heuristic:baseline"),
        router=PromptABRouter(overrides=baseline_overrides),
    )

    wins = 0
    total_assets = 0
    bankrupt = 0
    illegal_actions = 0
    fallback_count = 0
    decision_count = 0

    for index in range(cfg.games):
        manager = GameManager()
        game_id = f"eval-{profile.name}-{index}"
        manager.create_game(
            game_id=game_id,
            max_rounds=cfg.max_rounds,
            seed=cfg.seed + index,
            players=[
                PlayerConfig(player_id="p1", name="target", is_agent=True),
                PlayerConfig(player_id="p2", name="base-2", is_agent=True),
                PlayerConfig(player_id="p3", name="base-3", is_agent=True),
                PlayerConfig(player_id="p4", name="base-4", is_agent=True),
            ],
        )

        max_steps = cfg.max_rounds * 4 * 3
        for _ in range(max_steps):
            state = manager.state(game_id)
            if state.status == "finished":
                break

            current_player_id = state.current_player_id
            manager.advance_to_decision_if_needed(game_id, current_player_id)
            state = manager.state(game_id)
            if state.status == "finished":
                break
            if state.current_phase != "DECISION":
                continue

            session = manager.get_game(game_id)
            snapshots = manager.build_players_snapshot(session)
            current_snapshot = next(item for item in snapshots if item.player_id == state.current_player_id)
            turn_input = (
                target_runtime if state.current_player_id == "p1" else baseline_runtime
            ).build_turn_input(
                TurnBuildInput(
                    turn_meta=manager.build_turn_meta(session),
                    tile_context=manager.build_tile_context(session),
                    player_state=current_snapshot,
                    players_snapshot=snapshots,
                    board_snapshot=BoardSnapshot(
                        track_length=len(session.board),
                        tiles=manager.build_board_snapshot(session),
                    ),
                    options=state.allowed_actions,
                )
            )

            runtime = target_runtime if state.current_player_id == "p1" else baseline_runtime
            envelope = runtime.decide(turn_input)
            accepted, _, event = manager.apply_action(
                game_id=game_id,
                player_id=state.current_player_id,
                action=envelope.decision.action,
                args=envelope.decision.args,
                decision_audit=envelope if state.current_player_id == "p1" else None,
            )

            if state.current_player_id == "p1":
                decision_count += 1
                if envelope.audit.status == "fallback":
                    fallback_count += 1
                if (not accepted) or (event and event.type == "action.rejected"):
                    illegal_actions += 1

        final_state = manager.state(game_id)
        target = next(item for item in final_state.players if item.player_id == "p1")
        total_assets += target.net_worth
        if not target.alive:
            bankrupt += 1

        winner = max(final_state.players, key=lambda item: item.net_worth)
        if winner.player_id == "p1":
            wins += 1

    denominator = max(cfg.games, 1)
    decision_denominator = max(decision_count, 1)
    return EvaluationResult(
        profile=profile.name,
        games=cfg.games,
        win_rate=wins / denominator,
        avg_total_assets=total_assets / denominator,
        bankrupt_rate=bankrupt / denominator,
        illegal_action_rate=illegal_actions / decision_denominator,
        fallback_rate=fallback_count / decision_denominator,
    )


def compare_template_versions(
    template_key: str,
    baseline_version: str,
    challenger_version: str,
    games: int,
    max_rounds: int,
    seed: int,
) -> TemplateABReport:
    cfg = BatchConfig(games=games, max_rounds=max_rounds, seed=seed)
    baseline_profile = EvaluationProfile(
        name=f"{template_key}:{baseline_version}",
        template_overrides={template_key: baseline_version},
    )
    challenger_profile = EvaluationProfile(
        name=f"{template_key}:{challenger_version}",
        template_overrides={template_key: challenger_version},
    )

    baseline = run_profile_eval(
        baseline_profile,
        baseline_overrides={template_key: baseline_version},
        config=cfg,
    )
    challenger = run_profile_eval(
        challenger_profile,
        baseline_overrides={template_key: baseline_version},
        config=cfg,
    )

    delta = {
        "win_rate": challenger.win_rate - baseline.win_rate,
        "avg_total_assets": challenger.avg_total_assets - baseline.avg_total_assets,
        "bankrupt_rate": challenger.bankrupt_rate - baseline.bankrupt_rate,
        "illegal_action_rate": challenger.illegal_action_rate - baseline.illegal_action_rate,
        "fallback_rate": challenger.fallback_rate - baseline.fallback_rate,
    }
    return TemplateABReport(
        template_key=template_key,
        baseline_version=baseline_version,
        challenger_version=challenger_version,
        baseline=baseline,
        challenger=challenger,
        delta=delta,
    )


def report_markdown(report: TemplateABReport) -> str:
    return "\n".join(
        [
            f"# Template A/B Report: {report.template_key}",
            "",
            f"- baseline: {report.baseline_version}",
            f"- challenger: {report.challenger_version}",
            "",
            "| Metric | Baseline | Challenger | Delta |",
            "|---|---:|---:|---:|",
            f"| win_rate | {report.baseline.win_rate:.4f} | {report.challenger.win_rate:.4f} | {report.delta['win_rate']:+.4f} |",
            f"| avg_total_assets | {report.baseline.avg_total_assets:.2f} | {report.challenger.avg_total_assets:.2f} | {report.delta['avg_total_assets']:+.2f} |",
            f"| bankrupt_rate | {report.baseline.bankrupt_rate:.4f} | {report.challenger.bankrupt_rate:.4f} | {report.delta['bankrupt_rate']:+.4f} |",
            f"| illegal_action_rate | {report.baseline.illegal_action_rate:.4f} | {report.challenger.illegal_action_rate:.4f} | {report.delta['illegal_action_rate']:+.4f} |",
            f"| fallback_rate | {report.baseline.fallback_rate:.4f} | {report.challenger.fallback_rate:.4f} | {report.delta['fallback_rate']:+.4f} |",
        ]
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Template version evaluator")
    parser.add_argument("--template", required=True, help="template key")
    parser.add_argument("--baseline", required=True, help="baseline version")
    parser.add_argument("--challenger", required=True, help="challenger version")
    parser.add_argument("--games", type=int, default=30)
    parser.add_argument("--max-rounds", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260418)
    parser.add_argument("--out-json", default="backend/reports/template_ab_report.json")
    parser.add_argument("--out-md", default="backend/reports/template_ab_report.md")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = compare_template_versions(
        template_key=args.template,
        baseline_version=args.baseline,
        challenger_version=args.challenger,
        games=args.games,
        max_rounds=args.max_rounds,
        seed=args.seed,
    )

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    out_md.write_text(report_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
