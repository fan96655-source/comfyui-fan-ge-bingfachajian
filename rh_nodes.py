"""A standalone ComfyUI node for the documented RunningHub image APIs.

This module deliberately has no dependency on other custom nodes.  It accepts
ComfyUI IMAGE tensors, uploads reference images to RunningHub when needed, and
returns the generated image as a normal ComfyUI IMAGE tensor.
"""

from __future__ import annotations

import base64
import ipaddress
import io
import json
import logging
import re
import secrets
import socket
import threading
import time
import uuid
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

import numpy as np
import torch
from PIL import Image as PILImage


NODE_NAME = "RHDirectStrongModelFan"
NODE_DISPLAY_NAME = "🚀RH直连（兼容旧版）"

RH_DIRECT_CHANNEL = "RH直连"
OFFICIAL_CHANNEL = "官方线路"
THIRD_PARTY_CHANNEL = "第三方线路"

RH_BASE_URL = "https://www.runninghub.ai/openapi/v2"
RH_UPLOAD_URL = f"{RH_BASE_URL}/media/upload/binary"
RH_QUERY_URL = f"{RH_BASE_URL}/query"
RH_POLL_INTERVAL_SECONDS = 2.0
# A remote service queue should never make ComfyUI appear frozen indefinitely.
# These caps cover a normal image job while still returning a useful task ID
# when RunningHub is congested.
RH_POLL_TIMEOUT_SECONDS = 6 * 60
RH_TOTAL_TIMEOUT_SECONDS = 8 * 60
RH_UPLOAD_TIMEOUT_SECONDS = 45
RH_SUBMIT_TIMEOUT_SECONDS = 45
RH_QUERY_TIMEOUT_SECONDS = 30
HTTP_TIMEOUT_SECONDS = 90
RESULT_IMAGE_DOWNLOAD_TIMEOUT_SECONDS = 45
HTTP_READ_CHUNK_BYTES = 1024 * 1024
MAX_IMAGE_DOWNLOAD_BYTES = 64 * 1024 * 1024
MAX_IMAGE_PIXELS = 268_435_456

LOGGER = logging.getLogger(__name__)

MODEL_OPTIONS = (
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
    "gpt-image-2",
)

# RunningHub limits each individual reference image, not the whole request.
# Keep this in one place so the encoder and the final upload guard agree.
RH_REFERENCE_IMAGE_LIMITS = {
    "gemini-3.1-flash-image-preview": 30 * 1024 * 1024,
    "gemini-3-pro-image-preview": 10 * 1024 * 1024,
    "gpt-image-2": 10 * 1024 * 1024,
}

RH_MODEL_ENDPOINTS = {
    "gemini-3.1-flash-image-preview": (
        f"{RH_BASE_URL}/rhart-image-n-g31-flash/image-to-image"
    ),
    "gemini-3-pro-image-preview": f"{RH_BASE_URL}/rhart-image-n-pro/edit",
    "gpt-image-2": f"{RH_BASE_URL}/rhart-image-g-2-official/image-to-image",
}

PROMPT_STRENGTH_INSTRUCTIONS = {
    "严格": "严格遵循提示词中明确指定的主体、构图、风格与限制，不自行添加未要求的内容。",
    "平衡": "以提示词为主要方向，同时允许为画面完整性做适度且合理的补充。",
    "创意": "保留提示词的核心意图，并允许更有创造性的视觉诠释和细节设计。",
}

REFERENCE_STRENGTH_INSTRUCTIONS = {
    "高保留": "将参考图作为高优先级依据，尽量保留其主体特征、构图、色彩和可识别细节。",
    "中保留": "参考图提供主要视觉方向；在保留关键特征的同时，可按提示词调整其他部分。",
    "低保留": "参考图只作为灵感来源，优先根据提示词进行新的视觉创作。",
}

SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "token",
    "secret",
    "password",
    "bearer",
    "credential",
)


class RHNodeError(RuntimeError):
    """Raised for a user-facing request, response, or decoding problem."""


