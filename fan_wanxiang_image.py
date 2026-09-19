"""🪄 帆 · 万象生图 — independent multi-reference ComfyUI image node.

This module intentionally does not import or alter the package's older nodes.
It accepts up to ten independent IMAGE sockets and exposes the node schema
defined for the APL workflow.
"""

from __future__ import annotations

import base64
import codecs
import io
import json
import logging
import secrets
import ssl
import threading
import time
import uuid
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import numpy as np
import torch
from PIL import Image as PILImage
try:
    import requests
except ImportError:  # pragma: no cover - ComfyUI normally ships requests
    requests = None


LOGGER = logging.getLogger("comfyui.fan_wanxiang_image")


NODE_NAME = "FanWanXiangImage"
NODE_DISPLAY_NAME = "🪄 帆 · 万象生图"

RH_DIRECT = "RH 直连"
APIYI_DIRECT = "APIYI 直连"
YYROUTER_DIRECT = "YYRouter 直连"
THIRD_PARTY = "第三方线路"
CUSTOM = "自定义线路"
GRSAI_DIRECT = "Grsai 直连"
CHANNELS = (RH_DIRECT, GRSAI_DIRECT, APIYI_DIRECT, YYROUTER_DIRECT, THIRD_PARTY, CUSTOM)
MODELS = (
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
    "gpt-image-2",
    "gpt-image-2-vip",
    "gpt-image-2.5",
    "gpt-image-2.5-flare",
    "gpt-image-2.5-sunburst",
)
GRSAI_GPT_MODELS = frozenset(MODELS[2:])
RATIOS = ("auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9")
RESOLUTIONS = ("1K", "2K", "4K")
MAX_REFERENCE_IMAGE_BYTES = 8 * 1024 * 1024
PROMPT_STRENGTH = ("严格", "平衡", "创意")
REFERENCE_STRENGTH = ("高保留", "中保留", "低保留")
RANDOMIZE = ("fixed", "randomize", "increment", "decrement")
PARALLEL_GENERATIONS = tuple(str(value) for value in range(1, 13))

# The reference Grsai node starts as many workers as requested. That can
# duplicate a large multi-reference payload twelve times and overload both
# ComfyUI and the remote gateway. Queue up to twelve outputs, but keep only a
# small, memory-bounded number of remote jobs active at once.
MAX_GRSAI_CONCURRENT_JOBS = 1
GRSAI_CONCURRENT_BODY_BUDGET = 32 * 1024 * 1024
GRSAI_SUBMIT_TIMEOUT = (15, 60)
GRSAI_SUBMIT_DEADLINE = 75.0
GRSAI_POLL_TIMEOUT = (20, 35)
GRSAI_POLL_RETRIES = 6
GRSAI_TASK_TIMEOUT = 900.0
GRSAI_NOT_FOUND_GRACE = 15.0
GRSAI_POLL_INTERVAL = 5.0
GRSAI_GPT_TASK_RETRY_DELAYS = (30.0, 60.0)
TRANSIENT_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
MAX_IMAGE_DOWNLOAD_WORKERS = 4
IMAGE_DOWNLOAD_TIMEOUT = (8, 45)
IMAGE_DOWNLOAD_RETRIES = 2

RH_BASE = "https://www.runninghub.ai/openapi/v2"
RH_UPLOAD = f"{RH_BASE}/media/upload/binary"
RH_QUERY = f"{RH_BASE}/query"
RH_ENDPOINTS = {
    "gemini-3.1-flash-image-preview": f"{RH_BASE}/rhart-image-n-g31-flash/image-to-image",
    "gemini-3-pro-image-preview": f"{RH_BASE}/rhart-image-n-pro/edit",
    "gpt-image-2": f"{RH_BASE}/rhart-image-g-2-official/image-to-image",
}
GRSAI_BASE_URL = "https://grsai.dakka.com.cn"
YYROUTER_BASE_URL = "https://dmit.yyrouter.cc"

# These are the combinations covered by the interface documents shipped with
# this node.  In particular, APIYI's supplied documents describe Gemini
# Nano Banana endpoints; they do not define a gpt-image-2 endpoint.
CHANNEL_MODELS = {
    RH_DIRECT: frozenset(MODELS[:3]),
    GRSAI_DIRECT: frozenset(MODELS),
    APIYI_DIRECT: frozenset({MODELS[0], MODELS[1]}),
    YYROUTER_DIRECT: frozenset(MODELS[:3]),
    THIRD_PARTY: frozenset(MODELS[:3]),
    CUSTOM: frozenset(MODELS[:3]),
}

# A single route adapter is used at the final request boundary.  Keeping the
# profiles explicit prevents a provider's limits or MIME assumptions from
# leaking into another APL route.
APL_ROUTE_PROFILES = {
    # RH uploads images one by one. The model-specific 30/10 MiB limits are
    # selected in _route_profile from the supplied RH documentation.
    RH_DIRECT: {"max_image_bytes": None, "max_request_bytes": None, "allow_webp": False},
    # APIYI documents a 7 MiB hard limit and recommends <= 5 MiB per inline
    # reference because Base64 expands the request. Other inline routes use
    # the same conservative stable profile until their own limits are known.
    GRSAI_DIRECT: {"max_image_bytes": 5 * 1024 * 1024, "max_request_bytes": 8 * 1024 * 1024, "allow_webp": False},
    APIYI_DIRECT: {"max_image_bytes": 5 * 1024 * 1024, "max_request_bytes": 8 * 1024 * 1024, "allow_webp": False},
    YYROUTER_DIRECT: {"max_image_bytes": 5 * 1024 * 1024, "max_request_bytes": 8 * 1024 * 1024, "allow_webp": False},
    THIRD_PARTY: {"max_image_bytes": 5 * 1024 * 1024, "max_request_bytes": 8 * 1024 * 1024, "allow_webp": False},
    CUSTOM: {"max_image_bytes": 5 * 1024 * 1024, "max_request_bytes": 8 * 1024 * 1024, "allow_webp": False},
}


def _route_profile(api_channel: str, model: str) -> Mapping[str, Any]:
    profile = dict(APL_ROUTE_PROFILES[api_channel])
    if api_channel == RH_DIRECT:
        profile["max_image_bytes"] = 30 * 1024 * 1024 if model == "gemini-3.1-flash-image-preview" else 10 * 1024 * 1024
    return profile


def _parallel_generation_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise WanXiangError("🚀 智能并发生成数量无效。") from exc
    if count < 1 or count > 12:
        raise WanXiangError("🚀 智能并发生成数量必须在 1 到 12 之间。")
    return count

PROMPT_RULES = {
    "严格": "严格遵循提示词中明确指定的主体、构图、风格和限制，不添加未要求的内容。",
    "平衡": "以提示词为主要方向，并为画面完整性进行适度、合理的补充。",
    "创意": "保留提示词核心意图，允许更有创造性的视觉诠释与细节设计。",
}
REFERENCE_RULES = {
    "高保留": "将参考图作为高优先级依据，尽量保留主体、构图、色彩和可识别细节。",
    "中保留": "保留参考图的关键视觉特征，同时按提示词调整其他部分。",
    "低保留": "参考图仅作为灵感来源，优先根据提示词进行新的视觉创作。",
}


class WanXiangError(RuntimeError):
    """A concise error message that is safe to show in the ComfyUI UI."""


class WanXiangNetworkError(WanXiangError):
    """A transport failure, distinguished so idempotent polls can retry."""

    def __init__(self, message: str, *, timed_out: bool = False) -> None:
        super().__init__(message)
        self.timed_out = timed_out


