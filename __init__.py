"""ComfyUI node registrations for this custom-node package."""

# ComfyUI loads this package entry point only.  The multi-platform node below
# is the sole public node.  The old RH-only implementation remains on disk for
# reference/recovery but is deliberately not registered.
from .fan_wanxiang_image import (
    NODE_CLASS_MAPPINGS as WANXIANG_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as WANXIANG_NODE_DISPLAY_NAME_MAPPINGS,
)
from .preview_inner_loop import (
    NODE_CLASS_MAPPINGS as PREVIEW_INNER_LOOP_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as PREVIEW_INNER_LOOP_NODE_DISPLAY_NAME_MAPPINGS,
)

NODE_CLASS_MAPPINGS = {
    **WANXIANG_NODE_CLASS_MAPPINGS,
    **PREVIEW_INNER_LOOP_NODE_CLASS_MAPPINGS,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    **WANXIANG_NODE_DISPLAY_NAME_MAPPINGS,
    **PREVIEW_INNER_LOOP_NODE_DISPLAY_NAME_MAPPINGS,
}

# Expose the small frontend extension that supplies Chinese/icon labels to the
# Vue-node renderer while preserving every internal socket/widget name.  Those
# internal names are workflow serialization keys and must remain unchanged.
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
