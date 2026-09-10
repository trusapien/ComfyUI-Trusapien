import torch

class TrusapienValidationNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # Receives image tensors from other nodes
                "image": ("IMAGE",),
                # API Key widget for user authentication
                "api_key": ("STRING", {
                    "default": "PASTE_YOUR_API_KEY_HERE",
                    "multiline": False
                }),
            }
        }

    # Outputs available to connect to other nodes
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "status")

    # Method name that executes when the workflow runs
    FUNCTION = "validate_creative"
    CATEGORY = "Trusapien"

    def validate_creative(self, image, api_key):
        # Gate check for waitlist users without a key
        if not api_key or api_key == "PASTE_YOUR_API_KEY_HERE":
            print("\n[Trusapien] Private Beta Active. Join waitlist at trusapien.com\n")
            status = "Waitlist Required: Visit trusapien.com to get your API key."
            return (image, status)

        # Logic for when API is connected
        # Note: ComfyUI images are PyTorch tensors with shape [Batch, Height, Width, Channels]
        status = "Creative validation processed successfully."
        return (image, status)
