APIYI   Nano Banana 2 接口文档
> ## Documentation Index
> Fetch the complete documentation index at: https://docs.apiyi.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Nano Banana 2 生图/编辑

> 谷歌最新图像生成模型 Nano Banana 2 (gemini-3.1-flash-image-preview)，Pro级画质、Flash级速度，支持4K输出、14种宽高比、图像搜索Grounding，按次 $0.055/次，按量低至 $0.025/张。

## 概述

**Nano Banana 2**（代号）是谷歌于 2026 年 2 月 26 日发布的最新图像生成模型，模型 ID 为 `gemini-3.1-flash-image-preview`。它以 **Pro 级画质 + Flash 级速度和成本** 重新定义了图像生成的性价比，是 Nano Banana 系列的最新旗舰。

<Note>
  **🔥 2026年2月26日发布**：Nano Banana 2 上线！Pro 级画质、Flash 级速度，支持按量计费（低至官网 36%），512px 低至 \$0.025/张！支持 4K 输出、14 种宽高比、图像搜索 Grounding 等独家特性。
</Note>

<Note>
  **🆕 2026年5月29日更新（去掉 `-preview`）**：谷歌更新了官方文档，推出去掉 `-preview` 的正式模型名 **`gemini-3.1-flash-image`**，API易已同步上线支持。

  * **原模型名仍可用**：`gemini-3.1-flash-image-preview` 继续正常调用，**价格不变**，现有代码无需改动。
  * **两个名字都能跑**：可按需选用新名 `gemini-3.1-flash-image` 或原 `-preview` 名。

  话说在前面：正式版相比 preview 版在效果表现、安全审核机制等方面是否存在差异，谷歌官方暂未明确说明，欢迎大家在实际使用中一起测试反馈。
</Note>

<Info>
  图片 API 全部为**同步调用**：没有异步任务 ID，客户端断开连接结果即丢失、但请求仍会计费。请为本模型设置足够大的 timeout，详见 [图片 API 调用须知与最佳实践](/api-capabilities/image-api-best-practices)。
</Info>

<CardGroup cols={2}>
  <Card title="文生图 API" icon="wand-sparkles" href="/api-capabilities/nano-banana-2-image/text-to-image">
    输入文本提示词生成图片，带交互式 Playground 在线调试。
  </Card>

  <Card title="图片编辑 API" icon="image" href="/api-capabilities/nano-banana-2-image/image-edit">
    上传图片 + 编辑指令生成新图片，带交互式 Playground 在线调试。
  </Card>
</CardGroup>

## 为什么选 API易 的 Nano Banana 2

**Nano Banana Pro / 2 是 API易 消耗量排名第一的图像模型**——稳定、可靠、速度快。如果你期望跟专业的团队合作，那选 API易 就对了。

针对 Nano Banana 2 这种谷歌官方刚发布、产能仍紧张的新模型，API易 在**稳定性**、**成本**、**接入体验**三方面做了深度优化：

<CardGroup cols={2}>
  <Card title="官方通道 · 与 Gemini 一致" icon="shield-check">
    完全兼容谷歌官方 Gemini API 格式（`/v1beta/models/.../generateContent`），同时支持 OpenAI SDK 模式，请求体、响应字段、错误码与官方一致，迁移零改造。
  </Card>

  <Card title="不限并发 · 企业可放量" icon="infinity">
    无谷歌 AI Studio 的 RPM/RPD 硬限制，企业批量出图、高峰流量都能线性放大，避免被官方配额打断。
  </Card>

  <Card title="官网 28-36% 价格" icon="percent">
    按次 \$0.055/张（官方 \$0.151）、按量 512px 低至 \$0.025/张（官方 \$0.045），叠加 [充值加赠活动](/faq/recharge-promotions) 最低可达官方 30.3%。
  </Card>

  <Card title="全球零门槛接入" icon="globe">
    **无需海外服务器或代理**，国内机房、家宽网络、海外节点均可直连 `api.apiyi.com`，延迟稳定、免去出海改造。
  </Card>

  <Card title="模型生态齐全" icon="layers">
    同系列覆盖 [Nano Banana Pro](/api-capabilities/nano-banana-image/overview)（极致画质）、Nano Banana 2（性价比）、Nano Banana 第一代（基础版），按场景自由组合。
  </Card>

  <Card title="专业服务 · 企业陪跑" icon="handshake">
    团队深耕图像生成场景，具备丰富的选型、调优与集成经验，可为企业客户提供从 PoC 到生产上线的完整技术支持。
  </Card>
