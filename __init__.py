"""
darkHUB Video to Base64
ComfyUI custom nodes for encoding media to Base64 and decoding Base64 back to images.
"""

from ._version import VERSION as __version__
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

WEB_DIRECTORY = "./web"

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
    "__version__",
]