class WanXiangHTTPError(WanXiangError):
    """An HTTP failure that keeps its status for safe idempotent retries."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = int(status_code)
        self.retry_after = retry_after


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _safe_url(value: str) -> str:
    parsed = urlparse(value)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _safe_message(value: Any, limit: int = 600) -> str:
    """Never include request headers or credentials in an error shown to users."""
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    for marker in ("api_key", "apikey", "authorization", "bearer", "token", "secret"):
        text = text.replace(marker, "***")
    return text.replace("\r", " ").replace("\n", " ").strip()[:limit]


def _read_timeout(timeout: float | tuple[float, float]) -> float:
    return float(timeout[1] if isinstance(timeout, tuple) else timeout)


def _retry_after_seconds(value: Any) -> float | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(seconds, 30.0))


def _http_error(
    action: str,
    status_code: int,
    detail: Any = "",
    retry_after: Any = None,
) -> WanXiangError:
    if status_code == 413:
        return WanXiangError(
            f"{action}失败（HTTP 413）：请求体总大小超过平台限制；"
            "请减少参考图数量，或改用支持文件 URL 的接口。"
        )
    suffix = f"：{_safe_message(detail)}" if detail else ""
    return WanXiangHTTPError(
        f"{action}失败（HTTP {status_code}）{suffix}",
        status_code=status_code,
        retry_after=_retry_after_seconds(retry_after),
    )


def _http(
    request: Request,
    *,
    action: str,
    timeout: float | tuple[float, float] = 120,
    max_bytes: int = 80 * 1024 * 1024,
) -> bytes:
    if requests is not None:
        try:
            response = requests.request(
                request.get_method(),
                request.full_url,
                data=request.data,
                headers=dict(request.header_items()),
                timeout=timeout,
                verify=True,
            )
            LOGGER.info("APL response: %s HTTP %s (%d bytes)", action, response.status_code, len(response.content))
            if response.status_code >= 400:
                detail = response.text[:600] if response.text else ""
                raise _http_error(
                    action,
                    response.status_code,
                    detail,
                    response.headers.get("Retry-After"),
                )
            data = response.content
            if len(data) > max_bytes:
                raise WanXiangError(f"{action}失败：响应内容过大。")
            return data
        except WanXiangError:
            raise
        except requests.Timeout as exc:
            raise WanXiangNetworkError(
                f"{action}超时（{_safe_message(exc)}）。", timed_out=True
            ) from None
        except requests.RequestException as exc:
            raise WanXiangNetworkError(f"{action}失败：网络不可用（{_safe_message(exc)}）。") from None

    # A few OpenSSL/edge combinations close an idle TLS handshake with EOF.
    # Retry that transport-only failure once with an explicit short-lived
    # connection; request/response errors are never retried.
    attempts = (request, Request(request.full_url, data=request.data, headers={**dict(request.headers), "Connection": "close", "User-Agent": "ComfyUI-FanWanXiang/1.0"}, method=request.get_method()))
    for attempt, current in enumerate(attempts):
        try:
            with urlopen(current, timeout=_read_timeout(timeout), context=ssl.create_default_context()) as response:
                data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise WanXiangError(f"{action}失败：响应内容过大。")
            return data
        except URLError as exc:
            if isinstance(exc, HTTPError):
                try:
                    detail = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    detail = ""
                raise _http_error(
                    action,
                    exc.code,
                    detail,
                    exc.headers.get("Retry-After") if exc.headers else None,
                ) from None
            reason = str(getattr(exc, "reason", exc))
            if attempt == 0 and ("EOF" in reason or "SSL" in reason or "reset" in reason.lower()):
                time.sleep(0.25)
                continue
            raise WanXiangNetworkError(f"{action}失败：网络不可用（{_safe_message(reason)}）。") from None
        except (ssl.SSLError, ConnectionResetError) as exc:
            if attempt == 0:
                time.sleep(0.25)
                continue
            raise WanXiangNetworkError(f"{action}失败：网络不可用（{_safe_message(exc)}）。") from None
        except TimeoutError:
            raise WanXiangNetworkError(f"{action}超时。", timed_out=True) from None
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            raise _http_error(
                action,
                exc.code,
                detail,
                exc.headers.get("Retry-After") if exc.headers else None,
            ) from None
    raise WanXiangNetworkError(f"{action}失败：网络不可用。")


def _decode_json_response(raw: bytes, *, action: str) -> dict[str, Any]:
    """Decode a normal JSON object or the final JSON event of an SSE response."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WanXiangError(f"{action}失败：服务返回内容不是 UTF-8 JSON。") from exc
    try:
        response = json.loads(text)
    except json.JSONDecodeError:
        # Grsai documents a stream response.  Its terminal event is commonly
        # formatted as `data: { ... }`; use the last valid JSON event.
        response = None
        for line in reversed(text.splitlines()):
            if not line.lstrip().startswith("data:"):
                continue
            candidate = line.split(":", 1)[1].strip()
            if not candidate or candidate == "[DONE]":
                continue
            try:
                response = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
        if response is None:
            raise WanXiangError(f"{action}失败：服务没有返回有效 JSON。") from None
    if not isinstance(response, dict):
        raise WanXiangError(f"{action}失败：服务响应格式错误。")
    return response


def _post_json(
    url: str,
    payload: Mapping[str, Any],
    headers: Mapping[str, str],
    *,
    action: str,
    timeout: float | tuple[float, float] = 120,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    LOGGER.info("APL request start: %s POST %s (%d bytes)", action, _safe_url(url), len(body))
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **dict(headers)},
        method="POST",
    )
    started = time.monotonic()
    try:
        return _decode_json_response(_http(request, action=action, timeout=timeout), action=action)
    finally:
        LOGGER.info("APL request finished: %s (%.2fs)", action, time.monotonic() - started)


def _get_json(
    url: str,
    headers: Mapping[str, str],
    *,
    action: str,
    timeout: float | tuple[float, float] = 120,
) -> dict[str, Any]:
    request = Request(url, headers=dict(headers), method="GET")
    started = time.monotonic()
    LOGGER.info("APL request start: %s GET %s", action, _safe_url(url))
    try:
        return _decode_json_response(_http(request, action=action, timeout=timeout), action=action)
    finally:
        LOGGER.info("APL request finished: %s (%.2fs)", action, time.monotonic() - started)


def _grsai_event_ready(payload: Mapping[str, Any]) -> bool:
    """Return as soon as Grsai has supplied an id, result, or terminal error."""
    if payload.get("code") not in (None, 0):
        return True
    data = payload.get("data") if isinstance(payload.get("data"), Mapping) else payload
    if not isinstance(data, Mapping):
        return False
    if data.get("id") or payload.get("id") or data.get("url") or data.get("results"):
        return True
    return str(data.get("status", "")).lower() in {
        "success", "succeeded", "completed", "failed", "error", "cancelled", "canceled"
    }


def _complete_json_mapping(text: str) -> dict[str, Any] | None:
    """Return a complete top-level JSON object while a response is still open."""
    candidate = text.lstrip("\ufeff \t\r\n")
    if not candidate:
        return None
    try:
        value, end = json.JSONDecoder().raw_decode(candidate)
    except json.JSONDecodeError:
        return None
    if candidate[end:].strip() or not isinstance(value, dict):
        return None
    return value