</CardGroup>

## 核心特性

<CardGroup cols={2}>
  <Card title="Pro 级画质" icon="sparkles">
    生动光影、丰富纹理、锐利细节，画质媲美 Nano Banana Pro，速度却快得多
  </Card>

  <Card title="4K 超清输出" icon="expand">
    支持 512px、1K、2K、4K 四档分辨率，最高 4096×4096
  </Card>

  <Card title="14 种宽高比" icon="maximize">
    新增 1:4、4:1、1:8、8:1，共支持 14 种宽高比，覆盖更多场景
  </Card>

  <Card title="图像搜索 Grounding" icon="search">
    Nano Banana 2 独家功能，可从 Google 图片搜索拉取视觉上下文
  </Card>
</CardGroup>

<CardGroup cols={2}>
  <Card title="精准文字渲染" icon="type">
    图片内文字清晰可读，支持多语言文本渲染，适合海报、营销物料
  </Card>

  <Card title="多轮编辑对话" icon="message-circle">
    支持多轮对话式图像编辑，逐步精调画面效果
  </Card>

  <Card title="思维模式" icon="brain">
    可配置 minimal 或 high 思维级别，处理复杂提示词更精准
  </Card>

  <Card title="主体一致性" icon="users">
    最多保持 5 个角色的相貌一致性，14 个参考物体的高保真度
  </Card>
</CardGroup>

## 版本对比

| 特性             | **Nano Banana 2**                | Nano Banana Pro              | Nano Banana              |
| -------------- | -------------------------------- | ---------------------------- | ------------------------ |
| 模型 ID          | `gemini-3.1-flash-image-preview` | `gemini-3-pro-image-preview` | `gemini-2.5-flash-image` |
| 画质             | ⭐⭐⭐⭐⭐ Pro 级                      | ⭐⭐⭐⭐⭐ 最高                     | ⭐⭐⭐⭐ 优秀                  |
| 速度             | 🚀 最快                            | 🐢 较慢                        | ⚡ 快速                     |
| 最高分辨率          | 4K                               | 4K                           | 1K                       |
| 宽高比数量          | 14 种                             | 10 种                         | 10 种                     |
| 图像搜索 Grounding | ✅ 独家                             | ❌                            | ❌                        |
| API易定价         | **\$0.055/次（按次）**                | \$0.09/次                     | \$0.02/次                 |
| 状态             | Preview                          | Preview                      | GA                       |

<Tip>
  **选择建议**：

  * 🔥 **追求性价比** → Nano Banana 2（按量计费低至 \$0.025/张，Pro 级画质 + Flash 级速度）
  * 🎨 **追求极致画质** → Nano Banana Pro（\$0.09/次，最高保真度）
  * ⚡ **追求最低成本** → Nano Banana（\$0.02/次，快速稳定）
</Tip>

## 模型定价

<Info>
  **计费模式选择**：Nano Banana 2 支持两种计费方式，通过创建令牌时的「Billing model」设置选择：

  * 选择 **Pay-as-you-go**（按量计费）或 **Pay-as-you-go Priority**（按量优先）→ 按量计费
  * 选择 **Pay-per-request**（按次计费）或 **Pay-per-request Priority**（按次优先）→ 按次计费（与 Nano Banana Pro 相同）
  * ⚠️ **请勿选择 Hybrid billing（混合计费）**
</Info>

### 按次计费

