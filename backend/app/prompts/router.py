from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.prompts.templates import get_template, list_template_versions


@dataclass(frozen=True)
class ABRule:
    baseline_version: str
    challenger_version: str
    challenger_ratio: float


class PromptABRouter:
    def __init__(
        self,
        rules: dict[str, ABRule] | None = None,
        overrides: dict[str, str] | None = None,
    ) -> None:
        self._rules = rules or {}
        self._overrides = overrides or {}

    def resolve_version(self, template_key: str, game_id: str, player_id: str, turn_index: int) -> str:
        override = self._overrides.get(template_key)
        if override:
            return override

        rule = self._rules.get(template_key)
        versions = list_template_versions(template_key)
        if not versions:
            raise KeyError(f"unknown template key: {template_key}")
        if not rule:
            return versions[-1]

        ratio = min(max(rule.challenger_ratio, 0.0), 1.0)
        bucket = self._stable_bucket(template_key, game_id, player_id, turn_index)
        if bucket < int(ratio * 100):
            return rule.challenger_version
        return rule.baseline_version

    def resolve_template(self, template_key: str, game_id: str, player_id: str, turn_index: int):
        version = self.resolve_version(template_key, game_id, player_id, turn_index)
        return get_template(template_key, version)

    @staticmethod
    def _stable_bucket(template_key: str, game_id: str, player_id: str, turn_index: int) -> int:
        content = f"{template_key}:{game_id}:{player_id}:{turn_index}".encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        return int(digest[:8], 16) % 100


def default_router() -> PromptABRouter:
    return PromptABRouter(
        rules={
            "PROPERTY_UNOWNED_TEMPLATE": ABRule("1.0.0", "1.1.0", 0.5),
            "BANK_TEMPLATE": ABRule("1.0.0", "1.1.0", 0.5),
            "EVENT_TEMPLATE": ABRule("1.0.0", "1.1.0", 0.5),
            "EMPTY_TEMPLATE": ABRule("1.0.0", "1.1.0", 0.5),
        }
    )