class _NoRedirectHandler(HTTPRedirectHandler):
    """Prevent a result URL from silently hopping to a different host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def _is_http_url(value: str) -> bool:
    """Return whether *value* is an absolute http(s) URL."""

    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _redact_text(value: Any) -> str:
    """Redact credentials that may be embedded in an unstructured error body."""

    text = str(value)
    text = re.sub(
        r"(?i)(\b(?:api[_ -]?key|authorization|access[_ -]?token|token|secret|password|credential)\b\s*[:=]\s*[\"']?)(?:bearer\s+)?[^\s,;\"'<>]+",
        r"\1***",
        text,
    )
    return re.sub(r"(?i)(\bbearer\s+)[a-z0-9._~+/=-]+", r"\1***", text)


def _redact(value: Any) -> Any:
    """Recursively remove common credential fields before returning response JSON."""

    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower().replace("-", "_")
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                clean[key_text] = "***"
            else:
                clean[key_text] = _redact(item)
        return clean
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _safe_error_text(value: Any, limit: int = 700) -> str:
    """Produce a short, redacted message suitable for a ComfyUI error."""

    if isinstance(value, (Mapping, list, tuple)):
        text = json.dumps(_redact(value), ensure_ascii=False)
    else:
        text = str(value)
    text = _redact_text(text).replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def _remaining_rh_timeout(deadline: float, maximum: float, action: str) -> float:
    """Return a bounded request timeout without exceeding RH's total budget."""

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RHNodeError(
            f"RH 请求总等待超过 {RH_TOTAL_TIMEOUT_SECONDS} 秒；{action}未完成。"
        )
    return max(1.0, min(maximum, remaining))


def _http_bytes(
    request: Request,
    *,
    action: str,
    timeout: float = HTTP_TIMEOUT_SECONDS,
    max_bytes: int | None = None,
    block_redirects: bool = False,
    socket_timeout: float | None = None,
) -> bytes:
    """Send a request with a total wall-clock deadline and safe size limit."""

    deadline = time.monotonic() + timeout
    effective_socket_timeout = max(1.0, min(socket_timeout or timeout, timeout))
    try:
        opener = build_opener(_NoRedirectHandler) if block_redirects else None
        open_request = opener.open if opener is not None else urlopen
        with open_request(request, timeout=effective_socket_timeout) as response:
            chunks: list[bytes] = []
            total_bytes = 0
            while True:
                # response.read() may keep receiving a few bytes forever.  A
                # wall-clock deadline prevents that slow stream from freezing
                # ComfyUI long after an RH task has already reported SUCCESS.
                if time.monotonic() >= deadline:
                    raise TimeoutError
                chunk = response.read(HTTP_READ_CHUNK_BYTES)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if max_bytes is not None and total_bytes > max_bytes:
                    raise RHNodeError(
                        f"{action}失败：图片文件超过 {max_bytes // (1024 * 1024)} MB 限制。"
                    )
                chunks.append(chunk)
        return b"".join(chunks)
    except HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        if detail:
            raise RHNodeError(
                f"{action}失败（HTTP {exc.code}）：{_safe_error_text(detail)}"
            ) from None
        raise RHNodeError(f"{action}失败（HTTP {exc.code}）。") from None
    except URLError as exc:
        reason = _safe_error_text(getattr(exc, "reason", "网络不可用"))
        raise RHNodeError(f"{action}失败：{reason}") from None
    except TimeoutError:
        raise RHNodeError(f"{action}超时。") from None


def _ensure_public_image_url(value: str) -> None:
    """Reject image URLs that resolve to localhost or private/internal addresses."""

    parsed = urlparse(value.strip())
    host = parsed.hostname
    if not host or parsed.username or parsed.password:
        raise RHNodeError("接口返回的图片 URL 不安全。")
    hostname = host.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise RHNodeError("接口返回的图片 URL 指向本机，已拒绝下载。")

    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        try:
            resolved = socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise RHNodeError("无法解析接口返回的图片 URL 主机名。") from exc
        addresses = {ipaddress.ip_address(item[4][0]) for item in resolved}

    if not addresses or any(not address.is_global for address in addresses):
        raise RHNodeError("接口返回的图片 URL 指向非公网地址，已拒绝下载。")


def _post_json(
    url: str,
    payload: Mapping[str, Any],
    headers: Mapping[str, str],
    *,
    action: str,
    timeout: float = HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """POST a JSON object and require a JSON-object response."""

    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **dict(headers)}
    request = Request(url, data=body, headers=request_headers, method="POST")
    raw = _http_bytes(request, action=action, timeout=timeout)
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RHNodeError(f"{action}返回了无法解析的 JSON。") from exc
    if not isinstance(decoded, dict):
        raise RHNodeError(f"{action}返回格式错误：预期 JSON 对象。")
    return decoded


def _build_multipart(
    fields: Sequence[tuple[str, str]],
    files: Sequence[tuple[str, str, str, bytes]],
) -> tuple[bytes, str]:
    """Build a compact multipart/form-data payload using only the stdlib."""

    boundary = f"----ComfyRH{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    marker = f"--{boundary}\r\n".encode("ascii")

    for name, value in fields:
        chunks.extend(
            (
                marker,
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            )
        )
    for name, filename, content_type, data in files:
        safe_filename = filename.replace('"', "_")
        chunks.extend(
            (
                marker,
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{safe_filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("ascii"),
                data,
                b"\r\n",
            )
        )
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), boundary