| 模型                                                 | API易定价        | 谷歌官方 4K 定价     | 折扣             |
| -------------------------------------------------- | ------------- | -------------- | -------------- |
| **Nano Banana 2** `gemini-3.1-flash-image-preview` | **\$0.055/次** | \$0.151/次      | **🔥 约 3.6 折** |
| Nano Banana Pro `gemini-3-pro-image-preview`       | \$0.09/次      | \$0.151/次      | **约 6 折**      |
| Nano Banana `gemini-2.5-flash-image`               | \$0.020/次     | \$0.039/次（仅1K） | 约 5 折          |

<Info>
  Nano Banana Pro 另提供 `NanoBananaEnterprise` 企业 HA 通道（1.4 倍费率，即 \$0.126/次），适合对可用性有更高要求的场景。
</Info>

### 按量计费（Nano Banana 2 专属）

| 计费项目            | Google 官方             | API易            | 官网折扣    |
| --------------- | --------------------- | --------------- | ------- |
| Input           | \$0.50/M tokens       | \$0.18/M tokens | **36%** |
| Output（图片和文本统一） | 图片 \$60/M, 文本 \$1.5/M | \$21.6/M tokens | **36%** |

### 按量计费价格预估

| 分辨率   | Google 官方 | API易          | Fal AI |
| ----- | --------- | ------------- | ------ |
| 512px | \$0.045   | **\~\$0.025** | \$0.06 |
| 1K    | \$0.067   | **\~\$0.035** | \$0.08 |
| 2K    | \$0.101   | **\~\$0.045** | \$0.12 |
| 4K    | \$0.151   | **\~\$0.07**  | \$0.16 |

<Tip>
  **💰 按量计费更省钱！** 使用按量计费，512px 低至 \$0.025/张，仅为官方 36%！低分辨率场景下比按次计费（\$0.055/次）更实惠。4K 场景按量计费约 \$0.07/张，仍远低于谷歌官方 \$0.151/次。结合充值加赠活动，实际成本更低。
</Tip>

## 分组介绍

Nano Banana 2 在 API易提供两个分组，可在后台「令牌设置」中切换：

| 分组                          | 倍率   | 适用场景                     |
| --------------------------- | ---- | ------------------------ |
| `Default` 默认分组              | 1.0x | 基础通道，与定价表一致；默认推荐         |
| `NanoBananaEnterprise` 企业分组 | 1.4x | 兜底通道，默认紧张/超时高发时手动切换，稳定优先 |

**1.4x 倍率怎么来的？** 1.4x 后仍约等于谷歌官方 5 折水平，远低于官网原价。这是面向更高并发需求、应对意外风控时的兜底方案，为企业客户提供高可用性保障。默认分组紧张时，把令牌切到 `NanoBananaEnterprise` 即可临时过渡。

**令牌「计费模式」推荐**：选 `按量优先`（Pay-as-you-go Priority）—— 同时兼容 Nano Banana 2 的按量计费 和 Nano Banana Pro 的按次计费，**一把令牌跑全系列**。

<Frame caption="令牌设置：计费模式选「按量优先」，主分组选 Default、兜底分组挂上 NanoBananaEnterprise（1.4x）">
  <img src="https://mintcdn.com/apiyillc/EyWjOyg5fLaMGReJ/images/nano-banana-enterprise-token-setup-20260506.png?fit=max&auto=format&n=EyWjOyg5fLaMGReJ&q=85&s=cf85cd8ddaaa541ebbd970a52a98c68f" alt="令牌创建界面：计费模式『按量优先』兼容 NB2 按量 + NB Pro 按次；主分组 Default + 兜底分组 NanoBananaEnterprise（1.4x 兜底通道）" width="1270" height="1052" data-path="images/nano-banana-enterprise-token-setup-20260506.png" />
</Frame>

<Tip>
  **拓展玩法**：如果你的令牌还覆盖其它图像模型（如 GPT-image-2），把更稳的 Default 分组放主位、`NanoBananaEnterprise` 放兜底位即可，主分组 429 会自动回退到企业分组继续出图，无需切换 token。
</Tip>

## 支持的分辨率与宽高比

### 输出分辨率

