from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

from app.agent_memory import AgentMemoryStore
from app.prompts import PromptABRouter, default_router
from app.schemas import (
    ActionOption,
    AgentDecisionEnvelope,
    AgentTurnOutput,
    BoardSnapshot,
    DecisionAudit,
    OutputContract,
    PlayerSnapshot,
    TileContext,
    TurnInput,
    TurnMeta,
)


class ModelTimeoutError(Exception):
    pass


class OutputParseError(Exception):
    pass


class IllegalActionError(Exception):
    pass


class DecisionModel(Protocol):
    model_tag: str

    def generate(self, prompt: str, output_contract: OutputContract, timeout_sec: float) -> str:
        ...


class RuntimeConfig(BaseModel):
    model_provider: str = Field(default=os.getenv("MODEL_PROVIDER", "heuristic"))
    model_name: str = Field(default=os.getenv("MODEL_NAME", "gpt-4o-mini"))
    model_base_url: str = Field(default=os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1"))
    model_api_key: str = Field(default=os.getenv("MODEL_API_KEY", ""))
    timeout_sec: float = Field(default=float(os.getenv("MODEL_TIMEOUT_SEC", "8")), gt=0.5, le=60)
    max_retries: int = Field(default=int(os.getenv("MODEL_MAX_RETRIES", "2")), ge=0, le=5)


class OpenAICompatibleDecisionModel:
    def __init__(self, model_name: str, model_base_url: str, model_api_key: str) -> None:
        self._model_name = model_name
        self._model_base_url = model_base_url.rstrip("/")
        self._model_api_key = model_api_key
        self.model_tag = f"openai-compatible:{model_name}"

    def generate(self, prompt: str, output_contract: OutputContract, timeout_sec: float) -> str:
        if not self._model_api_key:
            raise RuntimeError("MODEL_API_KEY is empty for openai-compatible provider")

        headers = {
            "Authorization": f"Bearer {self._model_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a strict decision agent. Always return JSON only. "
                        f"Protocol must be {output_contract.protocol}."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        try:
            with httpx.Client(timeout=timeout_sec) as client:
                response = client.post(f"{self._model_base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError("model timeout") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"model http error: {exc}") from exc

        body = response.json()
        choices = body.get("choices", [])
        if not choices:
            raise OutputParseError("empty choices in model response")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            texts = [chunk.get("text", "") for chunk in content if isinstance(chunk, dict)]
            return "".join(texts)
        if not isinstance(content, str):
            raise OutputParseError("invalid content in model response")
        return content


class HeuristicDecisionModel:
    def __init__(self, model_tag: str = "heuristic/v1") -> None:
        self.model_tag = model_tag

    def generate(self, prompt: str, output_contract: OutputContract, timeout_sec: float) -> str:
        template_version = "1.0.0"
        for line in prompt.splitlines():
            if line.startswith("version: "):
                template_version = line.split(":", 1)[1].strip()
                break
        aggressive = template_version.endswith("1.1.0")

        input_json = prompt.split("## Turn Input JSON\n", 1)[-1].strip()
        payload = json.loads(input_json)
        options = payload.get("options", [])
        player = payload.get("player_state", {})
        tile_context = payload.get("tile_context", {})

        selected_action = "pass"
        args: dict[str, Any] = {}
        candidate_actions: list[str] = []
        for item in options:
            action_name = item["action"]
            candidate_actions.append(action_name)

        if tile_context.get("tile_subtype") == "PROPERTY_UNOWNED":
            buy = next((item for item in options if item["action"] == "buy_property"), None)
            liquidity_floor = 250 if aggressive else 400
            if buy and player.get("cash", 0) >= int(tile_context.get("property_price") or 0) + liquidity_floor:
                selected_action = "buy_property"
                args = buy.get("default_args", {})
            else:
                selected_action = "skip_buy" if any(item["action"] == "skip_buy" for item in options) else "pass"
        elif tile_context.get("tile_subtype") == "BANK":
            deposit = next((item for item in options if item["action"] == "bank_deposit"), None)
            withdraw = next((item for item in options if item["action"] == "bank_withdraw"), None)
            deposit_threshold = 1300 if aggressive else 1600
            withdraw_threshold = 450 if aggressive else 300
            if player.get("cash", 0) > deposit_threshold and deposit:
                selected_action = "bank_deposit"
                args = deposit.get("default_args", {})
            elif player.get("cash", 0) < withdraw_threshold and withdraw:
                selected_action = "bank_withdraw"
                args = withdraw.get("default_args", {})
        else:
            alliance = next((item for item in options if item["action"] == "propose_alliance"), None)
            if alliance and player.get("alliance_with") is None and player.get("cash", 0) < 500:
                selected_action = "propose_alliance"
                args = alliance.get("default_args", {})

        response = {
            "protocol": output_contract.protocol,
            "action": selected_action,
            "args": args,
            "thought": "heuristic fallback model",
            "strategy_tags": infer_strategy_tags(player_cash=player.get("cash", 0), action=selected_action),
            "candidate_actions": candidate_actions,
            "confidence": 0.72,
        }
        return json.dumps(response, ensure_ascii=False)


@dataclass
class TurnBuildInput:
    turn_meta: TurnMeta
    tile_context: TileContext
    player_state: PlayerSnapshot
    players_snapshot: list[PlayerSnapshot]
    board_snapshot: BoardSnapshot
    options: list[ActionOption]


class AgentRuntime:
    def __init__(
        self,
        config: RuntimeConfig | None = None,
        model: DecisionModel | None = None,
        router: PromptABRouter | None = None,
        memory: AgentMemoryStore | None = None,
    ) -> None:
        self.config = config or RuntimeConfig()
        self.model = model or self._build_model()
        self.router = router or default_router()
        self.memory = memory or AgentMemoryStore()

    def build_turn_input(self, payload: TurnBuildInput) -> TurnInput:
        template_key = template_key_from_tile(payload.tile_context.tile_subtype)
        template = self.router.resolve_template(
            template_key,
            payload.turn_meta.game_id,
            payload.turn_meta.current_player_id,
            payload.turn_meta.turn_index,
        )
        memory_summary = self.memory.summary(payload.turn_meta.game_id, payload.turn_meta.current_player_id)
        return TurnInput(
            turn_meta=payload.turn_meta,
            tile_context=payload.tile_context,
            player_state=payload.player_state,
            players_snapshot=payload.players_snapshot,
            board_snapshot=payload.board_snapshot,
            options=payload.options,
            output_contract=OutputContract(),
            template_key=template.key,
            template_version=template.version,
            memory_summary=memory_summary,
        )

    def decide(self, turn_input: TurnInput) -> AgentDecisionEnvelope:
        template = self.router.resolve_template(
            turn_input.template_key,
            turn_input.turn_meta.game_id,
            turn_input.turn_meta.current_player_id,
            turn_input.turn_meta.turn_index,
        )
        prompt = template.render(turn_input)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        prompt_token_estimate = estimate_tokens(prompt)

        failure_codes: list[str] = []
        raw_response_summary = ""
        parsed: AgentTurnOutput | None = None
        attempt_count = 0

        for attempt in range(1, self.config.max_retries + 2):
            attempt_count = attempt
            try:
                start = time.perf_counter()
                raw = self.model.generate(
                    prompt,
                    output_contract=turn_input.output_contract,
                    timeout_sec=self.config.timeout_sec,
                )
                elapsed = time.perf_counter() - start
                raw_response_summary = summarize_raw_response(raw, elapsed)
                parsed = parse_turn_output(raw, turn_input.output_contract, turn_input.options)
                break
            except ModelTimeoutError:
                failure_codes.append("timeout")
                continue
            except OutputParseError:
                failure_codes.append("parse_error")
                continue
            except IllegalActionError:
                failure_codes.append("illegal_action")
                break
            except Exception as exc:  # noqa: BLE001
                failure_codes.append(f"runtime_error:{type(exc).__name__}")
                continue

        if parsed is None:
            fallback = fallback_decision(turn_input.options)
            audit = DecisionAudit(
                model_tag=self.model.model_tag,
                template_key=turn_input.template_key,
                template_version=turn_input.template_version,
                prompt_hash=prompt_hash,
                prompt_token_estimate=prompt_token_estimate,
                attempt_count=attempt_count,
                status="fallback",
                failure_codes=failure_codes,
                raw_response_summary=raw_response_summary,
                fallback_reason=";".join(failure_codes) if failure_codes else "unknown",
                final_decision=fallback,
            )
            decision = fallback
        else:
            audit = DecisionAudit(
                model_tag=self.model.model_tag,
                template_key=turn_input.template_key,
                template_version=turn_input.template_version,
                prompt_hash=prompt_hash,
                prompt_token_estimate=prompt_token_estimate,
                attempt_count=attempt_count,
                status="ok",
                failure_codes=failure_codes,
                raw_response_summary=raw_response_summary,
                fallback_reason=None,
                final_decision=parsed,
            )
            decision = parsed

        self.memory.record(
            game_id=turn_input.turn_meta.game_id,
            player_id=turn_input.turn_meta.current_player_id,
            turn_index=turn_input.turn_meta.turn_index,
            action=decision.action,
            strategy_tags=decision.strategy_tags,
            note=decision.thought or "",
        )

        return AgentDecisionEnvelope(decision=decision, audit=audit)

    def _build_model(self) -> DecisionModel:
        if self.config.model_provider == "openai-compatible":
            return OpenAICompatibleDecisionModel(
                model_name=self.config.model_name,
                model_base_url=self.config.model_base_url,
                model_api_key=self.config.model_api_key,
            )
        return HeuristicDecisionModel(model_tag=f"{self.config.model_provider}:{self.config.model_name}")


def parse_turn_output(raw: str | dict[str, Any], output_contract: OutputContract, options: list[ActionOption]) -> AgentTurnOutput:
    data = parse_json_only(raw)
    try:
        parsed = AgentTurnOutput.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        raise OutputParseError("output schema validation failed") from exc
    if parsed.protocol != output_contract.protocol:
        raise OutputParseError("protocol mismatch")

    option_map = {item.action: item for item in options}
    if parsed.action not in option_map:
        raise IllegalActionError(f"action not allowed: {parsed.action}")

    option = option_map[parsed.action]
    for field in option.required_args:
        if field not in parsed.args:
            raise IllegalActionError(f"missing required arg: {field}")
    for key, allowed_values in option.allowed_values.items():
        if key in parsed.args and parsed.args[key] not in allowed_values:
            raise IllegalActionError(f"arg value not allowed: {key}")
    return parsed


def parse_json_only(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        raise OutputParseError("raw response is not a JSON string")

    text = raw.strip()
    if text.startswith("```"):
        # tolerate fenced outputs but still enforce single JSON block
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OutputParseError("json_only parse failed") from exc

    if not isinstance(data, dict):
        raise OutputParseError("json root must be object")
    return data


def fallback_decision(options: list[ActionOption]) -> AgentTurnOutput:
    if not options:
        return AgentTurnOutput(action="pass", args={}, thought="fallback without options")

    option_map = {item.action: item for item in options}
    if "pass" in option_map:
        return AgentTurnOutput(action="pass", args={}, thought="fallback to pass")

    first = options[0]
    return AgentTurnOutput(
        action=first.action,
        args=first.default_args,
        thought="fallback to first allowed action",
    )


def template_key_from_tile(tile_subtype: str) -> str:
    mapping = {
        "PROPERTY_UNOWNED": "PROPERTY_UNOWNED_TEMPLATE",
        "PROPERTY_SELF": "PROPERTY_SELF_TEMPLATE",
        "PROPERTY_ALLY": "PROPERTY_ALLY_TEMPLATE",
        "PROPERTY_OTHER": "PROPERTY_OTHER_TEMPLATE",
        "BANK": "BANK_TEMPLATE",
        "EVENT": "EVENT_TEMPLATE",
        "QUIZ": "QUIZ_TEMPLATE",
        "EMPTY": "EMPTY_TEMPLATE",
    }
    return mapping.get(tile_subtype, "EMPTY_TEMPLATE")


def infer_strategy_tags(player_cash: int, action: str) -> list[str]:
    tags: list[str] = []
    if player_cash < 500:
        tags.append("cash_priority")
    if action in {"buy_property", "propose_alliance"}:
        tags.append("expansion")
    if action in {"pass", "skip_buy"}:
        tags.append("conservative")
    return tags


def summarize_raw_response(raw: str, elapsed_sec: float) -> str:
    compact = raw.replace("\n", " ").strip()
    if len(compact) > 240:
        compact = compact[:237] + "..."
    return f"latency={elapsed_sec:.3f}s raw={compact}"


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def decide_fallback(allowed_actions: list[str]) -> AgentTurnOutput:
    options = [ActionOption(action=item, description=item) for item in allowed_actions]
    return fallback_decision(options)