def _json_mapping(value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _post_grsai_submit(
    url: str,
    payload: Mapping[str, Any],
    headers: Mapping[str, str],
) -> dict[str, Any]:
    """Read only until Grsai returns a task id instead of waiting for SSE EOF.

    ``webHook=-1`` (draw) and ``replyType=async`` (GPT) return a task id promptly.
    Some gateways expose that acknowledgement as SSE and leave the connection
    open. Normal ``requests`` response loading waits for EOF, which caused a
    completed remote job to be reported locally as a 120-second ReadTimeout.
    """
    if requests is None:
        raise WanXiangError("Grsai 直连需要 requests 依赖；当前 ComfyUI Python 环境未安装。")

    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    action = "提交 Grsai 生图任务"
    LOGGER.info("APL request start: %s POST %s (%d bytes)", action, _safe_url(url), len(body))
    started = time.monotonic()
    deadline = started + GRSAI_SUBMIT_DEADLINE
    received = bytearray()
    decoder = codecs.getincrementaldecoder("utf-8")()
    all_text = ""
    line_buffer = ""
    sse_data: list[str] = []
    last_event: dict[str, Any] | None = None
    try:
        with requests.request(
            "POST",
            url,
            data=body,
            headers={"Content-Type": "application/json", **dict(headers)},
            timeout=GRSAI_SUBMIT_TIMEOUT,
            verify=True,
            stream=True,
        ) as response:
            if response.status_code >= 400:
                detail = response.text[:600] if response.text else ""
                raise _http_error(
                    action,
                    response.status_code,
                    detail,
                    response.headers.get("Retry-After"),
                )

            # A one-byte read is intentional here: an acknowledgement JSON is
            # tiny, and a larger buffered read can wait for EOF when a broken
            # gateway leaves the connection open after sending the task ID.
            for chunk in response.iter_content(chunk_size=1):
                if not chunk:
                    continue
                received.extend(chunk)
                if len(received) > 2 * 1024 * 1024:
                    raise WanXiangError(f"{action}失败：确认响应内容异常过大。")
                text = decoder.decode(chunk)
                all_text += text
                line_buffer += text

                # A normal JSON response may be complete even if a gateway
                # keeps the HTTP connection open. Parse it before waiting for
                # another chunk or EOF.
                complete = _complete_json_mapping(all_text)
                if complete is not None:
                    LOGGER.info(
                        "APL response: %s HTTP %s (complete JSON acknowledgement)",
                        action,
                        response.status_code,
                    )
                    return complete

                while "\n" in line_buffer:
                    line, line_buffer = line_buffer.split("\n", 1)
                    line = line.rstrip("\r")
                    if line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        value = line.split(":", 1)[1].lstrip()
                        if value and value != "[DONE]":
                            sse_data.append(value)
                            event = _json_mapping(value)
                            if event is not None:
                                last_event = event
                                if _grsai_event_ready(event):
                                    LOGGER.info(
                                        "APL response: %s HTTP %s (early SSE acknowledgement)",
                                        action,
                                        response.status_code,
                                    )
                                    return event
                        continue
                    if not line.strip():
                        if sse_data:
                            event = _json_mapping("\n".join(sse_data))
                            sse_data.clear()
                            if event is not None:
                                last_event = event
                                if _grsai_event_ready(event):
                                    return event
                        continue
                    event = _json_mapping(line.strip())
                    if event is not None:
                        last_event = event
                        if _grsai_event_ready(event):
                            return event

                if time.monotonic() >= deadline:
                    raise WanXiangNetworkError(
                        f"{action}超过 {GRSAI_SUBMIT_DEADLINE:.0f} 秒仍未返回任务ID。",
                        timed_out=True,
                    )

            tail = decoder.decode(b"", final=True)
            all_text += tail
            line_buffer += tail

        if not received:
            raise WanXiangError(f"{action}失败：服务返回空响应。")
        complete = _complete_json_mapping(all_text)
        if complete is not None:
            return complete
        if line_buffer.startswith("data:"):
            value = line_buffer.split(":", 1)[1].strip()
            if value and value != "[DONE]":
                sse_data.append(value)
        if sse_data:
            event = _json_mapping("\n".join(sse_data))
            if event is not None:
                last_event = event
        if last_event is not None:
            return last_event
        return _decode_json_response(bytes(received), action=action)
    except WanXiangError:
        raise
    except requests.Timeout as exc:
        raise WanXiangNetworkError(
            f"{action}超时（{_safe_message(exc)}）。", timed_out=True
        ) from None
    except requests.RequestException as exc:
        raise WanXiangNetworkError(
            f"{action}失败：网络不可用（{_safe_message(exc)}）。"
        ) from None
    finally:
        LOGGER.info("APL request finished: %s (%.2fs)", action, time.monotonic() - started)


def _multipart(
    fields: Sequence[tuple[str, str]], files: Sequence[tuple[str, str, str, bytes]]
) -> tuple[bytes, str]:
    boundary = f"----ComfyWanXiang{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    separator = f"--{boundary}\r\n".encode("ascii")
    for name, value in fields:
        chunks += [separator, f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), value.encode(), b"\r\n"]
    for name, filename, mime, content in files:
        chunks += [
            separator,
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(), content, b"\r\n",
        ]
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), boundary


def _post_multipart(
    url: str, fields: Sequence[tuple[str, str]], files: Sequence[tuple[str, str, str, bytes]],
    headers: Mapping[str, str], *, action: str,
    timeout: float | tuple[float, float] = 120,
) -> dict[str, Any]:
    body, boundary = _multipart(fields, files)
    LOGGER.info("APL request start: %s POST %s (%d bytes)", action, _safe_url(url), len(body))
    request = Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}", **dict(headers)}, method="POST")
    return _decode_json_response(_http(request, action=action, timeout=timeout), action=action)


def _frames(inputs: Iterable[Any]) -> list[torch.Tensor]:
    """Filter null sockets and preserve socket/frame order without padding."""
    result: list[torch.Tensor] = []
    for index, image in enumerate(inputs, 1):
        if image is None:
            continue
        if not isinstance(image, torch.Tensor):
            raise WanXiangError(f"参考图{index}不是有效的 IMAGE。")
        value = image.detach().cpu()
        if value.ndim == 3:
            value = value.unsqueeze(0)
        if value.ndim != 4 or value.shape[-1] not in (3, 4):
            raise WanXiangError(f"参考图{index}必须是 [B,H,W,3] 或 [B,H,W,4] 图像。")
        result.extend(frame for frame in value)
    if len(result) > 10:
        raise WanXiangError("已连接的参考图总数超过 10 张；请减少批次或输入连接。")
    return result


def _png(frame: torch.Tensor) -> bytes:
    image = _pil_image(frame)
    buffer = io.BytesIO()
    # ``optimize=True`` can spend minutes searching PNG filters on large
    # photographic frames.  The adapter has a byte budget and will switch to
    # high-quality JPEG when PNG does not fit, so use the bounded-time encoder
    # here.  Pixel values remain lossless whenever the PNG fits the budget.
    image.save(buffer, "PNG", compress_level=6, optimize=False)
    return buffer.getvalue()


def _encode_frame(frame: torch.Tensor) -> tuple[PILImage.Image, bytes]:
    """Convert a tensor once and return both the PIL image and its PNG bytes."""
    image = _pil_image(frame)
    buffer = io.BytesIO()
    image.save(buffer, "PNG", compress_level=6, optimize=False)
    return image, buffer.getvalue()


def _ordered_parallel_map(
    items: Sequence[Any], worker: Any, *, enabled: bool, max_workers: int = 4
) -> list[Any]:
    """Run independent image work concurrently while preserving socket order."""
    if not enabled or len(items) < 2:
        return [worker(item) for item in items]
    results: list[Any] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=min(max(1, max_workers), len(items))) as executor:
        futures = {executor.submit(worker, item): index for index, item in enumerate(items)}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


def _reference_worker_count(frames: Sequence[torch.Tensor]) -> int:
    """Choose safe CPU parallelism for high-fidelity reference adaptation."""
    if len(frames) < 2:
        return 1
    pixels = [int(frame.shape[0]) * int(frame.shape[1]) for frame in frames]
    total_pixels = sum(pixels)
    largest_pixels = max(pixels)
    # PIL conversion temporarily needs several image-sized buffers.  Huge
    # references therefore use fewer workers, while normal multi-reference
    # jobs no longer wait for every image to be encoded one by one.
    if largest_pixels >= 20_000_000:
        return 1
    if total_pixels >= 40_000_000:
        return 2
    if total_pixels >= 20_000_000:
        return min(3, len(frames))
    return min(4, len(frames))


def _pil_image(frame: torch.Tensor) -> PILImage.Image:
    array = frame.float().numpy()
    array = np.nan_to_num(array, nan=0.0, posinf=1.0, neginf=0.0)
    array = np.clip(array, 0, 1) * 255 if array.max(initial=0) <= 1 else np.clip(array, 0, 255)
    return PILImage.fromarray(
        np.rint(array).astype(np.uint8), "RGBA" if array.shape[-1] == 4 else "RGB"
    ).convert("RGB")


def _image_mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _fit_image_preserving_dimensions(
    frame: torch.Tensor,
    byte_limit: int,
    *,
    allow_webp: bool,
    original: bytes | None = None,
    image: PILImage.Image | None = None,
) -> bytes:
    """Prefer lossless/high-quality encoding, then minimally resize to fit."""
    if image is None:
        image = _pil_image(frame)
    if original is None:
        buffer = io.BytesIO()
        image.save(buffer, "PNG", compress_level=6, optimize=False)
        original = buffer.getvalue()
    if len(original) <= byte_limit:
        return original
    # WebP lossless keeps the exact pixels and can be substantially smaller
    # than PNG for photographic references.
    if allow_webp:
        buffer = io.BytesIO()
        try:
            image.save(buffer, "WEBP", lossless=True, method=6)
        except Exception:
            candidate = original
        else:
            candidate = buffer.getvalue()
        if len(candidate) <= byte_limit:
            return candidate
    # Lossless compression cannot guarantee a target byte size for detailed
    # imagery. Encode at the original dimensions once at high quality first.
    # The old implementation performed up to 70 JPEG encodes per image; this
    # bounded search uses an area/byte estimate and at most four refinements.
    base_width, base_height = image.size
    quality = 95

    def encode_jpeg(source: PILImage.Image, jpeg_quality: int) -> bytes:
        buffer = io.BytesIO()
        source.save(
            buffer,
            "JPEG",
            quality=jpeg_quality,
            optimize=False,
            progressive=True,
            subsampling=0,
        )
        return buffer.getvalue()

    candidate = encode_jpeg(image, quality)
    if len(candidate) <= byte_limit:
        return candidate

    # JPEG size is approximately proportional to pixel area for a fixed
    # quality. Start close to the target, then make only a few corrections.
    scale = max(0.10, min(0.999, (byte_limit / max(1, len(candidate))) ** 0.5 * 0.96))
    best: bytes | None = None
    best_scale = 0.0
    for _ in range(4):
        resized = image.resize(
            (max(1, round(base_width * scale)), max(1, round(base_height * scale))),
            PILImage.Resampling.LANCZOS,
        )
        candidate = encode_jpeg(resized, quality)
        if len(candidate) <= byte_limit:
            best = candidate
            best_scale = scale
            scale = min(0.999, scale * min(1.12, (byte_limit / max(1, len(candidate))) ** 0.5))
        else:
            scale *= max(0.55, min(0.94, (byte_limit / max(1, len(candidate))) ** 0.5 * 0.98))

    if best is not None:
        return best

    # Extremely detailed images may still exceed the limit at quality 95.
    # One quality fallback is preferable to another long encode search.
    fallback_scale = max(0.10, min(best_scale or scale, 0.999))
    resized = image.resize(
        (max(1, round(base_width * fallback_scale)), max(1, round(base_height * fallback_scale))),
        PILImage.Resampling.LANCZOS,
    )
    for fallback_quality in (92, 88):
        candidate = encode_jpeg(resized, fallback_quality)
        if len(candidate) <= byte_limit:
            return candidate
    raise WanXiangError(
        f"参考图在自适应缩放后仍超过单图限制（{byte_limit / 1024 / 1024:.1f} MB）；"
        "请减少参考图数量，或改用支持文件 URL 的路线。"
    )


