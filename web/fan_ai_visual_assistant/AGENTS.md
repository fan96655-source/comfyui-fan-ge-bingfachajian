# 🚀 帆 AI 视觉个人助手：Codex 项目指引

## 项目目标

开发一个本地 ComfyUI 扩展，名称为“🚀 帆 AI 视觉个人助手”。

核心能力：

1. 在 ComfyUI 左侧栏注册个人中心。
2. 读取本地 `/api/jobs`，显示任务状态、创建时间、运行耗时和输出预览。
3. 显示最近一次任务及本地输出链接。
4. 支持原样重跑、随机 Seed 再出、载入画布和取消任务。
5. 后端统一展示 API 预算或余额，不向浏览器暴露完整密钥。
6. 不修改 ComfyUI Core，不 monkey patch 核心原型。

## 开始任务前必须阅读

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/API_CONTRACT.md`
- `docs/SECURITY.md`
- `docs/EXEC_PLAN.md`

本文件只做导航和稳定约束，不要继续堆成百科全书。

## 技术边界

- 后端：Python 3.10+、aiohttp、ComfyUI `PromptServer` 自定义路由。
- 前端：原生 ES Module、官方 `app.registerExtension`、`registerSidebarTab`、`api.fetchApi`。
- 数据源：优先复用 ComfyUI Core `/api/jobs` 和 `/prompt`。
- 当前版本不引入数据库和前端构建工具。
- API 密钥仅可从后端环境变量或密钥管理器读取。
- 不在工作流、前端代码、localStorage、日志或接口响应中保存完整密钥。

## 修改规则

- 优先小改动，不无故重写整个模块。
- 所有网络请求必须有超时和错误处理。
- 所有用户可见文字优先使用中文。
- 供应商金额必须标注 `exact_credit`、`budget_minus_cost`、`cost_only` 或 `manual`。
- “余额”“预算剩余”“成本”不得混称。
- 再生成只修改明确识别的 Seed 字段。
- 外部 API 任务可能没有 UI 工作流，必须明确提示。

## 验证命令

```bash
python -m compileall .
python -m unittest discover -s tests -v
```

修改 JavaScript 后至少检查：

- 浏览器控制台无语法错误。
- 侧边栏只注册一次。
- 刷新不会累积多个轮询器。
- `/api/jobs` 失败时界面不会整页崩溃。
- 前端和日志中不出现完整 API Key。

## 完成标准

提交前说明：

1. 修改文件。
2. 已完成需求。
3. 供应商权限依赖。
4. 验证结果。
5. 兼容性风险。
