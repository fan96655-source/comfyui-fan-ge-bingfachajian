from __future__ import annotations

import asyncio
import logging
import time

from aiohttp import web
from server import PromptServer

from .config import get_settings
from .providers import get_manual_balances, get_openai_key_budgets

LOGGER = logging.getLogger(__name__)
routes = PromptServer.instance.routes


@routes.get("/fan-ai-assistant/api/health")
async def health(_: web.Request) -> web.Response:
    settings = get_settings()
    return web.json_response(
        {
            "ok": True,
            "name": settings.assistant_name,
            "timestamp": int(time.time() * 1000),
        }
    )


@routes.get("/fan-ai-assistant/api/balances")
async def balances(_: web.Request) -> web.Response:
    settings = get_settings()
    result = get_manual_balances(settings)
    warnings: list[str] = []

    if settings.openai_admin_key:
        try:
            result.extend(
                await asyncio.wait_for(
                    get_openai_key_budgets(settings),
                    timeout=settings.request_timeout_seconds + 2,
                )
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("OpenAI 成本查询失败")
            warnings.append(str(exc))

    response = web.json_response(
        {
            "assistant_name": settings.assistant_name,
            "balances": result,
            "warnings": warnings,
            "updated_at": int(time.time() * 1000),
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return response
