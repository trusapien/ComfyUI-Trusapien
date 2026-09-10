# ComfyUI-Trusapien

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![ComfyUI Registry](https://img.shields.io/badge/ComfyUI-Custom--Node-purple.svg)](https://github.com/comfyanonymous/ComfyUI)
[![Platform Status](https://img.shields.io/badge/API-Private%20Beta-orange.svg)](https://trusapien.com)
[![ISO 27001 Certified](https://img.shields.io/badge/Security-ISO%2027001-green.svg)](https://trusapien.com)

Official ComfyUI custom nodes for **[Trusapien](https://trusapien.com)** — bringing enterprise-grade consumer-neuroscience models, attention heatmaps, and campaign impact scoring directly into your generative workflows.

---

> 🔒 **Private Beta Access Required**
> 
> The Trusapien API is currently in gated private beta. You can install and test this custom node today; however, running live inference requires an API key. 
> 
> 👉 **[Join the Trusapien Waitlist](https://trusapien.com)** — *Mention "ComfyUI" in your submission for priority developer onboarding.*

---

## Overview

**Trusapien Creative Validation** allows creators, marketing teams, and automation engineers to validate generated campaign assets in real time inside ComfyUI. Instead of exporting images and manually analyzing them, you can evaluate predicted human visual attention and impact scores directly within your generation pipeline.

```text
[ SDXL / Flux Sampler ] ──► [ Trusapien Creative Validation ] ──┬──► [ Visual Attention Heatmap ]
                                                                └──► [ Impact & Objectives Score ]

```

---

## Key Capabilities

* **Predicted Attention Heatmaps**: Generate visual overlays showing where human gaze lands during the first 3 seconds of exposure.
* **Campaign Objective Scoring**: Measure asset alignment against preset marketing and brand guidelines.
* **Non-Destructive Tensor Pass-Through**: The node outputs both the original image tensor and the analyzed heatmap overlay for seamless workflow chaining.
* **Enterprise Security**: Grounded in ISO 27001 and ISO 27701 certified architecture.

---

## Node Reference

### `Trusapien Creative Validation`

#### Inputs

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `image` | `IMAGE` | Yes | — | Image tensor output from any sampler, loader, or upscale node. |
| `api_key` | `STRING` | Yes | `""` | Your Trusapien platform API key (e.g., `tru_live_...`). |
| `analysis_mode` | `COMBO` | No | `Attention Heatmap` | Select evaluation type: `Attention Heatmap`, `Impact Score`, or `Full Suite`. |
| `target_audience` | `STRING` | No | `General` | Optional demographic or market filter for visual attention modeling. |

#### Outputs

| Output Name | Type | Description |
| --- | --- | --- |
| `IMAGE` | `IMAGE` | Visual attention heatmap overlay rendered as an image tensor. |
| `METRICS_JSON` | `STRING` | JSON string containing numeric scores (Impact Score, Attention Index, Clarity Score). |
| `STATUS` | `STRING` | Execution status or detailed error response from the Trusapien API. |

---

## Installation

### Method 1: ComfyUI Manager (Recommended)

1. Open **ComfyUI Manager** in your browser interface.
2. Search for `ComfyUI-Trusapien`.
3. Click **Install**.
4. Restart your ComfyUI server.

### Method 2: Manual Git Installation

Run the following commands in your terminal:

```bash
# Navigate to your ComfyUI custom nodes folder
cd ComfyUI/custom_nodes/

# Clone the repository
git clone [https://github.com/trusapien/ComfyUI-Trusapien.git](https://github.com/trusapien/ComfyUI-Trusapien.git)

# Install Python dependencies
cd ComfyUI-Trusapien
pip install -r requirements.txt

```

Restart your ComfyUI server after installation completes.

---

## Quickstart Workflow

1. Open ComfyUI and double-click the canvas.
2. Search for **Trusapien Creative Validation**.
3. Connect the `IMAGE` output of your `KSampler` or `Load Image` node to the `image` input of the Trusapien node.
4. Enter your API key into the `api_key` field.
5. Connect the `IMAGE` output of the Trusapien node to a `Preview Image` or `Save Image` node.
6. Click **Queue Prompt**.

---

## Troubleshooting & Common Issues

This message appears when the `api_key` field is empty or contains an unverified key. Ensure your key starts with `tru_live_` or `tru_test_`. If you do not have a key, request access at [trusapien.com](https://trusapien.com).

Your ComfyUI Python environment is missing required dependencies. Run:

```bash
pip install -r requirements.txt

```

If using a standalone ComfyUI portable environment on Windows, use:

```cmd
python_embedded\python.exe -m pip install -r custom_nodes\ComfyUI-Trusapien\requirements.txt

```

---

## Security & Enterprise Compliance

* **Data Privacy**: Input images sent to the Trusapien API are processed securely in ISO 27001 certified environments and are never used to train base models without consent.
* **Region Hosting**: Supports enterprise regional hosting requirements (EU / North America).
* Learn more at the [Trusapien Trust Centre](https://trusapien.com).

---

## License

Distributed under the MIT License. See [`LICENSE`](https://www.google.com/search?q=LICENSE) for details.

```
