# 🚀 帆 AI 视觉个人助手

一个本地 ComfyUI 侧边栏扩展，用于查看任务耗时、API 预算或余额、最近任务、输出预览，并执行原样重跑、随机 Seed 再出、载入画布和取消任务。

## 余额语义

API Key 通常没有统一的“余额接口”。本插件区分：

- `exact_credit`：供应商返回的真实信用余额
- `budget_minus_cost`：月预算减去本月成本
- `cost_only`：只能查询成本
- `manual`：手动配置

OpenAI 示例使用组织成本接口，因此显示“预算减成本”，不是预付费信用余额。

## 安装

把整个目录复制到：

```text
ComfyUI/custom_nodes/fan_ai_visual_assistant
```

重启 ComfyUI。

## 环境变量

参考 `.env.example`。ComfyUI 不会自动加载该文件，请配置到系统环境、启动脚本或密钥管理器。

Windows 临时测试：

```bat
set OPENAI_ADMIN_KEY=你的管理密钥
set FAN_AI_OPENAI_KEY_BUDGETS_JSON={"key-id-example":{"label":"OpenAI 主项目","budget":100}}
```

不要把含真实密钥的脚本提交到 Git。

## 使用

1. 启动 ComfyUI。
2. 打开左侧火箭图标。
3. 运行任意工作流。
4. 查看任务和耗时。
5. 点击“原样重跑”“再出生成”“载入画布”或“查看输出”。

## 当前限制

1. 依赖较新的 ComfyUI Core `/api/jobs`。
2. 外部 API 任务可能没有 UI 工作流。
3. Seed 自动识别只覆盖常见字段名。
4. `/view` 是本地链接。
5. 当前没有数据库和项目备注。

## Codex 中文开发入口

仓库根目录已提供 `AGENTS.md`。推荐给 Codex 的首条任务：

```text
阅读 AGENTS.md 与 docs 目录。
检查插件是否兼容当前 ComfyUI 版本。
先运行 Python 测试，再实现 SQLite 任务归档与工作流 Manifest。
不要修改 ComfyUI Core，不得在前端暴露任何 API Key。
完成后报告修改文件、测试结果和兼容性风险。
```
