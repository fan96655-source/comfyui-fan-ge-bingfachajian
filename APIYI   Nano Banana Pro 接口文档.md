APIYI   Nano Banana Pro 接口文档
> ## Documentation Index
> Fetch the complete documentation index at: https://docs.apiyi.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Nano Banana Pro 图片生成

> 谷歌最新、最强的图像生成模型 gemini-3-pro-image-preview，俗称 Nano Banana Pro。支持自定义分辨率 1K、2K、4K 输出、10种宽高比，低至官网 2 折优惠。

<Note>
  **🔥 最新发布**：谷歌于 2026年2月26日发布了 **Nano Banana 2** (`gemini-3.1-flash-image-preview`)，Pro 级画质 + Flash 级速度，按量低至 \$0.025/张！[查看 Nano Banana 2 文档](/api-capabilities/nano-banana-2-image/overview)
</Note>

<Note>
  **🆕 2026年5月29日更新（去掉 `-preview`）**：谷歌更新了官方文档，推出去掉 `-preview` 的正式模型名 **`gemini-3-pro-image`**，API易已同步上线支持。

  * **原模型名仍可用**：`gemini-3-pro-image-preview` 继续正常调用，**价格不变**，现有代码无需改动。
  * **两个名字都能跑**：可按需选用新名 `gemini-3-pro-image` 或原 `-preview` 名。

  话说在前面：正式版相比 preview 版在效果表现、安全审核机制等方面是否存在差异，谷歌官方暂未明确说明，欢迎大家在实际使用中一起测试反馈。
</Note>

<Info>
  图片 API 全部为**同步调用**：没有异步任务 ID，客户端断开连接结果即丢失、但请求仍会计费。请为本模型设置足够大的 timeout，详见 [图片 API 调用须知与最佳实践](/api-capabilities/image-api-best-practices)。
</Info>

**Nano Banana Pro**（代号）是谷歌图像生成模型系列，目前有以下版本可用：

### 最新版本

* **Nano Banana 2**：`gemini-3.1-flash-image-preview`（🔥 2026年2月26日上线）— [查看详情](/api-capabilities/nano-banana-2-image/overview)
* **Nano Banana Pro**：`gemini-3-pro-image-preview`（2025年11月20日上线）

### 前代版本

* **正式版**：`gemini-2.5-flash-image`（稳定版，支持 10 种宽高比）
* **预览版**：`gemini-2.5-flash-image-preview`（⚠️ 已于2025年10月30日下线）

<Card>
  **核心优势**

  * 🔥 **Nano Banana Pro 新特性**：
    * 🎯 **4K 高清支持**：支持 1K、2K、4K 三种分辨率，最高可达 4096×4096
    * 📝 **文本渲染之王**：图像中的文字清晰可读，适合海报、广告等场景
    * ✨ **局部编辑**：支持摄像机角度、焦点、色彩分级、场景照明调整
    * 🧠 **智能推理**：基于 Gemini 3 Pro，更好地理解复杂提示词

  * 🚀 **通用优势**：
    * ⚡ **生成速度**：Nano Banana Pro 约 20 秒，前代版本约 10 秒
    * 💰 **价格实惠**：结合充值优惠，性价比极高
    * 🔄 **完全兼容**：完全兼容谷歌官方 Gemini API 格式
    * 🎨 **谷歌技术**：基于谷歌最新、最强的图像生成/编辑技术
</Card>

## 在线调试 API

<CardGroup cols={2}>
  <Card title="文生图 API" icon="wand-sparkles" href="/api-capabilities/nano-banana-image/text-to-image">
    输入文本提示词生成图片，带交互式 Playground 在线调试。
  </Card>

  <Card title="图片编辑 API" icon="image" href="/api-capabilities/nano-banana-image/image-edit">
    上传图片 + 编辑指令生成新图片，带交互式 Playground 在线调试。
  </Card>
</CardGroup>

## 为什么选 API易 的 Nano Banana Pro

**Nano Banana Pro / 2 是 API易 消耗量排名第一的图像模型**——稳定、可靠、速度快。如果你期望跟专业的团队合作，那选 API易 就对了。

针对 Nano Banana Pro 这种谷歌最新旗舰、内容安全管控严格的模型，API易 在**稳定性**、**成本**、**接入体验**三方面做了深度优化：

