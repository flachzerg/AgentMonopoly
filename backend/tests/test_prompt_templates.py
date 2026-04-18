from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.agent_eval import compare_template_versions, report_markdown
from app.prompts.router import ABRule, PromptABRouter
from app.prompts.templates import get_template_changelog, list_template_keys, list_template_versions


class PromptTemplateTests(unittest.TestCase):
    def test_has_required_template_keys(self) -> None:
        keys = set(list_template_keys())
        required = {
            "PROPERTY_UNOWNED_TEMPLATE",
            "PROPERTY_SELF_TEMPLATE",
            "PROPERTY_ALLY_TEMPLATE",
            "PROPERTY_OTHER_TEMPLATE",
            "BANK_TEMPLATE",
            "EVENT_TEMPLATE",
            "EMPTY_TEMPLATE",
            "QUIZ_TEMPLATE",
        }
        self.assertTrue(required.issubset(keys))

    def test_template_versions_and_changelog(self) -> None:
        versions = list_template_versions("BANK_TEMPLATE")
        self.assertGreaterEqual(len(versions), 2)
        changelog = get_template_changelog()
        bank_rows = [item for item in changelog if item["template_key"] == "BANK_TEMPLATE"]
        self.assertGreaterEqual(len(bank_rows), 2)

    def test_ab_router_is_deterministic(self) -> None:
        router = PromptABRouter(
            rules={"BANK_TEMPLATE": ABRule("1.0.0", "1.1.0", 0.5)},
        )
        first = router.resolve_version("BANK_TEMPLATE", "g-a", "p1", 11)
        second = router.resolve_version("BANK_TEMPLATE", "g-a", "p1", 11)
        self.assertEqual(first, second)

    def test_ab_report_script_logic(self) -> None:
        report = compare_template_versions(
            template_key="BANK_TEMPLATE",
            baseline_version="1.0.0",
            challenger_version="1.1.0",
            games=4,
            max_rounds=8,
            seed=42,
        )
        text = report_markdown(report)
        self.assertIn("Template A/B Report", text)
        self.assertEqual(report.template_key, "BANK_TEMPLATE")
        self.assertEqual(report.baseline_version, "1.0.0")
        self.assertEqual(report.challenger_version, "1.1.0")


if __name__ == "__main__":
    unittest.main()
