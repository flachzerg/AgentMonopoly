from __future__ import annotations

import unittest

from app.agent_eval import BatchConfig, EvaluationProfile, compare_template_versions, run_profile_eval


class EvalMetricsTests(unittest.TestCase):
    def test_run_profile_eval_metrics_shape(self) -> None:
        result = run_profile_eval(
            profile=EvaluationProfile(name="baseline", template_overrides={}),
            config=BatchConfig(games=4, max_rounds=6, seed=13),
        )
        self.assertEqual(result.games, 4)
        self.assertGreaterEqual(result.win_rate, 0.0)
        self.assertLessEqual(result.win_rate, 1.0)
        self.assertGreaterEqual(result.bankrupt_rate, 0.0)
        self.assertLessEqual(result.bankrupt_rate, 1.0)
        self.assertGreaterEqual(result.illegal_action_rate, 0.0)
        self.assertLessEqual(result.illegal_action_rate, 1.0)
        self.assertGreaterEqual(result.fallback_rate, 0.0)
        self.assertLessEqual(result.fallback_rate, 1.0)

    def test_compare_template_versions_has_delta(self) -> None:
        report = compare_template_versions(
            template_key="BANK_TEMPLATE",
            baseline_version="1.0.0",
            challenger_version="1.1.0",
            games=4,
            max_rounds=6,
            seed=42,
        )
        self.assertIn("win_rate", report.delta)
        self.assertIn("avg_total_assets", report.delta)
        self.assertIn("bankrupt_rate", report.delta)
        self.assertIn("illegal_action_rate", report.delta)
        self.assertIn("fallback_rate", report.delta)


if __name__ == "__main__":
    unittest.main()