<CardGroup cols={2}>
  <Card title="官方通道 · 与 Gemini 一致" icon="shield-check">
    完全兼容谷歌官方 Gemini API 格式（`/v1beta/models/.../generateContent`），同时支持 OpenAI SDK 模式，请求体、响应字段、错误码与官方一致，迁移零改造。
  </Card>

  <Card title="不限并发 · 企业可放量" icon="infinity">
    无谷歌 AI Studio 的 RPM/RPD 硬限制，企业批量出图、高峰流量都能线性放大，避免被官方配额打断。
  </Card>

  <Card title="官网 31-38% 价格" icon="percent">
    按次 \$0.09/张（官方 4K \$0.24），叠加 [充值加赠活动](/faq/recharge-promotions) 最低可达官方 31.25%——4K 场景最多省 68.75%。
  </Card>

  <Card title="全球零门槛接入" icon="globe">
    **无需海外服务器或代理**，国内机房、家宽网络、海外节点均可直连 `api.apiyi.com`，延迟稳定、免去出海改造。
  </Card>

  <Card title="模型生态齐全" icon="layers">
    同系列覆盖 [Nano Banana 2](/api-capabilities/nano-banana-2-image/overview)（性价比 + Flash 速度）、Nano Banana Pro（极致画质）、Nano Banana 第一代（基础版），按场景自由组合。
  </Card>

  <Card title="专业服务 · 企业陪跑" icon="handshake">
    团队深耕图像生成场景，具备丰富的选型、调优与集成经验，可为企业客户提供从 PoC 到生产上线的完整技术支持。
  </Card>
</CardGroup>

## 调用方式

使用谷歌原生 Gemini API 格式调用：

```
POST /v1beta/models/gemini-3-pro-image-preview:generateContent
```

<Tip>
  * ✅ 支持 4K 高清分辨率（1K / 2K / 4K）
  * ✅ 10 种宽高比自由选择
  * ✅ 业界最佳文字渲染
  * ✅ 支持高级局部编辑
  * 📖 完全兼容谷歌官方 API 格式，参考 `ai.google.dev/gemini-api/docs/image-generation`
</Tip>

### 不支持的功能

<Warning>
  以下谷歌官方功能在 API易 中**不支持**，需要单独计费：

  * **Grounding with Google Search**（谷歌搜索增强）：通过 `tools: [{"google_search": {}}]` 调用
  * **thinkingConfig**（思维模式）：仅 Nano Banana 2 支持，Nano Banana Pro 不支持
  * **Image Search Grounding**（图片搜索增强）：仅 Nano Banana 2 独有

  其他图片生成和编辑能力均正常支持。
</Warning>

## 价格对比

| 模型                          | 定价                | 优势               |
| --------------------------- | ----------------- | ---------------- |
| **Nano Banana Pro** (4K)    | \$0.09/张（约¥0.52）  | 🔥 4K 支持，约官方 38% |
| **Nano Banana Pro** (1K-2K) | \$0.09/张（约¥0.52）  | 🔥 高清出图，约官方 67%  |
| **Nano Banana**             | \$0.025/张（约¥0.15） | ⭐ 快速生成，官方 52%    |
| gpt-image-1                 | 较高                | -                |
| flux-kontext-pro            | \$0.035/张         | 持平               |

<Tip>
  **性价比推荐**：

  * **Nano Banana Pro**：4K 支持，文字渲染最强，定价约官方 38-67%
  * **NanoBananaEnterprise**：企业 HA 通道 1.4 倍率（\$0.126/张），适合高可用需求
  * **Nano Banana**：快速生成（约10秒），官方 52% 价格，适合常规高质量图像生成
</Tip>

## 分组介绍

Nano Banana Pro 在 API易提供两个分组，可在后台「令牌设置」中切换：

| 分组                          | 倍率   | 适用场景                                  |
| --------------------------- | ---- | ------------------------------------- |
| `Default` 默认分组              | 1.0x | 基础通道，按次 \$0.09/张；默认推荐                 |
| `NanoBananaEnterprise` 企业分组 | 1.4x | 兜底通道，按次 \$0.126/张，默认紧张/超时高发时手动切换，稳定优先 |

