Grsai   GPT  接口文档
节点信息
Host(海外)
https://grsaiapi.com
Host(国内直连)
https://grsai.dakka.com.cn
使用方式Host+接口，例如:
https://grsai.dakka.com.cn/v1/draw/completions

图片生成
POST
/v1/draw/completions
API地址
复制
/v1/draw/completions
请求方式
POST
响应方式
stream 或 回调接口
请求头 Headers
复制
{
  "Content-Type": "application/json",
  "Authorization": "Bearer apikey"
}
请求参数 (JSON)
复制
{
  "model": "gpt-image-2",
  "prompt": "描述您想要生成的图像内容的提示词",
  "aspectRatio": "1024x1024",
  "urls": [
    "https://example.com/example1.png",
    "https://example.com/example2.png"
  ],
  "webHook": "https://example.com/callback",
  "shutProgress": false
}
参数说明
model（必填）
类型: string
示例: "gpt-image-2"
描述:
支持模型:
gpt-image-2
gpt-image-2-vip
prompt（必填）
类型: string
示例: "一只可爱的猫咪在草地上玩耍"
描述:
提示词
aspectRatio（选填）
类型: string
示例: "1024x1024"
描述:
分辨率参考新文档：
https://qmy27nhsd9.apifox.cn/452409160e0
新文档中的像素值通用
quality（选填）
类型: string
示例: "auto"
描述:
质量: "auto"
"low"
"medium"
"high"
urls（选填）
类型: string[]
示例: ["https://example.com/image1.jpg", "https://example.com/image2.jpg"]
描述:
参考图片的URL，支持多张图片，支持base64
webHook（选填）
类型: string
示例: "https://your-webhook-url.com/callback"
描述:
进度与结果的回调链接
接口默认以Stream流式响应进行回复
如果填了webHook，进度与结果则以Post请求回调地址的方式进行回复
请求头: Content-Type: application/json
-------
如果不使用回调，而使用轮询result接口方式获取结果，需要接口立即返回一个id
则webHook参数填"-1"，那么会立即返回一个id
shutProgress（选填）
类型: boolean
示例: false
描述:
关闭进度回复，直接回复最终结果,建议搭配webHook使用
默认false
webHook结果
(请求后该结果会返回一个id，用于对应回调数据)
(使用流式响应请跳过该步骤)
复制
{
  "code": 0,
  "msg": "success",
  "data": {
    "id": "id"
  }
}
webHook结果参数说明
(使用流式响应请跳过该步骤)
code
类型: number
示例: 0
描述:
状态码：0为成功
msg
类型: string
示例: "success"
描述:
状态信息
data
类型: object
示例: {}
描述:
数据
data.id
类型: object
示例: "xxxxxx"
描述:
程序任务id，对应回调数据
响应参数 (JSON)
(流式响应与webHook响应的参数)
复制
{
  "id": "xxxxx",
  "progress": 100,
  "results": [
    {
      "url": "https://example.com/example.png"
    }
  ],
  "status": "succeeded",
  "failure_reason": "",
  "error": ""
}
响应参数说明
id
类型: string
示例: "fb3b7d12-e7f3-4eda-b253-327a415a65b1"
描述:
Id (webHook回调可以用该id来对应数据)
url
类型: string
示例: "https://example.com/generated-image.jpg"
描述:
(旧参数，不会废弃，默认为results中第一个结果的url)
结果图片的URL（有效期为2小时）
progress
类型: number
示例: 100
描述:
任务进度,0~100
results
类型: object[]
描述:
图片生成结果
url: 图片链接（有效期为2小时）
status
类型: string
示例: "succeeded"
描述:
任务状态
"running": 进行中
"succeeded": 成功
"failed": 失败
failure_reason
类型: string
示例: "error"
描述:
失败原因
"output_moderation": 输出违规
"input_moderation": 输入违规
"error": 其他错误
------
当生成失败时，会返还积分
提示：当触发"error"时，可尝试重新提交任务来确保系统稳定性。
error
类型: string
示例: "Invalid input parameters"
描述:
失败详细信息
获取结果接口
POST
/v1/draw/result
另外提供一个接口用于单独获取结果的接口
(如有单独获取结果的需求，可以使用该接口)
复制
/v1/draw/result
Method
POST
请求参数
复制
{
  "id": "xxxxx"
}
响应结果
复制
{
  "code": 0,
  "data": {
    "id": "xxx",
    "progress": 100,
    "status": "succeeded",
    "failure_reason": "",
    "error": "",
    "results": [
      {
        "url": "https://example.com/example.png"
      }
    ]
  },
  "msg": "success"
}
响应参数说明
code
类型: number
示例: 0
描述:
状态码：0成功, -22任务不存在
msg
类型: string
示例: "success"
描述:
状态信息
data
类型: object
描述:
绘画结果，请参考上方的绘画结果的数据格式