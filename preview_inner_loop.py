"""Preview images and expose their temporary ComfyUI view URLs."""

from __future__ import annotations

import json
import os
import random
from typing import Any
from urllib.parse import urlencode

import numpy as np
import torch
from PIL import Image
from PIL.PngImagePlugin import PngInfo

import folder_paths
from comfy.cli_args import args


NODE_NAME = "FanPreviewImageInnerLoop"
NODE_DISPLAY_NAME = "帆-预览图像（内循环用）"


def _tensor_to_pil(image: torch.Tensor) -> Image.Image:
    pixels = 255.0 * image.detach().cpu().numpy()
    pixels = np.clip(pixels, 0, 255).astype(np.uint8)
    return Image.fromarray(pixels)


def _view_url(filename: str, subfolder: str, file_type: str) -> str:
    query = urlencode(
        {
            "filename": filename,
            "type": file_type,
            "subfolder": subfolder,
        }
    )
    return f"/view?{query}"


class FanPreviewImageInnerLoop:
    CATEGORY = "image"
    DESCRIPTION = "Preview IMAGE batches in ComfyUI temp storage and return their image_urls for inner-loop workflows."
    FUNCTION = "preview"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("image_urls",)
    OUTPUT_NODE = True

    def __init__(self) -> None:
        self.output_dir = folder_paths.get_temp_directory()
        self.type = "temp"
        suffix = "".join(random.choice("abcdefghijklmnopqrstupvxyz") for _ in range(5))
        self.prefix_append = f"_temp_{suffix}"
        self.compress_level = 1

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "images": ("IMAGE",),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    def preview(
        self,
        images: torch.Tensor,
        prompt: dict[str, Any] | None = None,
        extra_pnginfo: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        filename_prefix = "ComfyUI" + self.prefix_append
        height = int(images[0].shape[0])
        width = int(images[0].shape[1])
        full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix,
            self.output_dir,
            width,
            height,
        )

        results: list[dict[str, str]] = []
        image_urls: list[str] = []
        for batch_number, image in enumerate(images):
            img = _tensor_to_pil(image)
            metadata = None
            if not args.disable_metadata:
                metadata = PngInfo()
                if prompt is not None:
                    metadata.add_text("prompt", json.dumps(prompt))
                if extra_pnginfo is not None:
                    for key, value in extra_pnginfo.items():
                        metadata.add_text(key, json.dumps(value))

            filename_with_batch_num = filename.replace("%batch_num%", str(batch_number))
            file = f"{filename_with_batch_num}_{counter:05}_.png"
            img.save(
                os.path.join(full_output_folder, file),
                pnginfo=metadata,
                compress_level=self.compress_level,
            )

            item = {
                "filename": file,
                "subfolder": subfolder,
                "type": self.type,
            }
            results.append(item)
            image_urls.append(_view_url(file, subfolder, self.type))
            counter += 1

        return {
            "ui": {"images": results},
            "result": (json.dumps(image_urls, ensure_ascii=False),),
        }

    @classmethod
    def IS_CHANGED(cls, images: torch.Tensor, **_: Any) -> float:
        return float("nan")


NODE_CLASS_MAPPINGS = {NODE_NAME: FanPreviewImageInnerLoop}
NODE_DISPLAY_NAME_MAPPINGS = {NODE_NAME: NODE_DISPLAY_NAME}
