from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .config import Settings


def _month_start_unix() -> int:
    now = datetime.now(timezone.utc)
    return int(
        datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp()
    )


def _manual(item: dict[str, Any]) -> dict[str, Any]:
    used = item.get("used")
    budget = item.get("budget")
    remaining = item.get("remaining")
    if remaining is None and budget is not None and used is not None:
        remaining = max(float(budget) - float(used), 0.0)
    return {
        "provider": str(item.get("provider", "manual")),
        "label": str(item.get("label", item.get("provider", "手动账户"))),
        "status": "ok",
        "balance_type": str(item.get("balance_type", "manual")),
        "currency": str(item.get("currency", "USD")),
        "used": used,
        "budget": budget,
        "remaining": remaining,
        "updated_at": int(time.time() * 1000),
    }


def get_manual_balances(settings: Settings) -> list[dict[str, Any]]:
    return [_manual(x) for x in settings.manual_balances if isinstance(x, dict)]


async def get_openai_key_budgets(settings: Settings) -> list[dict[str, Any]]:
    """按 api_key_id 查询本月成本，并计算“预算减成本”。"""
    if not settings.openai_admin_key:
        return []

    headers = {
        "Authorization": f"Bearer {settings.openai_admin_key}",
        "Content-Type": "application/json",
    }
    params: dict[str, Any] = {
        "start_time": str(_month_start_unix()),
        "end_time": str(int(time.time())),
        "bucket_width": "1d",
        "limit": "31",
        "group_by": "api_key_id",
    }
    timeout = ClientTimeout(total=settings.request_timeout_seconds)
    costs: dict[str, float] = {}
    next_page: str | None = None

    async with ClientSession(timeout=timeout) as session:
        while True:
            if next_page:
                params["page"] = next_page
            else:
                params.pop("page", None)

            async with session.get(
                "https://api.openai.com/v1/organization/costs",
                params=params,
                headers=headers,
            ) as response:
                if response.status != 200:
                    body = await response.text()
                    raise RuntimeError(
                        f"OpenAI 成本查询失败：HTTP {response.status} {body[:300]}"
                    )
                payload = await response.json()

            for bucket in payload.get("data", []):
                for result in bucket.get("results", []):
                    key_id = str(result.get("api_key_id") or "unknown")
                    amount = result.get("amount") or {}
                    if str(amount.get("currency", "")).lower() == "usd":
                        costs[key_id] = costs.get(key_id, 0.0) + float(
                            amount.get("value", 0.0)
                        )

            next_page = payload.get("next_page")
            if not next_page:
                break

    rows: list[dict[str, Any]] = []
    configured = set(settings.openai_key_budgets)
    now_ms = int(time.time() * 1000)

    for key_id, cfg in settings.openai_key_budgets.items():
        if not isinstance(cfg, dict):
            continue
        budget = float(cfg.get("budget", 0.0))
        used = round(costs.get(key_id, 0.0), 6)
        rows.append(
            {
                "provider": "openai",
                "label": str(cfg.get("label", f"OpenAI {key_id[-6:]}")),
                "api_key_id": key_id,
                "status": "ok",
                "balance_type": "budget_minus_cost",
                "currency": "USD",
                "used": used,
                "budget": budget,
                "remaining": round(max(budget - used, 0.0), 6),
                "updated_at": now_ms,
            }
        )

    for key_id, used in costs.items():
        if key_id in configured:
            continue
        rows.append(
            {
                "provider": "openai",
                "label": f"OpenAI {key_id[-6:]}",
                "api_key_id": key_id,
                "status": "ok",
                "balance_type": "cost_only",
                "currency": "USD",
                "used": round(used, 6),
                "budget": None,
                "remaining": None,
                "updated_at": now_ms,
            }
        )
    return rows
