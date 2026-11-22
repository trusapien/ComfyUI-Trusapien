"""Two development-only ComfyUI nodes for `tools/run_in_comfyui.py`. Not part of the pack.

Symlink this directory into a *test* ComfyUI's `custom_nodes/` next to the pack:

- `TrusapienDevProbe` reports what an IMAGE tensor really is (dtype, shape, range,
  device), so a script talking to ComfyUI over HTTP can check the node's output
  tensor and not only the PNG that SaveImage writes from it.
- `TrusapienDevCast` turns an IMAGE into the kinds ComfyUI's LoadImage does not
  produce but other nodes do: half precision, bfloat16, four or one channels, a
  non-contiguous view. Fed into the Trusapien node, it exercises the way frames
  are turned into PNG bytes.
"""

import torch


class TrusapienDevProbe:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"images": ("IMAGE",)}}

    RETURN_TYPES = ()
    FUNCTION = "probe"
    OUTPUT_NODE = True
    CATEGORY = "Trusapien/dev"

    def probe(self, images):
        values = images.float()
        return {
            "ui": {
                "probe": [
                    {
                        "dtype": str(images.dtype),
                        "shape": list(images.shape),
                        "min": float(values.min()),
                        "max": float(values.max()),
                        "device": str(images.device),
                        "contiguous": bool(images.is_contiguous()),
                    }
                ]
            }
        }


class TrusapienDevCast:
    MODES = ("fp16", "bf16", "rgba", "grey", "noncontiguous")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"images": ("IMAGE",), "mode": (list(cls.MODES),)}}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "cast"
    CATEGORY = "Trusapien/dev"

    def cast(self, images, mode):
        if mode == "fp16":
            out = images.to(torch.float16)
        elif mode == "bf16":
            out = images.to(torch.bfloat16)
        elif mode == "rgba":
            alpha = torch.full_like(images[..., :1], 0.5)
            out = torch.cat([images, alpha], dim=-1)
        elif mode == "grey":
            out = images.mean(dim=-1, keepdim=True)
        else:  # a view with the channels last in shape but not in memory
            out = images.permute(0, 3, 1, 2).contiguous().permute(0, 2, 3, 1)
        return (out,)


NODE_CLASS_MAPPINGS = {"TrusapienDevProbe": TrusapienDevProbe, "TrusapienDevCast": TrusapienDevCast}
NODE_DISPLAY_NAME_MAPPINGS = {
    "TrusapienDevProbe": "Trusapien dev: probe IMAGE",
    "TrusapienDevCast": "Trusapien dev: cast IMAGE",
}