| 分辨率   | 说明   | 推荐场景      |
| ----- | ---- | --------- |
| 512px | 低分辨率 | 缩略图、快速预览  |
| 1K    | 默认   | 社交媒体、网页展示 |
| 2K    | 高清   | 高清显示、打印材料 |
| 4K    | 超高清  | 专业设计、商业海报 |

### 支持的宽高比（14 种）

`1:1`、`1:4`、`4:1`、`1:8`、`8:1`、`2:3`、`3:2`、`3:4`、`4:3`、`4:5`、`5:4`、`9:16`、`16:9`、`21:9`

### 各宽高比的输出尺寸（像素）

下表为 Nano Banana 2 在 512px / 1K / 2K / 4K 四档分辨率下、14 种宽高比对应的实际输出像素尺寸（数据来源：谷歌官方文档）。在请求中通过 `aspect_ratio` 指定宽高比、`image_size`（或 `resolution`）指定分辨率即可：

| 宽高比      | 512px    | 1K        | 2K        | 4K         |
| -------- | -------- | --------- | --------- | ---------- |
| **1:1**  | 512×512  | 1024×1024 | 2048×2048 | 4096×4096  |
| **1:4**  | 256×1024 | 512×2048  | 1024×4096 | 2048×8192  |
| **1:8**  | 192×1536 | 384×3072  | 768×6144  | 1536×12288 |
| **2:3**  | 424×632  | 848×1264  | 1696×2528 | 3392×5056  |
| **3:2**  | 632×424  | 1264×848  | 2528×1696 | 5056×3392  |
| **3:4**  | 448×600  | 896×1200  | 1792×2400 | 3584×4800  |
| **4:1**  | 1024×256 | 2048×512  | 4096×1024 | 8192×2048  |
| **4:3**  | 600×448  | 1200×896  | 2400×1792 | 4800×3584  |
| **4:5**  | 464×576  | 928×1152  | 1856×2304 | 3712×4608  |
| **5:4**  | 576×464  | 1152×928  | 2304×1856 | 4608×3712  |
| **8:1**  | 1536×192 | 3072×384  | 6144×768  | 12288×1536 |
| **9:16** | 384×688  | 768×1376  | 1536×2752 | 3072×5504  |
| **16:9** | 688×384  | 1376×768  | 2752×1536 | 5504×3072  |
| **21:9** | 792×168  | 1584×672  | 3168×1344 | 6336×2688  |

<Info>
  相比 Nano Banana Pro 的 10 种宽高比，Nano Banana 2 新增了 `1:4`、`4:1`、`1:8`、`8:1` 四种超长/超宽比例，适合长图、信息图等特殊场景；并独有 512px 低分辨率档位，适合缩略图与快速预览。
</Info>

## 常见问题

