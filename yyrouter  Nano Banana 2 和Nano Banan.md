yyrouter  Nano Banana 2 和Nano Banana PRO 接口文档

Gemini 原生生图协议
需要使用 Gemini 原生 generateContent 格式时，可选择当前密钥实际可见的图片模型。常见模型 ID 包括：

gemini-3-pro-image-preview
gemini-3.1-flash-image-preview
这些名称可能随上游预览版本变化，调用前仍应以 /v1/models 为准。将模型 ID 放入路径，并使用 x-goog-api-key 认证：

curl "https://dmit.yyrouter.cc" \
  -H "x-goog-api-key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [
      {
        "parts": [
          {"text": "一张雨夜霓虹街道上的复古机器人海报，3:2 横版构图"}
        ]
      }
    ],
    "generationConfig": {
      "responseModalities": ["TEXT", "IMAGE"],
      "imageConfig": {
        "aspectRatio": "3:2"
      }
    }
  }'
复制
响应的 candidates[].content.parts[] 可能同时包含文字和图片。图片通常位于 inlineData.data，并带有 inlineData.mimeType；对 data 进行 Base64 解码后，按对应 MIME 类型保存文件。客户端解析时不要假设图片一定是第一个 part。

