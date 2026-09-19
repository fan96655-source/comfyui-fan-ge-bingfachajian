from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Settings:
    assistant_name: str
    openai_admin_key: str | None
    openai_key_budgets: dict[str, dict[str, Any]]
    manual_balances: list[dict[str, Any]]
    request_timeout_seconds: float


def _load_json_env(name: str, default: Any) -> Any:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"环境变量 {name} 不是合法 JSON：{exc}") from exc


def get_settings() -> Settings:
    budgets = _load_json_env("FAN_AI_OPENAI_KEY_BUDGETS_JSON", {})
    manual = _load_json_env("FAN_AI_MANUAL_BALANCES_JSON", [])
    if not isinstance(budgets, dict):
        raise RuntimeError("FAN_AI_OPENAI_KEY_BUDGETS_JSON 必须是 JSON 对象")
    if not isinstance(manual, list):
        raise RuntimeError("FAN_AI_MANUAL_BALANCES_JSON 必须是 JSON 数组")
    return Settings(
        assistant_name=os.getenv(
            "FAN_AI_ASSISTANT_NAME", "🚀 帆 AI 视觉个人助手"
        ),
        openai_admin_key=os.getenv("OPENAI_ADMIN_KEY"),
        openai_key_budgets=budgets,
        manual_balances=manual,
        request_timeout_seconds=float(
            os.getenv("FAN_AI_REQUEST_TIMEOUT_SECONDS", "15")
        ),
    )