<AccordionGroup>
  <Accordion title="Nano Banana 2 和 Nano Banana Pro 有什么区别？">
    **Nano Banana 2** (`gemini-3.1-flash-image-preview`) 基于 Gemini 3.1 Flash，**Nano Banana Pro** (`gemini-3-pro-image-preview`) 基于 Gemini 3 Pro。主要区别：

    * ✅ **速度**：Nano Banana 2 更快（Flash 级速度）
    * ✅ **价格**：Nano Banana 2 按量计费更便宜（低至 \$0.025 vs \$0.09）
    * ✅ **宽高比**：Nano Banana 2 支持 14 种（多 4 种）
    * ✅ **图像搜索 Grounding**：Nano Banana 2 独家
    * ⚠️ **极致画质**：Nano Banana Pro 仍略优
  </Accordion>

  <Accordion title="我应该从 Nano Banana Pro 切换到 Nano Banana 2 吗？">
    **推荐切换**！Nano Banana 2 以更低的价格提供了接近 Pro 级别的画质，速度还更快。除非你对画质有极致要求，否则 Nano Banana 2 是更好的选择。

    只需将模型名称从 `gemini-3-pro-image-preview` 改为 `gemini-3.1-flash-image-preview` 即可。
  </Accordion>

  <Accordion title="模型名该用 gemini-3.1-flash-image-preview 还是带 -4k 后缀的版本？">
    **代码 / API 调用，建议统一用不带 `-4k` 后缀的通用模型名 `gemini-3.1-flash-image-preview`，而不是 `gemini-3.1-flash-image-preview-4k`。**

    * **官方命名不带 `-4k`**：谷歌官方的模型名就是 `gemini-3.1-flash-image-preview`。这也是我们投入最多资源持续维护的通用通道，稳定性和兼容性最有保障。
    * **`-4k` 的由来**：`gemini-3.1-flash-image-preview-4k` 当初是为 Chatbox 等对话式客户端的「对话出图」场景准备的配置——在聊天界面里直接对话生成图片时使用。
    * **代码 + Gemini 原生格式更推荐通用名**：如果你是通过代码调用、走 Gemini 原生格式（`/v1beta/models/.../generateContent`），用常规模型名 `gemini-3.1-flash-image-preview` 会更稳定。

    需要 4K 分辨率输出时，无需依赖 `-4k` 模型名——直接在请求参数里指定 4K 分辨率即可（见上方「支持的分辨率与宽高比」）。
  </Accordion>

  <Accordion title="什么是图像搜索 Grounding？">
    图像搜索 Grounding 是 Nano Banana 2 的独家功能。它可以从 Google 图片搜索拉取视觉上下文，生成更贴合现实世界的图像。例如，当你要求生成某个真实地标的图片时，它能参考搜索结果来提高准确性。
  </Accordion>

  <Accordion title="思维模式有什么用？">
    思维模式（Thinking Mode）让模型在生成图像前进行推理分析，对复杂提示词的理解更准确。设置为 `high` 时效果最好，但会稍微增加生成时间。适合需要精确构图、包含文字、或涉及复杂场景的生成任务。
  </Accordion>

  <Accordion title="生成一张图片需要多长时间？">
    生成时间取决于分辨率和是否启用思维模式：

    * **1K 分辨率**：约 5-10 秒
    * **2K 分辨率**：约 10-15 秒
    * **4K 分辨率**：约 15-25 秒
    * 启用高级思维模式会额外增加几秒

    建议设置较长的超时时间（至少 360 秒）以应对偶发延迟和高峰拥塞。
  </Accordion>

  <Accordion title="有并发限制吗？API 是串行处理吗？需要 20 个用户同时调用怎么办？">
    **API 不限制并发，也不是串行处理。** 你可以放心地自行并发调用，请求之间不用排队、不会互相阻塞——20 个用户同时调用直接发起 20 个并发请求即可，无需额外申请配额或做限流。

    与谷歌 AI Studio 不同，API易 的通道没有 RPM/RPD 硬限制，企业批量出图、高峰流量都能线性放大。

    **真正要注意的是 `timeout` 超时时间**：图像生成（尤其 4K 或高峰拥塞时）单次耗时可能较长，**建议把客户端超时设到 360 秒**，避免请求还在正常处理就被本地超时掐断。

    <Tip>
      如果偶发 429（并发过高被限流），可把令牌的兜底分组挂上 `NanoBananaEnterprise`（见上方「分组介绍」），主分组打满时自动回退，进一步提升高并发下的成功率。
    </Tip>
  </Accordion>

  <Accordion title="支持哪些输入图片格式？">
    支持 `image/png` 和 `image/jpeg` 格式。可以通过 base64 编码或 Files API 上传。
  </Accordion>

  <Accordion title="输出图片有水印吗？">
    所有输出图片都带有 SynthID 隐形数字水印（Google 的 AI 生成内容标识技术），肉眼不可见，不影响使用。
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

* [Nano Banana Pro 图片生成](/api-capabilities/nano-banana-image) - 上一代旗舰版
* [Nano Banana 图片编辑](/api-capabilities/nano-banana-image-edit) - 图片编辑功能
* [图像生成对比测试](https://imagen.apiyi.com/)
* [API 使用手册](/api-manual)

<Info>
  Nano Banana 2 目前处于 Preview 状态，功能和定价可能会有调整。建议关注文档更新获取最新信息。
</Info>