**1.4x 倍率怎么来的？** 1.4x 后仍约等于谷歌官方 5 折水平，远低于官网原价。这是面向更高并发需求、应对意外风控时的兜底方案，为企业客户提供高可用性保障。默认分组紧张时，把令牌切到 `NanoBananaEnterprise` 即可临时过渡。

**令牌「计费模式」推荐**：选 `按量优先`（Pay-as-you-go Priority）—— 同时兼容 Nano Banana Pro 的按次计费 和 Nano Banana 2 的按量计费，**一把令牌跑全系列**。

<Frame caption="令牌设置：计费模式选「按量优先」，主分组选 Default、兜底分组挂上 NanoBananaEnterprise（1.4x）">
  <img src="https://mintcdn.com/apiyillc/EyWjOyg5fLaMGReJ/images/nano-banana-enterprise-token-setup-20260506.png?fit=max&auto=format&n=EyWjOyg5fLaMGReJ&q=85&s=cf85cd8ddaaa541ebbd970a52a98c68f" alt="令牌创建界面：计费模式『按量优先』兼容 NB Pro 按次 + NB2 按量；主分组 Default + 兜底分组 NanoBananaEnterprise（1.4x 兜底通道）" width="1270" height="1052" data-path="images/nano-banana-enterprise-token-setup-20260506.png" />
</Frame>

<Tip>
  **拓展玩法**：如果你的令牌还覆盖其它图像模型（如 GPT-image-2），把更稳的 Default 分组放主位、`NanoBananaEnterprise` 放兜底位即可，主分组 429 会自动回退到企业分组继续出图，无需切换 token。
</Tip>

## 兼容性说明

如果你之前使用过以下模型，可以直接替换模型名称：

### 升级到最新版本

* 任何旧版本 → `gemini-3-pro-image-preview`（🔥 推荐，Nano Banana Pro）
  * 支持 4K 高清出图
  * 文本渲染能力最强
  * 局部编辑功能

### 使用稳定版本

* `gpt-4o-image` → `gemini-2.5-flash-image`
* `sora_image` → `gemini-2.5-flash-image`
* 旧版 Nano Banana → `gemini-2.5-flash-image`

其他参数保持不变，即可无缝切换使用。

## 支持的分辨率与宽高比

### 输出分辨率

Nano Banana Pro 支持 1K、2K、4K 三档分辨率（不含 Nano Banana 2 独有的 512px）：

| 分辨率 | 说明  | 推荐场景      |
| --- | --- | --------- |
| 1K  | 默认  | 社交媒体、网页展示 |
| 2K  | 高清  | 高清显示、打印材料 |
| 4K  | 超高清 | 专业设计、商业海报 |

### 各宽高比的输出尺寸（像素）

下表为 Nano Banana Pro 在 1K / 2K / 4K 三档分辨率下、10 种宽高比对应的实际输出像素尺寸（数据来源：谷歌官方文档）。在请求中通过 `aspect_ratio` 指定宽高比、`image_size`（或 `resolution`）指定分辨率即可：

| 宽高比      | 1K        | 2K        | 4K        |
| -------- | --------- | --------- | --------- |
| **1:1**  | 1024×1024 | 2048×2048 | 4096×4096 |
| **2:3**  | 848×1264  | 1696×2528 | 3392×5056 |
| **3:2**  | 1264×848  | 2528×1696 | 5056×3392 |
| **3:4**  | 896×1200  | 1792×2400 | 3584×4800 |
| **4:3**  | 1200×896  | 2400×1792 | 4800×3584 |
| **4:5**  | 928×1152  | 1856×2304 | 3712×4608 |
| **5:4**  | 1152×928  | 2304×1856 | 4608×3712 |
| **9:16** | 768×1376  | 1536×2752 | 3072×5504 |
| **16:9** | 1376×768  | 2752×1536 | 5504×3072 |
| **21:9** | 1584×672  | 3168×1344 | 6336×2688 |

<Info>
  需要 `1:4`、`4:1`、`1:8`、`8:1` 这类超长/超宽比例，或 512px 低分辨率档位时，请使用 [Nano Banana 2](/api-capabilities/nano-banana-2-image/overview)（支持 14 种宽高比 + 512px）。
</Info>

## API 错误处理指南

