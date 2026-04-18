from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import httpx

from app.agent_runtime import RuntimeConfig
from app.schemas import ModelExperienceRecord

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "model_experience_db.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ModelExperienceStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or DEFAULT_DB_PATH
        self._lock = Lock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._db_path.exists():
            self._db_path.write_text("[]", encoding="utf-8")

    def _read_rows(self) -> list[dict[str, Any]]:
        try:
            payload = json.loads(self._db_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _write_rows(self, rows: list[dict[str, Any]]) -> None:
        self._db_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_record(self, model_id: str, provider: str, game_id: str, summary: str) -> ModelExperienceRecord:
        record = ModelExperienceRecord(
            model_id=model_id,
            provider=provider,
            game_id=game_id,
            summary=summary.strip(),
            created_at=_utc_now(),
        )
        with self._lock:
            rows = self._read_rows()
            rows.append(record.model_dump(mode="json"))
            self._write_rows(rows)
        return record

    def list_records(self, model_id: str | None = None, limit: int = 100) -> list[ModelExperienceRecord]:
        rows = self._read_rows()
        parsed: list[ModelExperienceRecord] = []
        for row in rows:
            try:
                parsed.append(ModelExperienceRecord.model_validate(row))
            except Exception:  # noqa: BLE001
                continue
        parsed.sort(key=lambda item: item.created_at, reverse=True)
        if model_id:
            parsed = [item for item in parsed if item.model_id == model_id]
        return parsed[: max(limit, 1)]

    def context_for_model(self, model_id: str, max_items: int = 3) -> str:
        rows = self.list_records(model_id=model_id, limit=max_items)
        if not rows:
            return "暂无历史经验。"
        lines = []
        for item in rows:
            lines.append(
                f"[{item.created_at.date().isoformat()}|{item.game_id}] {item.summary}"
            )
        return "；".join(lines)


def _heuristic_summary(materials: dict[str, Any]) -> str:
    winner = str(materials.get("winner", "未知玩家"))
    turns = int(materials.get("total_turns", 0))
    bankrupt_count = int(materials.get("bankrupt_count", 0))
    if bankrupt_count > 0:
        return (
            f"本局共 {turns} 手，{winner} 在中后期通过资金管理稳定领先。"
            "后续应优先保现金安全垫，再择机扩张。"
        )
    return (
        f"本局共 {turns} 手，{winner} 依靠稳健买地与低失误拿下优势。"
        "后续建议保持节奏一致，避免无准备的高风险决策。"
    )


def build_experience_summary(
    runtime_cfg: RuntimeConfig,
    materials: dict[str, Any],
) -> str:
    provider = runtime_cfg.model_provider
    if provider != "openai-compatible" or not runtime_cfg.model_api_key:
        return _heuristic_summary(materials)

    system_prompt = (
        "你是策略复盘助手。请只输出两句中文经验总结。"
        "第一句讲本局关键打法，第二句讲下一局可执行建议。"
        "禁止输出编号、禁止输出JSON。"
    )
    user_prompt = "\n".join(
        [
            "# 对局材料",
            json.dumps(materials, ensure_ascii=False, sort_keys=True),
            "",
            "请给出两句中文经验总结。",
        ]
    )
    payload = {
        "model": runtime_cfg.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {runtime_cfg.model_api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=max(runtime_cfg.timeout_sec, 6)) as client:
            response = client.post(f"{runtime_cfg.model_base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            text = "".join(chunk.get("text", "") for chunk in content if isinstance(chunk, dict))
        else:
            text = str(content)
        text = text.strip()
        if not text:
            return _heuristic_summary(materials)
        return text.replace("\n", " ").strip()
    except Exception:  # noqa: BLE001
        return _heuristic_summary(materials)