def _post_multipart(
    url: str,
    fields: Sequence[tuple[str, str]],
    files: Sequence[tuple[str, str, str, bytes]],
    headers: Mapping[str, str],
    *,
    action: str,
    timeout: float = HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """POST multipart data and require a JSON-object response."""

    body, boundary = _build_multipart(fields, files)
    request_headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        **dict(headers),
    }
    request = Request(url, data=body, headers=request_headers, method="POST")
    raw = _http_bytes(request, action=action, timeout=timeout)
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RHNodeError(f"{action}返回了无法解析的 JSON。") from exc
    if not isinstance(decoded, dict):
        raise RHNodeError(f"{action}返回格式错误：预期 JSON 对象。")
    return decoded


def _iter_input_frames(images: Iterable[Any]) -> list[torch.Tensor]:
    """Flatten connected IMAGE sockets in socket order without inventing images."""

    frames: list[torch.Tensor] = []
    for position, image in enumerate(images, start=1):
        if image is None:
            continue
        if not isinstance(image, torch.Tensor):
            raise RHNodeError(f"参考图{position}不是有效的 ComfyUI IMAGE 张量。")
        tensor = image.detach().cpu()
        if tensor.ndim == 3:
            tensor = tensor.unsqueeze(0)
        if tensor.ndim != 4 or tensor.shape[-1] not in {3, 4}:
            raise RHNodeError(
                f"参考图{position}的形状无效；需要 [B,H,W,3] 或 [B,H,W,4]。"
            )
        for frame in tensor:
            frames.append(frame)
    if len(frames) > 10:
        raise RHNodeError(
            f"已连接的参考图批次共 {len(frames)} 张，RH 接口最多支持 10 张。"
        )
    return frames


def _encode_png(image: PILImage.Image) -> bytes:
    """Encode an RGB Pillow image as an optimized PNG."""

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _tensor_to_png(frame: torch.Tensor, *, max_bytes: int | None = None) -> bytes:
    """Convert one ComfyUI image frame to PNG, shrinking only when required.

    RH limits each uploaded reference image to 10 or 30 MiB depending on the
    model.  A lossless full-resolution PNG of a high-detail image can exceed
    that limit even when the source image looks ordinary.  Resize just enough
    to fit before uploading, while leaving smaller images byte-for-byte at
    their original encoded resolution.
    """

    array = frame.detach().cpu().float().numpy()
    array = np.nan_to_num(array, nan=0.0, posinf=1.0, neginf=0.0)
    if array.max(initial=0.0) <= 1.0:
        array = np.clip(array, 0.0, 1.0) * 255.0
    else:
        array = np.clip(array, 0.0, 255.0)
    pixels = np.rint(array).astype(np.uint8)
    image = PILImage.fromarray(pixels, mode="RGBA" if pixels.shape[-1] == 4 else "RGB")
    if image.mode != "RGB":
        image = image.convert("RGB")
    encoded = _encode_png(image)
    if max_bytes is None or len(encoded) <= max_bytes:
        return encoded

    # Leave a little room below the provider's limit.  PNG compression varies
    # with image content, so calculate the next dimensions from the actual
    # encoded size and retry a few times rather than assuming bytes/pixel.
    target_bytes = max(1, int(max_bytes * 0.92))
    resampling = getattr(PILImage, "Resampling", PILImage).LANCZOS
    resized = image
    for _ in range(10):
        scale = min(0.90, (target_bytes / len(encoded)) ** 0.5)
        next_size = (
            max(1, int(resized.width * scale)),
            max(1, int(resized.height * scale)),
        )
        if next_size == resized.size:
            break
        resized = resized.resize(next_size, resampling)
        encoded = _encode_png(resized)
        if len(encoded) <= max_bytes:
            return encoded
    return encoded


