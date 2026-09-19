# 🪄 帆 · 万象生图

这是一个从零编写的独立 ComfyUI 节点，不依赖、也不会修改同级的旧节点。

将本目录放在 `ComfyUI/custom_nodes/` 下，重启 ComfyUI 后，在 `APL/图像生成` 分类中添加“🪄 帆 · 万象生图”。

## 使用方式

- `image1` 到 `image10` 是十个独立且可选的 `IMAGE` 输入。未连接的输入会被过滤；批次中的每帧按插槽顺序计入，总数超过 10 张会明确报错，不会静默丢图。
- 选择 `RH直连` 时，节点按 RH 文档逐张上传参考图、提交对应模型任务、轮询结果，并下载图片转为 ComfyUI `IMAGE`。RH 的三个标准 image-to-image 接口要求至少一张参考图。
- `api_key` 为密码输入，只用于 HTTP 请求头；不会写日志，也不会放进 `response` 输出。
- `seed=0` 始终生成新的随机种子。`randomize` 会计算本次实际种子，并将它写入结构化响应信息。
- `image_url` 返回第一张可下载图片的 URL；所有返回链接和原始服务响应会放进 `response` JSON。

## API 线路

每个下拉线路都有独立的协议适配器和图像接口配置；节点不会读取另一家平台的字段，也不会因为模型名称相同而跨平台回退。Markdown 文档只是对应平台的契约说明，实际映射集中在 `fan_wanxiang_image.py` 的 `CHANNEL_MODELS`、`APL_ROUTE_PROFILES`、`RH_ENDPOINTS` 和各平台适配器中。

| 线路 | 对应文档/协议 | 支持模型 |
| --- | --- | --- |
| `RH直连` | `RH香蕉2的接口文档.md`、`RH香蕉PRO接口文档.md`、`RH GPT2接口文档.md`；上传 + 提交 + `/query` 轮询 | 三种模型 |
| `Grsai直连` | `Grsai Nano Banana 接口文档.md`、`Grsai gpt-image-2gpt-image-2.5接口文档.md`；Gemini 与 GPT 使用不同接口和字段 | 七种模型 |
| `APIYI直连` | APIYI Gemini 原生 `/v1beta/models/...:generateContent` | 两种 Gemini 模型 |
| `YYRouter直连` | YYRouter Gemini 原生协议或 Images API | 三种模型 |
| `第三方线路` | 用户填写基础地址；按第三方的原生 Gemini/OpenAI 兼容协议调用 | 三种模型 |
| `自定义线路` | 用户填写完整接口地址；发送本节点定义的通用 JSON | 由用户服务端决定 |

`第三方线路` 与 `自定义线路` 是两种不同协议：前者要求服务端兼容 Gemini/OpenAI 原生接口，后者接收本节点定义的通用 JSON，二者不会互相回退。

Grsai Gemini 请求继续使用文档规定的 `webHook: "-1"` 任务提交模式，并轮询 `/v1/draw/result`。Grsai GPT Image 请求使用新文档的 `/v1/api/generate`，发送 `images`、像素尺寸、`quality` 和 `replyType: "async"`，收到任务 ID 后通过 GET `/v1/api/result?id=...` 查询结果，不混用 Gemini 的字段。

