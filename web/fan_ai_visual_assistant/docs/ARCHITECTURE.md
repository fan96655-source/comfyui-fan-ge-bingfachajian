# 架构说明

```text
ComfyUI Sidebar
├── GET /api/jobs
├── GET /api/jobs/{id}
├── POST /api/jobs/{id}/cancel
├── POST /prompt
└── GET /fan-ai-assistant/api/balances
          ├── OpenAI 组织成本 Adapter
          └── 手动余额 Adapter
```

## 职责

### ComfyUI Core

负责工作流提交、队列、执行、任务历史、输出文件和 WebSocket 执行事件。

### 帆 AI 助手前端

负责个人中心、任务列表、实时计时、输出预览、重跑、Seed 随机再出、载入画布和取消任务。

### 帆 AI 助手后端

负责密钥隔离、供应商金额统一格式、网络超时和错误归一化。

## 当前版本不做

多用户权限、云端永久链接、商业支付、任务长期归档、多 Worker 和数据库项目管理。这些应放到第二阶段的独立业务层。