def _prepare_images(
    frames: Sequence[torch.Tensor],
    api_channel: str,
    model: str,
    *,
    parallel: bool = False,
    parallel_workers: int = 4,
) -> list[bytes]:
    """Apply per-platform per-image limits without degrading image pixels."""
    if not frames:
        return []
    profile = _route_profile(api_channel, model)
    request_limit = profile["max_request_bytes"]
    if request_limit is None:
        encoded = _ordered_parallel_map(
            frames, _encode_frame, enabled=parallel, max_workers=parallel_workers
        )
        work = list(zip(frames, encoded))
        return _ordered_parallel_map(
            work,
            lambda item: _fit_image_preserving_dimensions(
                item[0],
                profile["max_image_bytes"],
                allow_webp=profile["allow_webp"],
                image=item[1][0],
                original=item[1][1],
            ),
            enabled=parallel,
            max_workers=parallel_workers,
        )

    # Base64 expands binary data by about 4/3. Allocate the available binary
    # budget across the actual number of references (2 images get much more
    # room than 10), then let the encoder find the largest scale per image.
    overhead = 128 * 1024
    binary_budget = max(256 * 1024 * len(frames), (request_limit - overhead) * 3 // 4)
    encoded = _ordered_parallel_map(
        frames, _encode_frame, enabled=parallel, max_workers=parallel_workers
    )
    originals = [item[1] for item in encoded]
    original_total = max(1, sum(len(item) for item in originals))
    budgets = [max(256 * 1024, binary_budget * len(item) // original_total) for item in originals]
    # Keep the sum inside the budget after minimum-size rounding.
    while sum(budgets) > binary_budget:
        index = max(range(len(budgets)), key=budgets.__getitem__)
        if budgets[index] <= 256 * 1024:
            break
        budgets[index] -= min(budgets[index] - 256 * 1024, sum(budgets) - binary_budget)
    work = list(zip(frames, budgets, originals, (item[0] for item in encoded)))
    result = _ordered_parallel_map(
        work,
        lambda item: _fit_image_preserving_dimensions(
            item[0],
            min(profile["max_image_bytes"], item[1]),
            allow_webp=profile["allow_webp"],
            original=item[2],
            image=item[3],
        ),
        enabled=parallel,
        max_workers=parallel_workers,
    )
    estimated_body = sum(len(item) for item in result) * 4 // 3 + overhead
    if estimated_body > request_limit:
        raise WanXiangError(
            f"{api_channel} 的 {len(result)} 张参考图缩放后仍预计请求约 {estimated_body / 1024 / 1024:.1f} MB，"
            "超过路线总请求限制；请减少参考图数量或使用文件 URL 接口。"
        )
    return result


def _image_values(payload: Any) -> list[Any]:
    """Extract documented URL, b64_json, and Gemini inlineData image values."""
    found: list[Any] = []
    image_fields = {"url", "image_url", "b64_json", "image_base64", "base64"}

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            inline = value.get("inlineData") or value.get("inline_data")
            if isinstance(inline, Mapping) and isinstance(inline.get("data"), str):
                found.append(inline["data"])
            for key, item in value.items():
                if str(key).lower() in image_fields and isinstance(item, (str, bytes)):
                    found.append(item)
                elif isinstance(item, (Mapping, list)):
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    unique: list[Any] = []
    for value in found:
        if value not in unique:
            unique.append(value)
    return unique


def _grsai_data(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, Mapping) else payload


def _grsai_result_values(payload: Mapping[str, Any]) -> list[Any]:
    """Read only Grsai's documented result image fields, not arbitrary URLs."""
    data = _grsai_data(payload)
    found: list[Any] = []
    results = data.get("results")
    if isinstance(results, Sequence) and not isinstance(results, (str, bytes)):
        for item in results:
            if not isinstance(item, Mapping):
                continue
            for key in ("url", "b64_json", "image_base64", "base64"):
                value = item.get(key)
                if isinstance(value, (str, bytes)):
                    found.append(value)
                    break
    # GPT's document keeps a legacy top-level URL for the first result.
    if not found and isinstance(data.get("url"), (str, bytes)):
        found.append(data["url"])
    unique: list[Any] = []
    for value in found:
        if value not in unique:
            unique.append(value)
    return unique


def _grsai_status(payload: Mapping[str, Any]) -> str:
    return str(_grsai_data(payload).get("status", "")).strip().lower()


def _grsai_failure(payload: Mapping[str, Any]) -> str:
    data = _grsai_data(payload)
    return _safe_message(
        data.get("error")
        or data.get("failure_reason")
        or payload.get("msg")
        or payload.get("message")
        or "服务返回失败"
    )


class _GrsaiGPTTaskFailure(WanXiangError):
    """Only a confirmed failed task may authorize another paid submission."""

    def __init__(self, task_id: str, payload: Mapping[str, Any]) -> None:
        self.task_id = task_id
        self.detail = _grsai_failure(payload)
        super().__init__(f"Grsai 任务 {task_id or '未返回ID'} 失败：{self.detail}")
        data = _grsai_data(payload)
        error = " ".join(str(data.get("error", "")).lower().split())
        error = error.removesuffix(" please retry later.").rstrip(".")
        self.upstream_reason = {
            "upstream rate limit exceeded": "上游限流",
            "upstream service is temporarily unavailable": "上游服务暂时不可用",
        }.get(error, "")
        self.retryable = bool(
            task_id
            and _grsai_status(payload) == "failed"
            and data.get("failure_reason") in (None, "", "error")
            and self.upstream_reason
        )


def _download_image(url: str) -> bytes:
    last_error: WanXiangError | None = None
    for attempt in range(1, IMAGE_DOWNLOAD_RETRIES + 1):
        try:
            return _http(
                Request(url, headers={"User-Agent": "ComfyUI-FanWanXiang/1.0"}),
                action="下载生成图片",
                timeout=IMAGE_DOWNLOAD_TIMEOUT,
            )
        except WanXiangNetworkError as exc:
            last_error = exc
            delay = float(attempt)
        except WanXiangHTTPError as exc:
            if exc.status_code not in TRANSIENT_HTTP_STATUSES:
                raise
            last_error = exc
            delay = exc.retry_after if exc.retry_after is not None else float(attempt)
        if attempt < IMAGE_DOWNLOAD_RETRIES:
            time.sleep(delay)
    assert last_error is not None
    raise last_error


def _decode_image(value: Any) -> torch.Tensor:
    if isinstance(value, bytes):
        data = value
    elif isinstance(value, str):
        text = value.strip()
        if text.startswith("data:image/"):
            try:
                data = base64.b64decode(text.split(",", 1)[1], validate=True)
            except (IndexError, ValueError) as exc:
                raise WanXiangError("返回的 data URI 图像无效。") from exc
        elif _is_http_url(text):
            data = _download_image(text)
        else:
            try:
                data = base64.b64decode(text, validate=True)
            except ValueError as exc:
                raise WanXiangError("响应中的图片既不是 URL，也不是 base64。") from exc
    else:
        raise WanXiangError("响应中的图片字段格式错误。")
    try:
        with PILImage.open(io.BytesIO(data)) as image:
            pixels = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    except Exception as exc:
        raise WanXiangError("服务返回的内容无法解码为图片。") from exc
    return torch.from_numpy(pixels).unsqueeze(0)


def _to_tensor(
    values: Sequence[Any], *, parallel: bool = False
) -> tuple[torch.Tensor, list[Any], list[dict[str, Any]]]:
    """Decode a stable IMAGE batch, retaining partial-download diagnostics."""
    if not values:
        raise WanXiangError("服务响应中没有找到可用图片。")
    decoded: list[torch.Tensor | None] = [None] * len(values)
    failures: list[dict[str, Any]] = []

    if parallel and len(values) > 1:
        with ThreadPoolExecutor(max_workers=min(MAX_IMAGE_DOWNLOAD_WORKERS, len(values))) as executor:
            futures = {
                executor.submit(_decode_image, value): index
                for index, value in enumerate(values)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    decoded[index] = future.result()
                except Exception as exc:
                    failures.append({"index": index + 1, "message": _safe_message(exc)})
    else:
        for index, value in enumerate(values):
            try:
                decoded[index] = _decode_image(value)
            except Exception as exc:
                failures.append({"index": index + 1, "message": _safe_message(exc)})

    successful = [
        (index, item)
        for index, item in enumerate(decoded)
        if item is not None
    ]
    if not successful:
        details = "；".join(
            f"图片{item['index']}: {item['message']}" for item in failures
        )
        raise WanXiangError(f"服务返回的图片全部下载或解码失败：{details[:1000]}")

    shapes = {tuple(item.shape[1:]) for _, item in successful}
    if len(shapes) != 1:
        dimensions = "，".join(
            f"图片{index + 1}={item.shape[2]}x{item.shape[1]}"
            for index, item in successful
        )
        raise WanXiangError(
            "服务返回的多张图片尺寸不一致，无法组成 ComfyUI IMAGE 批次；"
            f"节点未静默丢图（{dimensions}）。"
        )

    if failures:
        LOGGER.warning("Generated image decode partial failure: %s", failures)
    tensors = [item for _, item in successful]
    successful_values = [values[index] for index, _ in successful]
    return torch.cat(tensors, dim=0).float(), successful_values, failures


def _controlled_prompt(prompt: str, prompt_strength: str, ref_strength: str) -> str:
    return (
        f"{prompt.strip()}\n\n[生成控制]\n"
        f"提示词循环强度：{prompt_strength}。{PROMPT_RULES[prompt_strength]}\n"
        f"参考图保留强度：{ref_strength}。{REFERENCE_RULES[ref_strength]}"
    )


def _openai_size(aspect_ratio: str, resolution: str) -> str:
    longest = {"1K": 1024, "2K": 2048, "4K": 4096}[resolution]
    if aspect_ratio in {"auto", "1:1"}:
        return f"{longest}x{longest}"
    left, right = (int(item) for item in aspect_ratio.split(":"))
    if left >= right:
        return f"{longest}x{max(1, round(longest * right / left))}"
    return f"{max(1, round(longest * left / right))}x{longest}"


def _grsai_gpt_size(model: str, aspect_ratio: str, resolution: str) -> str:
    """Return a documented pixel size for Grsai's pixel-only GPT models."""
    if aspect_ratio == "auto":
        return "auto"
    if model not in {"gpt-image-2-vip", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"}:
        return _openai_size(aspect_ratio, resolution)
    documented = {
        "1:1": {"1K": "1024x1024", "2K": "2048x2048", "4K": "2880x2880"},
        "16:9": {"1K": "1280x720", "2K": "2048x1152", "4K": "3840x2160"},
        "9:16": {"1K": "720x1280", "2K": "1152x2048", "4K": "2160x3840"},
        "4:3": {"1K": "1152x864", "2K": "2304x1728", "4K": "3264x2448"},
        "3:4": {"1K": "864x1152", "2K": "1728x2304", "4K": "2448x3264"},
        "3:2": {"1K": "1536x1024", "2K": "2048x1360", "4K": "3504x2336"},
        "2:3": {"1K": "1024x1536", "2K": "1360x2048", "4K": "2336x3504"},
        "5:4": {"1K": "1120x896", "2K": "2240x1792", "4K": "3200x2560"},
        "4:5": {"1K": "896x1120", "2K": "1792x2240", "4K": "2560x3200"},
    }
    return documented.get(aspect_ratio, {}).get(resolution, _openai_size(aspect_ratio, resolution))


class FanWanXiangImage:
    CATEGORY = "APL/图像生成"
    DESCRIPTION = "支持 10 张独立参考图、Grsai 智能并发生成及六条 APL 路线的多平台图像生成节点。"
    FUNCTION = "generate"
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("🖼️ 图像", "🔗 图片链接", "🆔 任务ID", "📦 响应信息")
    OUTPUT_TOOLTIPS = ("ComfyUI IMAGE 图像", "第一张图片 URL；无 URL 时为空", "服务任务 ID；同步线路可能为空", "已脱敏的结构化响应信息")

    def __init__(self) -> None:
        self._last_seed: int | None = None
        self._lock = threading.Lock()

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        images = {
            f"image{i}": ("IMAGE", {"display_name": f"🖼️ 参考图{i}", "tooltip": "可选；未连接的图像不会上传。"})
            for i in range(1, 11)
        }
        return {
            "required": {
                "api_channel": (list(CHANNELS), {"default": RH_DIRECT, "display_name": "🌐 API线路"}),
                "api_key": ("STRING", {"default": "", "password": True, "display_name": "🔐 API密钥", "tooltip": "必填，不写入日志或响应。"}),
                "custom_api_url": ("STRING", {"default": "", "display_name": "🔗 第三方/自定义 API 地址", "placeholder": "第三方填基础地址；自定义填完整接口地址"}),
                "prompt": ("STRING", {"default": "", "multiline": True, "dynamicPrompts": True, "display_name": "📝 提示词", "placeholder": "从灵感到画面，让想象自由发生。"}),
                "prompt_strength": (list(PROMPT_STRENGTH), {"default": "严格", "display_name": "🎚️ 提示词循环强度"}),
                "ref_strength": (list(REFERENCE_STRENGTH), {"default": "高保留", "display_name": "🧲 参考图保留强度"}),
                "model": (list(MODELS), {"default": "gemini-3.1-flash-image-preview", "display_name": "🧠 模型版本"}),
                "aspect_ratio": (list(RATIOS), {"default": "2:3", "display_name": "├── ↔️ 宽高比"}),
                "resolution": (list(RESOLUTIONS), {"default": "2K", "display_name": "├── 🖥️ 图片分辨率"}),
                "seed": ("INT", {"default": 583, "min": 0, "max": 0xFFFFFFFF, "control_after_generate": False, "display_name": "├── 🎲 随机种子"}),
                "randomize": (list(RANDOMIZE), {"default": "fixed", "display_name": "├── 🔀 randomize"}),
                "num_images": (
                    list(PARALLEL_GENERATIONS),
                    {
                        "default": "1",
                        "display_name": "└── 🚀 高性能 - 智能并发生成",
                        "tooltip": (
                            "多图同时处理，大幅提升生成速度。当前依据开源实现仅用于 Grsai 直连；"
                            "1 为普通单图，2–12 为独立生图任务数量，可能按任务分别计费。"
                        ),
                    },
                ),
            },
            "optional": images,
        }

    @classmethod
    def IS_CHANGED(
        cls,
        seed: int = 583,
        randomize: str = "fixed",
        num_images: str = "1",
        **_: Any,
    ) -> bool | float:
        parallel_count = _parallel_generation_count(num_images)
        return float("nan") if int(seed) == 0 or randomize != "fixed" or parallel_count > 1 else False

    def _effective_seed(self, seed: int, randomize: str) -> int:
        base = int(seed) & 0xFFFFFFFF
        with self._lock:
            if base == 0 or randomize == "randomize":
                result = secrets.randbelow(0xFFFFFFFF) + 1
            elif randomize == "increment":
                result = ((self._last_seed if self._last_seed is not None else base) + 1) & 0xFFFFFFFF
            elif randomize == "decrement":
                result = ((self._last_seed if self._last_seed is not None else base) - 1) & 0xFFFFFFFF
            else:
                result = base
            self._last_seed = result or 1
            return self._last_seed

    @staticmethod
    def _validate(api_channel: str, api_key: str, custom_api_url: str, prompt: str, model: str, prompt_strength: str, ref_strength: str, aspect_ratio: str, resolution: str, randomize: str) -> str:
        if api_channel not in CHANNELS or model not in MODELS or aspect_ratio not in RATIOS or resolution not in RESOLUTIONS:
            raise WanXiangError("节点参数无效，请从下拉选项中选择。")
        supported = CHANNEL_MODELS.get(api_channel, frozenset())
        if model not in supported:
            raise WanXiangError(
                f"{api_channel} 的接口文档未定义模型 {model}，请更换该平台支持的模型或选择对应路线。"
            )
        if prompt_strength not in PROMPT_STRENGTH or ref_strength not in REFERENCE_STRENGTH or randomize not in RANDOMIZE:
            raise WanXiangError("强度或随机种子策略无效。")
        if not isinstance(api_key, str) or not api_key.strip():
            raise WanXiangError("🔐 API密钥不能为空。")
        if not isinstance(prompt, str) or not prompt.strip():
            raise WanXiangError("📝 提示词不能为空。")
        if api_channel in {THIRD_PARTY, CUSTOM} and (not isinstance(custom_api_url, str) or not custom_api_url.strip() or not _is_http_url(custom_api_url)):
            if api_channel == THIRD_PARTY:
                raise WanXiangError("选择“第三方线路”时，必须填写该平台的基础 API 地址（http/https）。")
            raise WanXiangError("选择“自定义线路”时，必须填写有效的 http/https 自定义API地址。")
        return api_channel

    @staticmethod
    def _rh(api_key: str, model: str, images: Sequence[bytes], prompt: str, aspect_ratio: str, resolution: str) -> tuple[list[Any], str, dict[str, Any]]:
        if not images:
            raise WanXiangError("RH 直连至少需要连接一张参考图。")
        headers = {"Authorization": f"Bearer {api_key.strip()}"}
        urls: list[str] = []
        for index, image in enumerate(images, 1):
            mime = _image_mime(image)
            extension = "jpg" if mime == "image/jpeg" else "png"
            uploaded = _post_multipart(RH_UPLOAD, (), [("file", f"reference_{index}.{extension}", mime, image)], headers, action=f"上传参考图{index}")
            data = uploaded.get("data") if isinstance(uploaded.get("data"), Mapping) else {}
            url = data.get("download_url")
            if not isinstance(url, str) or not _is_http_url(url):
                raise WanXiangError(f"上传参考图{index}失败：未返回下载地址。")
            urls.append(url)
        payload: dict[str, Any] = {"imageUrls": urls, "prompt": prompt, "resolution": resolution.lower()}
        if aspect_ratio != "auto":
            payload["aspectRatio"] = aspect_ratio
        if model == "gpt-image-2":
            payload["quality"] = "medium"
        response = _post_json(RH_ENDPOINTS[model], payload, headers, action="提交 RH 生图任务")
        task_id = str(response.get("taskId") or response.get("task_id") or "")
        if not task_id:
            raise WanXiangError("RH 未返回任务ID。")
        deadline = time.monotonic() + 360
        while str(response.get("status", "")).upper() not in {"SUCCESS", "SUCCEEDED", "COMPLETED"}:
            if time.monotonic() > deadline:
                raise WanXiangError(f"RH 任务 {task_id} 等待超时。")
            if str(response.get("status", "")).upper() in {"FAILED", "ERROR", "CANCELLED", "CANCELED"}:
                raise WanXiangError(f"RH 任务 {task_id} 失败：{_safe_message(response.get('message') or response.get('errorMessage') or '')}")
            time.sleep(2)
            response = _post_json(RH_QUERY, {"taskId": task_id}, headers, action="查询 RH 生图任务")
        return _image_values(response), task_id, response

    @staticmethod
    def _grsai(
        api_key: str,
        model: str,
        images: Sequence[bytes],
        prompt: str,
        aspect_ratio: str,
        resolution: str,
        image_data_uris: Sequence[str] | None = None,
    ) -> tuple[list[Any], str, dict[str, Any]]:
        if model not in GRSAI_GPT_MODELS:
            return FanWanXiangImage._grsai_once(
                api_key, model, images, prompt, aspect_ratio, resolution, image_data_uris
            )

        encoded_images = image_data_uris if image_data_uris is not None else tuple(
            f"data:{_image_mime(image)};base64," + base64.b64encode(image).decode("ascii")
            for image in images
        )
        failed_tasks: list[dict[str, Any]] = []
        max_attempts = len(GRSAI_GPT_TASK_RETRY_DELAYS) + 1
        for attempt in range(1, max_attempts + 1):
            try:
                values, task_id, remote = FanWanXiangImage._grsai_once(
                    api_key, model, images, prompt, aspect_ratio, resolution, encoded_images
                )
            except _GrsaiGPTTaskFailure as exc:
                if not exc.retryable:
                    if failed_tasks:
                        previous_ids = ", ".join(item["task_id"] for item in failed_tasks)
                        raise WanXiangError(f"{exc}；此前失败任务ID：{previous_ids}") from exc
                    raise
                failed_tasks.append({"task_id": exc.task_id, "error": exc.detail})
                if attempt == max_attempts:
                    task_ids = ", ".join(item["task_id"] for item in failed_tasks)
                    raise WanXiangError(
                        f"Grsai GPT {exc.upstream_reason}，已尝试 {attempt} 次，仍未生成成功。"
                        f"请稍后再试，或将任务ID交给 Grsai 排查：{task_ids}。"
                        f"最后错误：{exc.detail}"
                    ) from exc
                # Back off only after a terminal failure, never after an
                # ambiguous submit timeout or an exhausted result query.
                delay = GRSAI_GPT_TASK_RETRY_DELAYS[attempt - 1] + secrets.randbelow(6)
                failed_tasks[-1]["retry_delay_seconds"] = delay
                LOGGER.warning(
                    "Grsai GPT confirmed upstream failure: task=%s error=%s; retry %d/%d in %.0fs",
                    exc.task_id, exc.detail, attempt, max_attempts - 1, delay,
                )
                time.sleep(delay)
            except WanXiangError as exc:
                if failed_tasks:
                    previous_ids = ", ".join(item["task_id"] for item in failed_tasks)
                    raise WanXiangError(f"{exc}；此前失败任务ID：{previous_ids}") from exc
                raise
            else:
                if failed_tasks:
                    remote = {
                        **remote,
                        "generation_retry": {"attempts": attempt, "failed_tasks": failed_tasks},
                    }
                return values, task_id, remote

    @staticmethod
    def _grsai_once(
        api_key: str,
        model: str,
        images: Sequence[bytes],
        prompt: str,
        aspect_ratio: str,
        resolution: str,
        image_data_uris: Sequence[str] | None = None,
    ) -> tuple[list[Any], str, dict[str, Any]]:
        """Call Grsai's Gemini or GPT Image endpoint using its documented contract."""
        uses_gpt_api = model in GRSAI_GPT_MODELS
        endpoint = "/v1/draw/nano-banana" if model.startswith("gemini-") else "/v1/api/generate"
        grsai_model = {
            "gemini-3.1-flash-image-preview": "nano-banana-2",
            "gemini-3-pro-image-preview": "nano-banana-pro",
            **{gpt_model: gpt_model for gpt_model in GRSAI_GPT_MODELS},
        }[model]
        # Grsai exposes two different request contracts under the same host:
        # Nano Banana uses Gemini-style ``aspectRatio`` + ``imageSize`` values,
        # while GPT Image expects a pixel size in ``aspectRatio`` and a
        # separate ``quality`` field.  Sending the Gemini fields to the GPT
        # endpoint is rejected as an invalid-parameter request.
        encoded_images = list(image_data_uris) if image_data_uris is not None else [
            f"data:{_image_mime(image)};base64," + base64.b64encode(image).decode("ascii")
            for image in images
        ]
        payload: dict[str, Any] = {
            "model": grsai_model,
            "prompt": prompt,
            ("images" if uses_gpt_api else "urls"): encoded_images,
        }
        if model.startswith("gemini-"):
            # The Nano Banana endpoint uses the legacy Grsai draw contract.
            payload["webHook"] = "-1"
            payload.update({"aspectRatio": aspect_ratio, "imageSize": resolution})
        else:
            # The GPT Image endpoint is documented at /v1/api/generate. Use
            # async so Grsai acknowledges the task immediately; the result is
            # then read from the documented GET /v1/api/result endpoint.
            payload.update(
                {
                    "aspectRatio": _grsai_gpt_size(model, aspect_ratio, resolution),
                    "quality": "auto",
                    "replyType": "async",
                }
            )
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Accept": "application/json, text/event-stream",
            "Connection": "close",
        }
        try:
            response = _post_grsai_submit(f"{GRSAI_BASE_URL}{endpoint}", payload, headers)
        except WanXiangNetworkError as exc:
            if exc.timed_out:
                raise WanXiangError(
                    "Grsai 提交响应超时：平台可能已经受理并继续生图，但节点没有收到任务ID。"
                    "为避免重复扣费，本节点没有自动重提；请先到 Grsai 平台日志确认任务状态。"
                ) from None
            raise
        if response.get("code") not in (None, 0):
            raise WanXiangError(f"Grsai 生图接口失败：{response.get('msg') or response.get('message') or '服务返回错误'}")
        data = _grsai_data(response)
        task_id = str(data.get("id") or response.get("id") or "")
        if task_id:
            LOGGER.info("Grsai task accepted: %s", task_id)
        status = _grsai_status(response)
        values = _grsai_result_values(response)
        success_statuses = {"success", "succeeded", "completed"}
        failure_statuses = {"failed", "error", "cancelled", "canceled", "expired"}
        if uses_gpt_api:
            failure_statuses.add("violation")

        if status in failure_statuses:
            if uses_gpt_api:
                raise _GrsaiGPTTaskFailure(task_id, response)
            raise WanXiangError(f"Grsai 任务 {task_id or '未返回ID'} 失败：{_grsai_failure(response)}")
        if status in success_statuses and not values:
            raise WanXiangError(
                f"Grsai 任务 {task_id or '未返回ID'} 已成功，但响应中没有 results 图片链接。"
            )
        if not task_id:
            if values and (not status or status in success_statuses):
                return values, "", response
            raise WanXiangError("Grsai 未返回任务 ID 或图片结果。")

        accepted_at = time.monotonic()
        deadline = accepted_at + GRSAI_TASK_TIMEOUT
        poll_count = 0
        while not (values and (not status or status in success_statuses)):
            if status in failure_statuses:
                if uses_gpt_api:
                    raise _GrsaiGPTTaskFailure(task_id, response)
                raise WanXiangError(
                    f"Grsai 任务 {task_id} 失败：{_grsai_failure(response)}"
                )
            if status in success_statuses:
                raise WanXiangError(
                    f"Grsai 任务 {task_id} 已成功，但响应中没有 results 图片链接。"
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WanXiangError(f"Grsai 任务 {task_id} 等待超时。")
            time.sleep(min(GRSAI_POLL_INTERVAL, remaining))
            poll_count += 1
            if uses_gpt_api:
                response = FanWanXiangImage._poll_grsai_task(
                    headers, task_id, poll_count, deadline, gpt_api=True
                )
            else:
                response = FanWanXiangImage._poll_grsai_task(
                    headers, task_id, poll_count, deadline
                )
            if response.get("code") == -22:
                # A just-created task can take a moment to become visible to
                # the result service. Do not mistake a permanently unknown ID
                # for a six-minute running task.
                if time.monotonic() - accepted_at >= GRSAI_NOT_FOUND_GRACE:
                    raise WanXiangError(
                        f"Grsai 任务 {task_id} 在 {GRSAI_NOT_FOUND_GRACE:.0f} 秒内始终未被平台查询接口识别（code=-22）。"
                    )
                status = "pending"
                values = []
                continue
            if response.get("code") not in (None, 0):
                raise WanXiangError(f"查询 Grsai 生图任务失败：{response.get('msg') or response.get('message') or '服务返回错误'}")
            status = _grsai_status(response)
            values = _grsai_result_values(response)
        LOGGER.info("Grsai task finished: %s status=%s polls=%d", task_id, status or "unknown", poll_count)
        return values, task_id, response

    @staticmethod
    def _poll_grsai_task(
        headers: Mapping[str, str],
        task_id: str,
        poll_count: int,
        deadline: float,
        *,
        gpt_api: bool = False,
    ) -> dict[str, Any]:
        last_error: WanXiangError | None = None
        for attempt in range(1, GRSAI_POLL_RETRIES + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WanXiangError(f"Grsai 任务 {task_id} 等待超时。")
            connect_timeout = max(0.1, min(float(GRSAI_POLL_TIMEOUT[0]), remaining * 0.3))
            read_timeout = max(0.1, min(float(GRSAI_POLL_TIMEOUT[1]), remaining - connect_timeout))
            try:
                if gpt_api:
                    return _get_json(
                        f"{GRSAI_BASE_URL}/v1/api/result?id={quote(task_id, safe='')}",
                        headers,
                        action=f"查询 Grsai GPT 生图任务 {task_id}",
                        timeout=(connect_timeout, read_timeout),
                    )
                return _post_json(
                    f"{GRSAI_BASE_URL}/v1/draw/result",
                    {"id": task_id},
                    headers,
                    action=f"查询 Grsai 生图任务 {task_id}",
                    timeout=(connect_timeout, read_timeout),
                )
            except WanXiangNetworkError as exc:
                last_error = exc
                delay = min(4.0, float(2 ** (attempt - 1)))
            except WanXiangHTTPError as exc:
                if exc.status_code not in TRANSIENT_HTTP_STATUSES:
                    raise
                last_error = exc
                delay = exc.retry_after if exc.retry_after is not None else min(
                    4.0, float(2 ** (attempt - 1))
                )
            if attempt >= GRSAI_POLL_RETRIES:
                break
            remaining = deadline - time.monotonic()
            if remaining <= delay:
                raise WanXiangError(f"Grsai 任务 {task_id} 等待超时。")
            LOGGER.warning(
                "Grsai poll transient failure: task=%s poll=%d attempt=%d/%d; retry in %.1fs",
                task_id,
                poll_count,
                attempt,
                GRSAI_POLL_RETRIES,
                delay,
            )
            time.sleep(delay)
        raise WanXiangError(
            f"Grsai 任务 {task_id} 查询连续失败；任务可能仍在平台运行。"
            f"请保留该任务ID后重试查询（{_safe_message(last_error)}）。"
        ) from None

    @staticmethod
    def _grsai_worker_count(requested: int, images: Sequence[bytes]) -> int:
        estimated_body = sum(4 * ((len(image) + 2) // 3) + 64 for image in images) + 64 * 1024
        memory_limit = max(1, GRSAI_CONCURRENT_BODY_BUDGET // max(1, estimated_body))
        return max(1, min(requested, MAX_GRSAI_CONCURRENT_JOBS, memory_limit))

    @staticmethod
    def _grsai_parallel(
        api_key: str,
        model: str,
        images: Sequence[bytes],
        prompt: str,
        aspect_ratio: str,
        resolution: str,
        requested: int,
    ) -> tuple[list[Any], str, dict[str, Any]]:
        workers = FanWanXiangImage._grsai_worker_count(requested, images)
        LOGGER.info(
            "Grsai smart parallel start: requested=%d active_workers=%d references=%d",
            requested,
            workers,
            len(images),
        )
        completed: dict[int, tuple[list[Any], str, dict[str, Any]]] = {}
        failures: dict[int, str] = {}
        image_data_uris = tuple(
            f"data:{_image_mime(image)};base64," + base64.b64encode(image).decode("ascii")
            for image in images
        )

        def generate_one() -> tuple[list[Any], str, dict[str, Any]]:
            return FanWanXiangImage._grsai(
                api_key, model, images, prompt, aspect_ratio, resolution, image_data_uris
            )

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(generate_one): index for index in range(requested)}
            for future in as_completed(futures):
                index = futures[future]
                try:
                    completed[index] = future.result()
                except Exception as exc:
                    failures[index] = _safe_message(exc)
                    LOGGER.warning("Grsai parallel job %d failed: %s", index + 1, failures[index])

        values: list[Any] = []
        task_ids: list[str] = []
        task_responses: list[dict[str, Any]] = []
        for index in range(requested):
            if index not in completed:
                continue
            task_values, task_id, task_response = completed[index]
            values.extend(task_values)
            if task_id:
                task_ids.append(task_id)
            task_responses.append(
                {"index": index + 1, "task_id": task_id, "response": task_response}
            )
        if not values:
            details = "；".join(
                f"任务{index + 1}: {message}" for index, message in sorted(failures.items())
            )
            raise WanXiangError(f"Grsai 智能并发生成全部失败：{details[:1000]}")

        remote = {
            "parallel": {
                "requested": requested,
                "active_workers": workers,
                "succeeded": len(completed),
                "failed": len(failures),
                "task_ids": task_ids,
                "errors": [
                    {"index": index + 1, "message": message}
                    for index, message in sorted(failures.items())
                ],
            },
            "tasks": task_responses,
        }
        LOGGER.info(
            "Grsai smart parallel finished: succeeded=%d failed=%d",
            len(completed),
            len(failures),
        )
        # Preserve the existing single task-id output contract. All task IDs
        # remain available in the structured response information.
        return values, task_ids[0] if task_ids else "", remote

    @staticmethod
    def _gemini(base_url: str, api_key: str, model: str, images: Sequence[bytes], prompt: str, aspect_ratio: str, resolution: str) -> tuple[list[Any], str, dict[str, Any]]:
        parts: list[dict[str, Any]] = [{"text": prompt}]
        parts.extend(
            {"inlineData": {"mimeType": _image_mime(image), "data": base64.b64encode(image).decode("ascii")}}
            for image in images
        )
        config: dict[str, Any] = {"responseModalities": ["TEXT", "IMAGE"], "imageConfig": {"imageSize": resolution}}
        if aspect_ratio != "auto":
            config["imageConfig"]["aspectRatio"] = aspect_ratio
        response = _post_json(f"{base_url}/v1beta/models/{model}:generateContent", {"contents": [{"role": "user", "parts": parts}], "generationConfig": config}, {"x-goog-api-key": api_key.strip()}, action="调用 Gemini 生图接口")
        return _image_values(response), str(response.get("responseId") or response.get("id") or ""), response

    @staticmethod
    def _openai(base_url: str, api_key: str, model: str, images: Sequence[bytes], prompt: str, aspect_ratio: str, resolution: str) -> tuple[list[Any], str, dict[str, Any]]:
        base = base_url.rstrip("/")
        fields = [("model", model), ("prompt", prompt), ("n", "1"), ("size", _openai_size(aspect_ratio, resolution)), ("quality", "medium"), ("response_format", "b64_json")]
        headers = {"Authorization": f"Bearer {api_key.strip()}"}
        if images:
            files = [("image", f"reference_{i}.{'jpg' if _image_mime(data) == 'image/jpeg' else 'png'}", _image_mime(data), data) for i, data in enumerate(images, 1)]
            response = _post_multipart(f"{base}/images/edits", fields, files, headers, action="调用图像编辑接口")
        else:
            response = _post_json(f"{base}/images/generations", dict(fields), headers, action="调用图像生成接口")
        return _image_values(response), str(response.get("id") or response.get("task_id") or ""), response

    @staticmethod
    def _custom(url: str, api_key: str, model: str, images: Sequence[bytes], prompt: str, parameters: Mapping[str, Any]) -> tuple[list[Any], str, dict[str, Any]]:
        response = _post_json(url.strip(), {"model": model, "prompt": prompt, "reference_images": [f"data:{_image_mime(image)};base64," + base64.b64encode(image).decode("ascii") for image in images], "parameters": dict(parameters)}, {"Authorization": f"Bearer {api_key.strip()}"}, action="调用自定义生图接口")
        return _image_values(response), str(response.get("task_id") or response.get("taskId") or response.get("id") or ""), response

    @staticmethod
    def _third_party(base_url: str, api_key: str, model: str, images: Sequence[bytes], prompt: str, aspect_ratio: str, resolution: str) -> tuple[list[Any], str, dict[str, Any]]:
        """Call a user-supplied third-party endpoint using its native API contract.

        The URL is a provider base URL (for example ``https://host/v1`` for
        OpenAI-compatible services or ``https://host`` for Gemini-compatible
        services).  This is intentionally separate from ``_custom``: custom
        routes receive the documented generic JSON envelope instead.
        """
        base = base_url.strip().rstrip("/")
        if model.startswith("gemini-"):
            return FanWanXiangImage._gemini(base, api_key, model, images, prompt, aspect_ratio, resolution)
        return FanWanXiangImage._openai(base, api_key, model, images, prompt, aspect_ratio, resolution)

    def generate(self, api_channel: str, api_key: str, custom_api_url: str, prompt: str, prompt_strength: str, ref_strength: str, model: str, aspect_ratio: str, resolution: str, seed: int, randomize: str, image1: Any = None, image2: Any = None, image3: Any = None, image4: Any = None, image5: Any = None, image6: Any = None, image7: Any = None, image8: Any = None, image9: Any = None, image10: Any = None, num_images: str = "1") -> tuple[torch.Tensor, str, str, str]:
        execution_started = time.monotonic()
        api_channel = self._validate(api_channel, api_key, custom_api_url, prompt, model, prompt_strength, ref_strength, aspect_ratio, resolution, randomize)
        parallel_count = _parallel_generation_count(num_images)
        if parallel_count > 1 and api_channel != GRSAI_DIRECT:
            raise WanXiangError(
                "🚀 高性能智能并发目前仅按 Grsai 开源节点协议用于“Grsai 直连”；"
                "其他路线请将生成数量设为 1，避免未经文档确认的重复请求和扣费。"
            )
        frames = _frames((image1, image2, image3, image4, image5, image6, image7, image8, image9, image10))
        reference_workers = _reference_worker_count(frames)
        LOGGER.info(
            "APL reference adapt start: route=%s model=%s references=%d workers=%d",
            api_channel,
            model,
            len(frames),
            reference_workers,
        )
        adapt_started = time.monotonic()
        images = _prepare_images(
            frames,
            api_channel,
            model,
            parallel=reference_workers > 1,
            parallel_workers=reference_workers,
        )
        LOGGER.info(
            "APL reference adapt ready: route=%s images=%d payload_bytes=%d workers=%d elapsed_ms=%d",
            api_channel,
            len(images),
            sum(len(image) for image in images),
            reference_workers,
            round((time.monotonic() - adapt_started) * 1000),
        )
        effective_seed = self._effective_seed(seed, randomize)
        enhanced_prompt = _controlled_prompt(prompt, prompt_strength, ref_strength)
        parameters = {"prompt_strength": prompt_strength, "ref_strength": ref_strength, "aspect_ratio": aspect_ratio, "resolution": resolution, "seed": int(seed), "effective_seed": effective_seed, "randomize": randomize, "reference_image_count": len(images), "requested_output_count": parallel_count}
        remote_started = time.monotonic()
        if api_channel == RH_DIRECT:
            values, task_id, remote = self._rh(api_key, model, images, enhanced_prompt, aspect_ratio, resolution)
        elif api_channel == GRSAI_DIRECT:
            if parallel_count > 1:
                values, task_id, remote = self._grsai_parallel(
                    api_key,
                    model,
                    images,
                    enhanced_prompt,
                    aspect_ratio,
                    resolution,
                    parallel_count,
                )
            else:
                values, task_id, remote = self._grsai(api_key, model, images, enhanced_prompt, aspect_ratio, resolution)
        elif api_channel == THIRD_PARTY:
            values, task_id, remote = self._third_party(custom_api_url, api_key, model, images, enhanced_prompt, aspect_ratio, resolution)
        elif api_channel == CUSTOM:
            values, task_id, remote = self._custom(custom_api_url, api_key, model, images, enhanced_prompt, parameters)
        elif model.startswith("gemini-"):
            gemini_base = {APIYI_DIRECT: "https://api.apiyi.com", YYROUTER_DIRECT: YYROUTER_BASE_URL}[api_channel]
            values, task_id, remote = self._gemini(gemini_base, api_key, model, images, enhanced_prompt, aspect_ratio, resolution)
        else:
            openai_base = {YYROUTER_DIRECT: f"{YYROUTER_BASE_URL}/v1"}[api_channel]
            values, task_id, remote = self._openai(openai_base, api_key, model, images, enhanced_prompt, aspect_ratio, resolution)
        remote_elapsed_ms = round((time.monotonic() - remote_started) * 1000)
        decode_started = time.monotonic()
        output, decoded_values, decode_errors = _to_tensor(
            values, parallel=len(values) > 1
        )
        decode_elapsed_ms = round((time.monotonic() - decode_started) * 1000)
        total_elapsed_ms = round((time.monotonic() - execution_started) * 1000)
        LOGGER.info(
            "APL execution timing: route=%s references=%d remote_ms=%d download_decode_ms=%d total_ms=%d",
            api_channel,
            len(images),
            remote_elapsed_ms,
            decode_elapsed_ms,
            total_elapsed_ms,
        )
        remote_urls = [
            value.strip()
            for value in values
            if isinstance(value, str) and _is_http_url(value)
        ]
        urls = [
            value.strip()
            for value in decoded_values
            if isinstance(value, str) and _is_http_url(value)
        ]
        profile = _route_profile(api_channel, model)
        summary = {
            "task_id": task_id,
            "request": {
                "api_channel": api_channel,
                "model": model,
                "adapter": {
                    "max_image_mb": profile["max_image_bytes"] / 1024 / 1024,
                    "max_request_mb": None if profile["max_request_bytes"] is None else profile["max_request_bytes"] / 1024 / 1024,
                },
                **parameters,
                "timing_ms": {
                    "remote": remote_elapsed_ms,
                    "download_decode": decode_elapsed_ms,
                    "total": total_elapsed_ms,
                },
            },
            "output_urls": remote_urls,
            "decoded_output_urls": urls,
            "output_decode_errors": decode_errors,
            "remote_response": remote,
        }
        return output, urls[0] if urls else "", task_id, json.dumps(summary, ensure_ascii=False)


NODE_CLASS_MAPPINGS = {NODE_NAME: FanWanXiangImage}
NODE_DISPLAY_NAME_MAPPINGS = {NODE_NAME: NODE_DISPLAY_NAME}