GPT 查询方式依据[Grsai 异步生成结果查询文档](https://qmy27nhsd9.apifox.cn/452409577e0)。节点每 5 秒查询一次，每个任务最多等待 15 分钟；生成耗时超过 60 秒时仍可继续查询同一个任务。更新节点后需重启 ComfyUI 才能加载修复。平台已成功的旧任务可在调用日志中查看详情，重新运行节点会创建新的生成任务。

如果网关把任务确认包装成 SSE，或已经发送完整 JSON 却没有及时关闭连接，节点会在读到任务 ID 后立即停止等待并转入轮询。首次生图提交若发生读取超时，节点会提示“平台可能已经受理”，并且**不会自动重发提交**，以免同一任务重复扣费；任务查询属于幂等操作，短暂网络错误、HTTP 429/5xx 才会进行有限退避重试。持续返回 `code=-22` 只给予短暂可见性宽限，不会再把一个不存在的任务等待数分钟。

Grsai GPT 任务已返回 ID 且状态为 `failed` 时，只有 `Upstream rate limit exceeded`（上游限流）和 `Upstream service is temporarily unavailable`（上游服务暂时不可用）会触发生图重试。每张输出最多尝试 3 次，重试前分别等待 30–35 秒、60–65 秒，并复用原模型、提示词和参考图。成功输出不会重新生成；参数、余额、审核错误，以及提交超时、查询失败或任务状态不明均不会自动创建替代任务。该策略仅用于 Grsai GPT。

重试会创建新的任务 ID，计费与失败任务退款以 Grsai 平台记录为准。重试后成功时，`响应信息` 中的 `generation_retry` 记录尝试次数、失败任务 ID 和错误；多图模式下该记录位于 `tasks[].response`。重试耗尽后节点停止该输出的生成并报告上游故障，不保证在 Grsai 持续不可用时出图。

## 🚀 高性能 - 智能并发生成

参数控制区新增 `🚀 高性能 - 智能并发生成`，可选 `1–12`，默认 `1`。默认值保持旧工作流的单任务行为；当前该能力只按已提供的开源节点语义用于 `Grsai 直连`，其他路线选择大于 1 会明确提示改回 1，不会把 Grsai 的接口规则套到别的平台。

- 数量 `N` 表示创建 `N` 个独立生图任务，不是把 10 张参考图拆成 N 组；平台可能按 N 个任务分别计费。
- 用户可以选择最多 12 个输出，当前每次节点执行只运行 1 个 Grsai 任务，其余任务排队；GPT 失败后的延迟重试也占用该任务位置。
- 十张参考图只进行一次尺寸/格式适配，并复用已经编码的内容，不会在每个任务中重复进行 PNG/Base64 处理。
- 参考图适配与输出任务数量相互独立：即使只生成 1 张图，多个参考图也会按总像素自动使用最多 4 路 CPU 适配；超大图会主动降低到 1–2 路，避免内存峰值。
- 多任务结果按提交顺序归位；允许部分任务成功。第三个输出继续返回第一条成功任务 ID，以兼容旧下游；全部任务 ID、成功/失败数量和逐项错误都保存在第四个 `响应信息` JSON 中。
- 返回图片最多 4 路并行下载；单张下载失败时保留其他成功图片并写入响应信息。若平台返回的多张图尺寸不同，节点会明确报错，不再静默丢弃其中一部分。

该功能缩短的是“需要生成多张结果”时的总耗时；单个任务本身仍由 Grsai 平台生成，不能把单张 89 秒变成几秒。

`RH直连` 是依据本目录 RH 接口文档实现并完整支持上传、提交、轮询的线路。模型会自动路由到各自的 RH endpoint，而不是把模型名错误地作为单一路由字段发送。

三份本地文档与节点模型下拉框的对应关系如下：

| 节点模型 | 接入的文档 | RH 提交接口 | 文档专用规则 |
| --- | --- | --- | --- |
| `gemini-3.1-flash-image-preview` | `RH香蕉2的接口文档.md` | `/rhart-image-n-g31-flash/image-to-image` | 单张参考图最大 30 MB |
| `gemini-3-pro-image-preview` | `RH香蕉PRO接口文档.md` | `/rhart-image-n-pro/edit` | 单张参考图最大 10 MB；`auto` 时不发送宽高比 |
| `gpt-image-2` | `RH GPT2接口文档.md` | `/rhart-image-g-2-official/image-to-image` | 单张参考图最大 10 MB；固定发送文档要求的 `quality: medium` |

三种模型共用 RH 文档规定的上传接口 `/media/upload/binary` 与任务查询接口 `/query`；节点会自动上传 1–10 张参考图、获得 URL 后再提交对应模型任务。

`自定义线路` 时必须填写 `custom_api_url`（http/https）。节点会 POST 以下通用 JSON，其中参考图是 PNG data URI：

```json
{
  "model": "gemini-3.1-flash-image-preview",
  "prompt": "...",
  "reference_images": ["data:image/png;base64,..."],
  "parameters": {
    "aspect_ratio": "2:3",
    "resolution": "2K",
    "prompt_strength": "严格",
    "ref_strength": "高保留",
    "seed": 583,
    "effective_seed": 583,
    "randomize": "fixed"
  }
}
```

自定义服务响应应在 `results`、`images` 或 `data` 中返回图片 `url`、`image_url` 或 `b64_json`。

## 关于强度与种子

RH 随附文档没有定义 `seed`、`randomize`、`prompt_strength` 或 `ref_strength` 的原生字段。为保证 RH 请求符合已公开的接口契约，节点不会向 RH 直接发送未文档化字段：提示词强度和参考图保留强度会转换成明确的生成指令；种子策略会被计算并保存在结构化响应中。自定义线路则会按上面的 `parameters` JSON 完整传输这些字段。

## 参考图大小处理

适配器按路线文档处理参考图：RH 香蕉 2 单图最多 30 MiB，RH Pro/GPT 单图最多 10 MiB；APIYI 文档规定单图 7 MiB、建议控制在 5 MiB，因此 Grsai、APIYI、YYRouter、第三方和自定义路线采用稳定的 5 MiB 单图配置。每张图优先使用文档兼容的 PNG；仍超限时使用原分辨率高质量 JPEG，再按实际字节比例估算最小缩放并做最多四次微调，保留目标体积内最大的像素尺寸，不会直接缩成固定小图。该有界编码策略避免旧版对一张大图反复几十次重编码而造成分钟级等待。各平台仍可能有整包请求上限；适配器会先按总请求限制缩放，再提交，避免 Nginx 413。10 张大图若要同时保留，必须由对应平台提供文件上传/URL 引用接口，或提高其 Nginx 的 `client_max_body_size`。

对于会把多张图放进同一个请求的路线，适配器会根据实际输入张数动态分配请求预算：连接 2 张时每张预算更大，连接 10 张时自动平均分配，再对每张图寻找能满足总请求限制的最大分辨率。
