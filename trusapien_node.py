"""The ComfyUI node: an image in, its heat map and its scores out."""

import io
import json

import numpy as np
from PIL import Image

from .trusapien_client import MAPS, Client, TrusapienError, parse_objectives, resolve_key, summary

#: Every image is one paid analysis, so a batch is bounded.
MAX_BATCH = 8


def to_png(frame) -> bytes:
    """One ComfyUI image ([H, W, C], floats 0..1) as PNG bytes."""
    array = np.clip(np.asarray(frame.cpu().numpy() if hasattr(frame, "cpu") else frame) * 255.0, 0, 255)
    buffer = io.BytesIO()
    Image.fromarray(array.astype(np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def to_array(content: bytes, size) -> "np.ndarray":
    """Result file bytes as a [H, W, 3] float array, at the input image's size."""
    picture = Image.open(io.BytesIO(content)).convert("RGB")
    if picture.size != size:
        picture = picture.resize(size, Image.LANCZOS)
    return np.asarray(picture).astype(np.float32) / 255.0


class TrusapienValidationNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "heatmap": (list(MAPS), {"default": "Attention"}),
            },
            "optional": {
                "api_key": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "Leave empty to use the TRUSAPIEN_API_KEY environment variable. "
                        "A key typed here is saved in the workflow file.",
                    },
                ),
                "objectives_json": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "Optional. All six objectives as JSON; with them the result "
                        "carries benchmarks and an impact score.",
                    },
                ),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("heatmap", "image", "metrics_json", "status")
    FUNCTION = "validate_creative"
    CATEGORY = "Trusapien"

    def validate_creative(self, image, heatmap="Attention", api_key="", objectives_json=""):
        import torch

        try:
            client = Client(resolve_key(api_key))
            objectives = parse_objectives(objectives_json)
            if image.shape[0] > MAX_BATCH:
                raise TrusapienError(
                    f"{image.shape[0]} images in one batch. Each image is one paid analysis; "
                    f"send at most {MAX_BATCH} at a time."
                )
            maps, results = [], []
            for index in range(image.shape[0]):
                frame = image[index]
                size = (int(frame.shape[1]), int(frame.shape[0]))
                validation = client.validate(to_png(frame), objectives, file_name=f"comfyui-{index + 1}.png")
                content = client.asset(validation, MAPS[heatmap])
                if content is None:
                    raise TrusapienError(
                        f"The analysis has no {heatmap} map for this image. "
                        f"Maps it does have: {', '.join(summary(validation)['maps']) or 'none'}."
                    )
                maps.append(torch.from_numpy(to_array(content, size)))
                results.append(summary(validation))
        except TrusapienError as error:
            # Raised, not returned: a workflow that carried on with the untouched
            # image would look as if it had been analysed.
            raise RuntimeError(f"[Trusapien] {error}") from None

        metrics = results[0] if len(results) == 1 else results
        status = f"Analysed {len(results)} image{'s' if len(results) != 1 else ''}."
        return (torch.stack(maps), image, json.dumps(metrics, indent=2), status)
