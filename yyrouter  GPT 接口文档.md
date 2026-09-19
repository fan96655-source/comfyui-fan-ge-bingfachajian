yyrouter  GPT 接口文档

文生图
向 /v1/images/generations 发送 JSON 请求：

curl "https://dmit.yyrouter.cc" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "一只纸雕风格的白鲸游过深蓝色星空，柔和侧光，细节丰富",
    "size": "1024x1024",
    "quality": "medium",
    "n": 1,
    "response_format": "url",
    "output_format": "png"
  }'
复制
成功响应遵循 Images API 的 data 数组结构。根据模型、响应格式和站点存储配置，图片可能通过 url 或 b64_json 返回：

{
  "created": 1784092923,
  "data": [
    {
      "url": "https://example.com/generated-image.png",
      "revised_prompt": "..."
    }
  ]
}
复制
如果返回 b64_json，需要先进行 Base64 解码再保存。图片链接也可能具有有效期，生产应用应及时下载并保存到自己的对象存储。

通过 Responses API 调用生图工具
已经使用 OpenAI Responses API 的客户端，也可以在 /v1/responses 中显式选择 image_generation 工具。文本模型与图片模型都应替换为当前 API Key 在 /v1/models 中可见、且实际支持对应能力的模型：

curl "https://yyrouter.cc/v1/responses" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "YOUR_TEXT_MODEL_ID",
    "input": "生成一张海报风格的城市夜景图",
    "tools": [
      {
        "type": "image_generation",
        "model": "YOUR_IMAGE_MODEL_ID",
        "size": "1024x1024"
      }
    ],
    "tool_choice": {"type": "image_generation"}
  }'
复制
此方式要求当前分组同时支持 Responses 与图片生成。响应可能包含文本、工具调用状态和图片结果等多种输出项，客户端应按 type 遍历输出，而不要假定图片固定出现在某个数组下标。只需要图片时，优先使用 Images API，调用和响应结构更直接。

Python SDK
import base64
from pathlib import Path

from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://yyrouter.cc/v1",
)

response = client.images.generate(
    model="gpt-image-2",
    prompt="一座漂浮在云海上的未来城市，清晨，电影感构图",
    size="1024x1024",
    quality="medium",
    n=1,
)

image = response.data[0]
if image.b64_json:
    Path("result.png").write_bytes(base64.b64decode(image.b64_json))
else:
    print(image.url)
复制
不同版本的 SDK 对新增参数支持速度不同。如果 SDK 拒绝某个网关已支持的字段，可以直接使用 HTTP 请求。

图片编辑
图片编辑使用 /v1/images/edits，推荐通过 multipart/form-data 上传原图：

curl "https://yyrouter.cc/v1/images/edits" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "model=gpt-image-2" \
  -F "prompt=保留主体轮廓，把背景改成雨夜霓虹街道" \
  -F "image=@input.png" \
  -F "size=1024x1024" \
  -F "quality=medium" \
  -F "response_format=url" \
  -F "output_format=png"
复制
需要上传多张参考图时，可以重复传递 image 字段。是否支持多图、蒙版、透明背景或高保真输入取决于所选模型；不支持的能力通常会由上游返回参数错误。

兼容路径与尺寸分档
推荐新客户端使用带 /v1 的标准路径。为兼容部分旧 SDK，本站也注册了不带 /v1 的等价别名：

POST /v1/images/generations       = POST /images/generations
POST /v1/images/edits             = POST /images/edits
POST /v1/images/generations/async = POST /images/generations/async
POST /v1/images/edits/async       = POST /images/edits/async
GET  /v1/images/tasks/{task_id}   = GET  /images/tasks/{task_id}
复制
size 应优先填写模型接受的 宽x高 分辨率。1K、2K、4K 是站内计费分档，不代表所有上游模型都接受这些字符串作为请求参数。当前计费归类按最长边计算：

最长边不超过 1024：1K，例如 1024x768、1024x1024。
最长边大于 1024 且不超过 2048：2K，例如 1280x768、1536x1024、2048x2048。
最长边大于 2048：4K，例如 2560x1600、3840x2160。
当输出和请求尺寸均为空、为 auto 或无法识别时，回退为 2K。
若上游响应能识别出实际输出尺寸，计费优先采用输出尺寸；一次返回多张不同尺寸的图片时，按其中最高分档记录。只有拿不到有效输出尺寸时才使用请求中的 size。因此，账单分档可能与请求值不同，这是上游实际输出尺寸覆盖请求尺寸的结果。

常用参数
model：图片模型 ID。建议显式传入，并以 /v1/models 的结果为准。
prompt：图片描述或编辑指令。
n：期望生成的图片数量，默认为 1；上限由模型与分组策略决定。
size：输出尺寸，例如 1024x1024、1536x1024 或 1024x1536。
quality：输出质量，例如 auto、low、medium 或 high。
response_format：通常为 url 或 b64_json。
output_format：常见值为 png、jpeg 或 webp。
background、style、input_fidelity、mask：模型特定选项，使用前请确认模型能力。
stream：设为 true 时使用 SSE 返回进度或最终图片事件。
模型可能只支持其中一部分参数。遇到参数错误时，先保留 model、prompt、size 和 n 做最小请求，再逐项增加高级选项。

流式结果
长耗时模型可以设置 stream: true，客户端按 Server-Sent Events 读取响应：

curl -N "https://yyrouter.cc/v1/images/generations" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "山谷中的玻璃温室，薄雾和晨光",
    "size": "1024x1024",
    "stream": true,
    "response_format": "url"
  }'
复制
客户端应逐个解析 data: 块，并以完成事件中的 url 或 b64_json 作为最终结果。反向代理应关闭响应缓冲，避免事件在请求结束后才一次性到达。

异步任务
如果生成时间可能超过 CDN 或反向代理超时，可使用异步接口：

POST /v1/images/generations/async
POST /v1/images/edits/async
GET  /v1/images/tasks/{task_id}
复制
提交请求的正文与对应同步接口基本一致，但不能同时使用 stream: true。服务接受任务后返回 202 Accepted、task_id、poll_url 和建议轮询间隔：

curl "https://yyrouter.cc/v1/images/generations/async" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "冬季暴风雪中的灯塔",
    "size": "1536x1024"
  }'
复制
随后使用提交任务时的同一个 API Key 查询：

curl "https://yyrouter.cc/v1/images/tasks/YOUR_TASK_ID" \
  -H "Authorization: Bearer YOUR_API_KEY"
复制
任务状态为 completed 时，最终 Images API 响应位于 result。异步任务由站点管理员选择对象存储或本地存储；两种模式都只在 Redis 中保存图片 URL，不保存 b64_json。本地模式沿用 GATEWAY_IMAGE_MIRROR_* 的目录、大小限制、访问路径和保留周期；多实例部署需要共享图片目录并保持静态访问配置一致。如果功能未启用，提交接口会返回 404，此时请使用同步接口或联系管理员