def _png_data_uri(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _decode_data_uri(value: str) -> bytes:
    try:
        header, encoded = value.split(",", 1)
    except ValueError as exc:
        raise RHNodeError("图片 data URI 格式无效。") from exc
    if ";base64" not in header.lower():
        raise RHNodeError("图片 data URI 必须使用 base64 编码。")
    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise RHNodeError("图片 data URI 的 base64 内容无效。") from exc


def _image_from_value(value: Any) -> PILImage.Image:
    """Decode an image URL, data URI, raw base64 value, or byte string."""

    if isinstance(value, bytes):
        data = value
    elif isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("data:image/"):
            data = _decode_data_uri(stripped)
        elif _is_http_url(stripped):
            _ensure_public_image_url(stripped)
            image_host = urlparse(stripped).netloc
            LOGGER.info("开始下载生成图片：%s（最长 %s 秒）", image_host, RESULT_IMAGE_DOWNLOAD_TIMEOUT_SECONDS)
            request = Request(stripped, headers={"User-Agent": "ComfyUI-RH-APL/1.0"})
            data = _http_bytes(
                request,
                action="下载生成图片",
                timeout=RESULT_IMAGE_DOWNLOAD_TIMEOUT_SECONDS,
                max_bytes=MAX_IMAGE_DOWNLOAD_BYTES,
                block_redirects=True,
                socket_timeout=10,
            )
            LOGGER.info("生成图片下载完成：%s（%.2f MiB）", image_host, len(data) / (1024 * 1024))
        else:
            try:
                data = base64.b64decode(stripped, validate=True)
            except ValueError as exc:
                raise RHNodeError("接口返回的图片不是有效 URL、data URI 或 base64。") from exc
    else:
        raise RHNodeError("接口返回的图片字段类型无效。")

    try:
        with PILImage.open(io.BytesIO(data)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise RHNodeError("接口返回的图片像素过大，已拒绝解码。")
            return image.convert("RGB").copy()
    except RHNodeError:
        raise
    except Exception as exc:
        raise RHNodeError("接口返回的内容无法解码为图片。") from exc


def _image_values_from_response(payload: Any) -> list[Any]:
    """Find common image result fields in a JSON response without scanning prompts."""

    image_keys = {
        "url",
        "imageurl",
        "image_url",
        "b64json",
        "b64_json",
        "imagebase64",
        "image_base64",
        "base64",
    }
    container_keys = {"results", "images", "data", "output", "outputs", "result", "artifacts"}
    found: list[Any] = []

    def visit(value: Any, allow_plain_string: bool = False) -> None:
        if isinstance(value, Mapping):
            for raw_key, item in value.items():
                key = str(raw_key).lower().replace("-", "_")
                compact_key = key.replace("_", "")
                if key in image_keys or compact_key in image_keys:
                    visit(item, allow_plain_string=True)
                elif key in container_keys or compact_key in container_keys:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item, allow_plain_string=allow_plain_string)
        elif allow_plain_string and isinstance(value, (str, bytes)):
            found.append(value)

    visit(payload)
    # Keep ordering while preventing duplicate URL downloads.
    unique: list[Any] = []
    seen: set[str] = set()
    for item in found:
        key = item if isinstance(item, str) else repr(item)
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return unique


def _http_image_urls(values: Iterable[Any]) -> list[str]:
    return [item.strip() for item in values if isinstance(item, str) and _is_http_url(item)]


def _images_to_tensor(values: Sequence[Any]) -> tuple[torch.Tensor, int, int]:
    """Decode returned images, batching equal-sized results when possible."""

    decoded: list[torch.Tensor] = []
    failures: list[str] = []
    for value in values:
        try:
            image = _image_from_value(value)
            pixels = np.asarray(image, dtype=np.float32) / 255.0
            decoded.append(torch.from_numpy(pixels).unsqueeze(0))
        except RHNodeError as exc:
            failures.append(str(exc))

    if not decoded:
        suffix = f"（最后一个错误：{failures[-1]}）" if failures else ""
        raise RHNodeError(f"接口响应中未找到可解码的图片{suffix}")

    first_shape = tuple(decoded[0].shape[1:])
    compatible = [image for image in decoded if tuple(image.shape[1:]) == first_shape]
    output = torch.cat(compatible, dim=0).float()
    return output, len(decoded), len(compatible)


def _controlled_prompt(prompt: str, prompt_strength: str, ref_strength: str) -> str:
    """Map the two visual controls into explicit model instructions."""

    return (
        f"{prompt.strip()}\n\n"
        "【生成控制】\n"
        f"提示词循环强度：{prompt_strength}。{PROMPT_STRENGTH_INSTRUCTIONS[prompt_strength]}\n"
        f"参考图保留强度：{ref_strength}。{REFERENCE_STRENGTH_INSTRUCTIONS[ref_strength]}"
    )


class RHDirectStrongModelFan:
    """🚀 RH direct multi-reference image generation node."""

    CATEGORY = "APL/兼容旧版"
    DESCRIPTION = "兼容旧工作流的 RH 标准模型节点；多平台路线请使用“🪄 帆 · 万象生图”。"
    FUNCTION = "generate"
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = (
        "📤 输出区 · 图像",
        "├── 🔗 图片链接",
        "├── 🆔 任务ID",
        "└── 📋 响应信息",
    )
    OUTPUT_TOOLTIPS = (
        "生成后的 ComfyUI IMAGE，可直接连接到预览、保存或后续处理节点。",
        "服务端返回的首张图片链接；没有链接时为空字符串。",
        "服务端任务 ID；同步接口可能为空字符串。",
        "去除密钥后的结构化服务端响应，便于排查问题。",
    )
    OUTPUT_NODE = False

    def __init__(self) -> None:
        self._seed_lock = threading.Lock()
        self._last_seed: int | None = None
        self._last_seed_request: tuple[str, int] | None = None

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        image_inputs = {
            f"image{index}": (
                "IMAGE",
                {
                    "display_name": f"🖼️ 参考图{index}",
                    "tooltip": "可选；未连接时不会上传。批次中的每一帧均按顺序计入，最多共 10 张。",
                },
            )
            for index in range(1, 11)
        }
        return {
            "required": {
                "api_channel": (
                    [RH_DIRECT_CHANNEL, OFFICIAL_CHANNEL, THIRD_PARTY_CHANNEL],
                    {
                        "default": RH_DIRECT_CHANNEL,
                        "display_name": "🌐 API线路",
                        "tooltip": "RH直连使用本目录附带的 RunningHub 标准模型接口文档。",
                    },
                ),
                "api_key": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "password": True,
                        "display_name": "🔑 API密钥",
                        "tooltip": "必填，仅用于请求头；节点不会记录或输出该值。",
                    },
                ),
                "custom_api_url": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "display_name": "🔗 自定义API地址",
                        "placeholder": "仅第三方线路填写，例如 https://example.com/generate",
                        "tooltip": "仅在“第三方线路”使用；RH直连和官方线路会忽略此字段。",
                    },
                ),
                "prompt": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "dynamicPrompts": True,
                        "display_name": "📝 提示词",
                        "placeholder": "📝 提示词\n请输入生成提示词，可结合 10 张参考图进行描述",
                    },
                ),
                "prompt_strength": (
                    ["严格", "平衡", "创意"],
                    {"default": "严格", "display_name": "🎯 prompt强度"},
                ),
                "ref_strength": (
                    ["高保留", "中保留", "低保留"],
                    {"default": "高保留", "display_name": "🧷 参考图强度"},
                ),
                "model": (
                    list(MODEL_OPTIONS),
                    {
                        "default": "gemini-3.1-flash-image-preview",
                        "display_name": "⚙️ 参数控制区 · 🤖 模型版本",
                    },
                ),
                "aspect_ratio": (
                    ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9"],
                    {"default": "2:3", "display_name": "├── 📐 宽高比"},
                ),
                "resolution": (
                    ["1K", "2K", "4K"],
                    {"default": "2K", "display_name": "├── 🖼️ 分辨率"},
                ),
                "seed": (
                    "INT",
                    {
                        "default": 583,
                        "min": 0,
                        "max": 0xFFFFFFFF,
                        "control_after_generate": False,
                        "display_name": "├── 🎲 seed",
                    },
                ),
                "randomize": (
                    ["fixed", "randomize", "increment", "decrement"],
                    {"default": "fixed", "display_name": "└── 🔀 randomize"},
                ),
            },
            "optional": image_inputs,
        }

    @classmethod
    def IS_CHANGED(cls, seed: int = 583, randomize: str = "fixed", **_: Any) -> bool | float:
        """Force a new execution whenever the requested seed policy is dynamic."""

        try:
            is_zero_seed = int(seed) == 0
        except (TypeError, ValueError):
            is_zero_seed = True
        if is_zero_seed or randomize in {"randomize", "increment", "decrement"}:
            # NaN is intentionally never equal to a cached fingerprint.
            return float("nan")
        return False

    @staticmethod
    def _validate_inputs(
        api_channel: str,
        api_key: str,
        custom_api_url: str,
        prompt: str,
        model: str,
        prompt_strength: str,
        ref_strength: str,
        aspect_ratio: str,
        resolution: str,
        randomize: str,
    ) -> None:
        if api_channel not in {RH_DIRECT_CHANNEL, OFFICIAL_CHANNEL, THIRD_PARTY_CHANNEL}:
            raise RHNodeError("API线路无效。")
        if not isinstance(api_key, str) or not api_key.strip():
            raise RHNodeError("API密钥不能为空。")
        if not isinstance(prompt, str) or not prompt.strip():
            raise RHNodeError("提示词不能为空。")
        if model not in MODEL_OPTIONS:
            raise RHNodeError("模型版本无效。")
        if prompt_strength not in PROMPT_STRENGTH_INSTRUCTIONS:
            raise RHNodeError("提示词循环强度无效。")
        if ref_strength not in REFERENCE_STRENGTH_INSTRUCTIONS:
            raise RHNodeError("参考图保留强度无效。")
        if aspect_ratio not in {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9"}:
            raise RHNodeError("宽高比无效。")
        if resolution not in {"1K", "2K", "4K"}:
            raise RHNodeError("图片分辨率无效。")
        if randomize not in {"fixed", "randomize", "increment", "decrement"}:
            raise RHNodeError("randomize 参数无效。")
        if api_channel == THIRD_PARTY_CHANNEL:
            if not isinstance(custom_api_url, str) or not custom_api_url.strip():
                raise RHNodeError("选择“第三方线路”时必须填写自定义API地址。")
            if not _is_http_url(custom_api_url):
                raise RHNodeError("自定义API地址必须是有效的 http 或 https URL。")

    def _effective_seed(self, seed: int, randomize: str) -> int:
        """Apply the requested seed policy; zero always means a fresh random seed."""

        max_seed = 0xFFFFFFFF
        base = int(seed) & max_seed
        with self._seed_lock:
            request_key = (randomize, base)
            previous = self._last_seed if self._last_seed_request == request_key else None
            if base == 0 or randomize == "randomize":
                chosen = secrets.randbelow(max_seed) + 1
            elif randomize == "increment":
                chosen = ((previous if previous is not None else base) + 1) & max_seed
                chosen = chosen or 1
            elif randomize == "decrement":
                chosen = ((previous if previous is not None else base) - 1) & max_seed
                chosen = chosen or max_seed
            else:
                chosen = base
            self._last_seed = chosen
            self._last_seed_request = request_key
            return chosen

    @staticmethod
    def _rh_upload_reference(
        api_key: str,
        image_bytes: bytes,
        index: int,
        *,
        timeout: float = RH_UPLOAD_TIMEOUT_SECONDS,
    ) -> str:
        response = _post_multipart(
            RH_UPLOAD_URL,
            fields=(),
            files=[("file", f"reference_{index}.png", "image/png", image_bytes)],
            headers={"Authorization": f"Bearer {api_key.strip()}"},
            action=f"上传参考图{index}",
            timeout=timeout,
        )
        download_url = response.get("data", {}).get("download_url") if isinstance(response.get("data"), Mapping) else None
        if not isinstance(download_url, str) or not _is_http_url(download_url):
            message = response.get("message") or response.get("errorMessage") or "未返回下载链接"
            raise RHNodeError(f"上传参考图{index}失败：{_safe_error_text(message)}")
        return download_url

    @staticmethod
    def _rh_wait_for_result(
        api_key: str,
        initial: Mapping[str, Any],
        *,
        deadline: float | None = None,
    ) -> tuple[str, dict[str, Any]]:
        task_id = initial.get("taskId") or initial.get("task_id")
        if not isinstance(task_id, (str, int)) or not str(task_id):
            message = initial.get("errorMessage") or initial.get("message") or "未返回任务ID"
            raise RHNodeError(f"RH 提交任务失败：{_safe_error_text(message)}")
        task_id_text = str(task_id)
        result = dict(initial)
        started_at = time.monotonic()
        poll_deadline = min(
            started_at + RH_POLL_TIMEOUT_SECONDS,
            deadline if deadline is not None else float("inf"),
        )
        last_logged_status: str | None = None

        while True:
            now = time.monotonic()
            status = str(result.get("status", "")).upper() or "UNKNOWN"
            elapsed_seconds = int(now - started_at)
            if status != last_logged_status:
                LOGGER.info(
                    "RH task %s status=%s (elapsed=%ss)",
                    task_id_text,
                    status,
                    elapsed_seconds,
                )
                last_logged_status = status
            if status == "SUCCESS":
                return task_id_text, result
            if status in {"FAILED", "CANCELLED", "CANCELED", "ERROR"}:
                message = result.get("errorMessage") or result.get("failedReason") or "任务失败"
                raise RHNodeError(f"RH 任务 {task_id_text} 失败：{_safe_error_text(message)}")
            if now >= poll_deadline:
                raise RHNodeError(
                    f"RH 任务 {task_id_text} 持续 {status} 超过 {elapsed_seconds} 秒；"
                    "服务端仍在排队或运行，请稍后重试、减少参考图，或更换线路/模型。"
                )
            time.sleep(min(RH_POLL_INTERVAL_SECONDS, poll_deadline - now))
            remaining = poll_deadline - time.monotonic()
            if remaining <= 0:
                continue
            result = _post_json(
                RH_QUERY_URL,
                {"taskId": task_id_text},
                {"Authorization": f"Bearer {api_key.strip()}"},
                action="查询 RH 任务",
                timeout=max(1.0, min(RH_QUERY_TIMEOUT_SECONDS, remaining)),
            )

    def _generate_via_rh(
        self,
        api_key: str,
        model: str,
        image_bytes: Sequence[bytes],
        prompt: str,
        aspect_ratio: str,
        resolution: str,
    ) -> tuple[list[Any], str, dict[str, Any]]:
        if not image_bytes:
            raise RHNodeError("RH直连接口要求至少连接一张参考图。")

        deadline = time.monotonic() + RH_TOTAL_TIMEOUT_SECONDS
        size_limit = RH_REFERENCE_IMAGE_LIMITS[model]
        uploaded_urls: list[str] = []
        for index, image_data in enumerate(image_bytes, start=1):
            if len(image_data) > size_limit:
                raise RHNodeError(
                    f"参考图{index}自动压缩后仍超过当前模型的上传大小限制"
                    f"（{size_limit // (1024 * 1024)} MB）；请降低输入图分辨率后重试。"
                )
            uploaded_urls.append(
                self._rh_upload_reference(
                    api_key,
                    image_data,
                    index,
                    timeout=_remaining_rh_timeout(
                        deadline,
                        RH_UPLOAD_TIMEOUT_SECONDS,
                        f"上传参考图{index}",
                    ),
                )
            )

        payload: dict[str, Any] = {
            "imageUrls": uploaded_urls,
            "prompt": prompt,
            "resolution": resolution.lower(),
        }
        if aspect_ratio != "auto":
            payload["aspectRatio"] = aspect_ratio
        # RH's GPT Image 2 documentation requires quality, while the supplied
        # node framework intentionally has no quality widget.
        if model == "gpt-image-2":
            payload["quality"] = "medium"

        submitted = _post_json(
            RH_MODEL_ENDPOINTS[model],
            payload,
            {"Authorization": f"Bearer {api_key.strip()}"},
            action="提交 RH 生成任务",
            timeout=_remaining_rh_timeout(
                deadline,
                RH_SUBMIT_TIMEOUT_SECONDS,
                "提交 RH 生成任务",
            ),
        )
        task_id, completed = self._rh_wait_for_result(
            api_key,
            submitted,
            deadline=deadline,
        )
        image_values = _image_values_from_response(completed)
        if not image_values:
            raise RHNodeError(f"RH 任务 {task_id} 成功但没有返回图片链接。")
        LOGGER.info("RH task %s 成功，开始处理 %s 张结果图。", task_id, len(image_values))
        return image_values, task_id, completed

    def _generate_via_official(
        self,
        api_key: str,
        model: str,
        image_bytes: Sequence[bytes],
        prompt: str,
        aspect_ratio: str,
        resolution: str,
    ) -> tuple[list[Any], str, dict[str, Any]]:
        """Use vendor-native formats for the two official provider families."""

        if model.startswith("gemini-"):
            parts: list[dict[str, Any]] = [{"text": prompt}]
            parts.extend(
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": base64.b64encode(image).decode("ascii"),
                    }
                }
                for image in image_bytes
            )
            generation_config: dict[str, Any] = {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"imageSize": resolution},
            }
            if aspect_ratio != "auto":
                generation_config["imageConfig"]["aspectRatio"] = aspect_ratio
            response = _post_json(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent",
                {"contents": [{"role": "user", "parts": parts}], "generationConfig": generation_config},
                {"x-goog-api-key": api_key.strip()},
                action="调用 Gemini 官方接口",
            )
            values = _image_values_from_response(response)
            task_id = str(response.get("responseId") or response.get("id") or "")
            if not values:
                # Gemini returns image parts under inlineData, which are not
                # URL fields. Add them explicitly after normal URL extraction.
                for candidate in response.get("candidates", []):
                    if not isinstance(candidate, Mapping):
                        continue
                    content = candidate.get("content", {})
                    for part in content.get("parts", []) if isinstance(content, Mapping) else []:
                        if not isinstance(part, Mapping):
                            continue
                        inline = part.get("inlineData") or part.get("inline_data")
                        if isinstance(inline, Mapping) and isinstance(inline.get("data"), str):
                            values.append(inline["data"])
            if not values:
                raise RHNodeError("Gemini 官方接口未返回可解码的图片。")
            return values, task_id, response

        # OpenAI's image-edit endpoint accepts image files as multipart fields.
        # With no references, the normal generation endpoint is used instead.
        if image_bytes:
            endpoint = "https://api.openai.com/v1/images/edits"
            files = [
                ("image[]", f"reference_{index}.png", "image/png", data)
                for index, data in enumerate(image_bytes, start=1)
            ]
        else:
            endpoint = "https://api.openai.com/v1/images/generations"
            files = []
        fields = [
            ("model", model),
            ("prompt", prompt),
            ("n", "1"),
            ("quality", "medium"),
        ]
        if files:
            response = _post_multipart(
                endpoint,
                fields=fields,
                files=files,
                headers={"Authorization": f"Bearer {api_key.strip()}"},
                action="调用 OpenAI 官方接口",
            )
        else:
            response = _post_json(
                endpoint,
                {"model": model, "prompt": prompt, "n": 1, "quality": "medium"},
                {"Authorization": f"Bearer {api_key.strip()}"},
                action="调用 OpenAI 官方接口",
            )
        values = _image_values_from_response(response)
        task_id = str(response.get("id") or "")
        if not values:
            raise RHNodeError("OpenAI 官方接口未返回可解码的图片。")
        return values, task_id, response

    @staticmethod
    def _generate_via_third_party(
        api_key: str,
        custom_api_url: str,
        model: str,
        image_bytes: Sequence[bytes],
        prompt: str,
        aspect_ratio: str,
        resolution: str,
        controls: Mapping[str, Any],
    ) -> tuple[list[Any], str, dict[str, Any]]:
        """Call a documented, portable JSON contract for third-party routes."""

        payload = {
            "model": model,
            "prompt": prompt,
            "reference_images": [_png_data_uri(data) for data in image_bytes],
            "parameters": {
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                **dict(controls),
            },
        }
        response = _post_json(
            custom_api_url.strip(),
            payload,
            {"Authorization": f"Bearer {api_key.strip()}"},
            action="调用第三方接口",
        )
        values = _image_values_from_response(response)
        task_id = str(response.get("task_id") or response.get("taskId") or response.get("id") or "")
        if not values:
            raise RHNodeError(
                "第三方接口未返回可解码图片。它应在 results/images/data 中返回 url 或 b64_json。"
            )
        return values, task_id, response

    def generate(
        self,
        api_channel: str,
        api_key: str,
        custom_api_url: str,
        prompt: str,
        prompt_strength: str,
        ref_strength: str,
        model: str,
        aspect_ratio: str,
        resolution: str,
        seed: int,
        randomize: str,
        image1: Any = None,
        image2: Any = None,
        image3: Any = None,
        image4: Any = None,
        image5: Any = None,
        image6: Any = None,
        image7: Any = None,
        image8: Any = None,
        image9: Any = None,
        image10: Any = None,
    ) -> tuple[torch.Tensor, str, str, str]:
        """Generate an image and return IMAGE, first URL, task id, response JSON."""

        self._validate_inputs(
            api_channel,
            api_key,
            custom_api_url,
            prompt,
            model,
            prompt_strength,
            ref_strength,
            aspect_ratio,
            resolution,
            randomize,
        )
        frames = _iter_input_frames(
            (image1, image2, image3, image4, image5, image6, image7, image8, image9, image10)
        )
        reference_size_limit = (
            RH_REFERENCE_IMAGE_LIMITS[model]
            if api_channel == RH_DIRECT_CHANNEL
            else None
        )
        image_bytes = [
            _tensor_to_png(frame, max_bytes=reference_size_limit)
            for frame in frames
        ]
        effective_seed = self._effective_seed(seed, randomize)
        controlled_prompt = _controlled_prompt(prompt, prompt_strength, ref_strength)
        if api_channel == RH_DIRECT_CHANNEL and len(controlled_prompt) > 20_000:
            raise RHNodeError(
                "提示词加上强度控制指令后超过 RH 接口的 20,000 字符上限，请缩短提示词。"
            )
        controls = {
            "prompt_strength": prompt_strength,
            "ref_strength": ref_strength,
            "seed": int(seed),
            "effective_seed": effective_seed,
            "randomize": randomize,
        }

        if api_channel == RH_DIRECT_CHANNEL:
            image_values, task_id, remote_response = self._generate_via_rh(
                api_key,
                model,
                image_bytes,
                controlled_prompt,
                aspect_ratio,
                resolution,
            )
        elif api_channel == OFFICIAL_CHANNEL:
            image_values, task_id, remote_response = self._generate_via_official(
                api_key,
                model,
                image_bytes,
                controlled_prompt,
                aspect_ratio,
                resolution,
            )
        else:
            image_values, task_id, remote_response = self._generate_via_third_party(
                api_key,
                custom_api_url,
                model,
                image_bytes,
                controlled_prompt,
                aspect_ratio,
                resolution,
                controls,
            )

        try:
            output_tensor, decoded_count, output_batch_size = _images_to_tensor(image_values)
        except RHNodeError as exc:
            if api_channel == RH_DIRECT_CHANNEL:
                raise RHNodeError(
                    f"RH 任务 {task_id} 已成功，但结果图下载或解码失败：{exc}"
                ) from exc
            raise
        if api_channel == RH_DIRECT_CHANNEL:
            LOGGER.info(
                "RH task %s 结果图已解码完成（%s 张，输出批次 %s 张）。",
                task_id,
                decoded_count,
                output_batch_size,
            )
        output_urls = _http_image_urls(image_values)
        response_summary = {
            "task_id": task_id,
            "request": {
                "api_channel": api_channel,
                "model": model,
                "reference_image_count": len(image_bytes),
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "controls": controls,
            },
            "output_urls": output_urls,
            "decoded_image_count": decoded_count,
            "output_batch_size": output_batch_size,
            "remote_response": _redact(remote_response),
        }
        return (
            output_tensor,
            output_urls[0] if output_urls else "",
            task_id,
            json.dumps(response_summary, ensure_ascii=False),
        )


NODE_CLASS_MAPPINGS = {NODE_NAME: RHDirectStrongModelFan}
NODE_DISPLAY_NAME_MAPPINGS = {NODE_NAME: NODE_DISPLAY_NAME}