Nano Banana Pro 有严格的内容安全管控，可能在多个层级拒绝不合规请求。

<CardGroup cols={3}>
  <Card title="candidatesTokenCount" icon="shield-check">
    **最高优先级**

    值为 0 时，内容在审核阶段被拒绝，未生成任何候选内容。
  </Card>

  <Card title="finishReason" icon="flag">
    **次要优先级**

    值非 `STOP`（如 `PROHIBITED_CONTENT`、`SAFETY`）时，表示生成过程中被拒绝。
  </Card>

  <Card title="API 文本响应" icon="message">
    **拒绝说明**

    API 返回拒绝说明文本而非图片数据时，应将这些说明展示给用户。
  </Card>
</CardGroup>

## FAQ

<AccordionGroup>
  <Accordion title="应该选择 Nano Banana 2 还是 Pro？">
    **追求性价比**推荐 **Nano Banana 2** (`gemini-3.1-flash-image-preview`)：

    * Pro 级画质 + Flash 级速度
    * 按量计费低至 \$0.025/张
    * 支持 14 种宽高比（比 Pro 多 4 种）
    * 独有：思维模式、图片搜索 Grounding

    **追求极致画质**选 **Nano Banana Pro** (`gemini-3-pro-image-preview`)：

    * 最高保真度
    * 定价 \$0.09/次

    详情参考 [Nano Banana 2 文档](/api-capabilities/nano-banana-2-image/overview)。
  </Accordion>

  <Accordion title="应该选择 Pro 版本还是前代版本？">
    **新项目推荐：Nano Banana Pro** (`gemini-3-pro-image-preview`)

    ✅ **Pro 版优势**：

    * 支持 4K 超高清分辨率
    * 业界最佳文本渲染质量
    * 高级局部编辑功能
    * 定价仅约官方 38-67%

    ⚡ **前代版本** (`gemini-2.5-flash-image`) 适合：

    * 预算敏感场景（约\$0.025/张 vs \$0.09/张）
    * 需要快速生成（10s vs 20s）
    * 现有项目迁移
  </Accordion>

  <Accordion title="如何从其他图像模型切换到 Nano Banana？">
    只需将模型名称从 `gpt-4o-image` 或 `sora_image` 更改为 `gemini-3-pro-image-preview`（推荐 Pro）或 `gemini-2.5-flash-image`（前代），其他参数保持不变。
  </Accordion>

  <Accordion title="生成的图片是什么格式？">
    模型返回 base64 编码的图片数据，通常为 PNG 或 JPEG 格式。代码会自动检测格式并保存为对应的文件类型。
  </Accordion>

  <Accordion title="支持图片编辑功能吗？">
    是的，Nano Banana Pro 支持图片生成和图片编辑。请查看 [图片编辑 API 参考](/api-capabilities/nano-banana-image/image-edit)。
  </Accordion>

  <Accordion title="报错 connection reset by peer / write_response_body_failed（500）是什么原因？">
    完整报错形如：

    ```text theme={null}
    [&{{write tcp ip:port->ip:port: write: connection reset by peer Unknown error shell_api_error  write_response_body_failed} 500 }]
    ```

    这种错误**往往是上传的图片体积过大，请求体超限把连接压崩了**。请按以下最佳实践处理：

    * **控制图片张数**：保持在官方规则内（每个提示最多 14 张图），不要堆图。
    * **控制单图体积**：每张图尽量不要超过 5MB——官方单图上限为 7MB，且 base64 编码后体积还会膨胀约 1/3，原图请留足余量。
    * **前端先压缩再上传**：在前端（或服务端中转层）压缩后再提交给接口，常见做法是限制最长边、转 JPEG/WebP 并控制质量参数。
    * **改用 URL 传图**：Gemini 原生格式支持 `fileData.fileUri` 直接传图片 URL，可避开 base64 请求体过大的问题，详见 [Nano Banana 开发指南](/api-capabilities/nano-banana-dev-guide)。
  </Accordion>
</AccordionGroup>

## 相关文档

* [Nano Banana 2 图片生成](/api-capabilities/nano-banana-2-image/overview)
* [Nano Banana 定价说明](/api-capabilities/nano-banana-pricing)
* [其他图像生成模型](/api-capabilities/gpt-image-1)
* [API 使用手册](/api-manual)
