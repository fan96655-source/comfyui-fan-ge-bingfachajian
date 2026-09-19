# API 契约

## GET `/fan-ai-assistant/api/health`

```json
{"ok":true,"name":"🚀 帆 AI 视觉个人助手","timestamp":0}
```

## GET `/fan-ai-assistant/api/balances`

```json
{
  "assistant_name":"🚀 帆 AI 视觉个人助手",
  "balances":[{
    "provider":"openai",
    "label":"OpenAI 主项目",
    "status":"ok",
    "balance_type":"budget_minus_cost",
    "currency":"USD",
    "used":12.5,
    "budget":100,
    "remaining":87.5,
    "updated_at":0
  }],
  "warnings":[],
  "updated_at":0
}
```

## Core 依赖

- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/cancel`
- `POST /prompt`
- `GET /view`

旧版 Core 没有 `/api/jobs` 时，需要增加 `/history` 兼容层。
