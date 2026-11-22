"""The ComfyUI node: an image in, its heat map and its scores out."""

import io
import json

import numpy as np
from PIL import Image

from .trusapien_client import MAPS, Client, TrusapienError, parse_objectives, resolve_key, summary

#: Every image is one paid analysis, so a batch is bounded.
MAX_BATCH = 8


def _as_numpy(frame) -> "np.ndarray":
    """A frame as a float32 numpy array, from a torch tensor wherever it lives.

    `.numpy()` alone fails on a tensor on the GPU, one that requires grad, and
    one in bfloat16 (all of which other nodes hand on); so detach, move, widen.
    Duck-typed, so this module does not import torch.
    """
    if hasattr(frame, "detach"):
        frame = frame.detach()
    if hasattr(frame, "cpu"):
        frame = frame.cpu()
    if hasattr(frame, "float") and hasattr(frame, "numpy"):
        frame = frame.float().numpy()
    return np.asarray(frame, dtype=np.float32)


def to_png(frame) -> bytes:
    """One ComfyUI image ([H, W, C], floats 0..1) as RGB PNG bytes.

    One channel is taken as grey and four as RGB plus alpha, which is dropped as
    ComfyUI's own LoadImage does.

    Values are rounded, not truncated: the bytes are the idempotency key, and an
    8-bit image must give the same bytes whether ComfyUI holds it in float32 or
    float16 (`--fp16-intermediates`); truncated, half of the levels came out one
    lower in float16 and the same image was paid for twice.
    """
    array = _as_numpy(frame)
    if array.ndim == 2:
        array = array[:, :, None]
    if array.ndim != 3 or array.shape[2] not in (1, 2, 3, 4):
        raise TrusapienError(
            f"The image has shape {list(array.shape)}; expected height x width x 1 to 4 channels."
        )
    if array.shape[2] in (1, 2):  # grey, or grey plus alpha
        array = np.repeat(array[:, :, :1], 3, axis=2)
    elif array.shape[2] == 4:
        array = array[:, :, :3]
    array = np.clip(np.round(np.nan_to_num(array) * 255.0), 0, 255)
    buffer = io.BytesIO()
    Image.fromarray(array.astype(np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def to_array(content: bytes, size) -> "np.ndarray":
    """Result file bytes (JPEG, at the service's own size) as a [H, W, 3] float32 array at `size`."""
    try:
        picture = Image.open(io.BytesIO(content))
        picture.load()
    except Exception:
        raise TrusapienError("The heat map the API returned could not be read as an image.") from None
    picture = picture.convert("RGB")
    if picture.size != size:
        picture = picture.resize(size, Image.LANCZOS)  # Image.Resampling needs Pillow 9.1
    return np.ascontiguousarray(np.asarray(picture), dtype=np.float32) / np.float32(255.0)


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
