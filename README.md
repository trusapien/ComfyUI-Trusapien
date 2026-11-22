# ComfyUI-Trusapien

A ComfyUI node that sends an image to the [Trusapien](https://trusapien.com) Creative Validation API and brings back a predicted-attention heat map and the analysis metrics, so an ad creative can be checked inside the workflow that made it.

You need a Trusapien API key (see [Your API key](#your-api-key)). Every image the node sends is one paid analysis (see [Cost](#cost)).

```text
[ Sampler / Load Image ] ──► [ Trusapien Creative Validation ] ──┬──► heatmap  (IMAGE)
                                                                 ├──► image    (IMAGE, unchanged)
                                                                 ├──► metrics_json (STRING)
                                                                 └──► status   (STRING)
```

## What it does

- Sends each image in the batch to the API as a PNG, one after another, and waits up to 300 seconds for each analysis.
- Returns the heat map you chose, resized to the input image's size; the input image, unchanged; and the analysis as JSON.
- Stops the workflow with an error that starts with `[Trusapien]` when there is no key, the key is refused, a map is missing, or the analysis fails. It never passes the image on as if it had been analysed.

## Cost

- **Every image is one paid analysis.** A batch of N images is N analyses.
- A batch holds at most **8** images. A larger batch is refused before anything is sent.

### Running the same image again

The node asks for each analysis under a key made from the image and the objectives (a hash of both). The service gives the earlier result for a key it has seen, so **the same image with the same objectives is analysed once**: queueing it again reads the earlier result and is not charged a second time. Exactly:

| You run again with... | Result |
| --- | --- |
| The same image, the same objectives | The earlier result. No new analysis. |
| The same image and objectives, another `heatmap` choice | The earlier result. No new analysis. The map choice is not part of the key. |
| The same objectives written differently (spacing, field order, extra fields) | The earlier result. Only the six fields' values count. |
| A different value in any objective, or objectives added or removed | A new analysis. |
| Any pixel changed (after the image is converted to 8-bit RGB; alpha is dropped) | A new analysis. |
| An image whose earlier analysis ended in an error, or whose result has expired | A new analysis: the node asks afresh. |

Results are kept for 30 days. After that, the same image is a new analysis.

## Install

**ComfyUI Manager:** once the pack is published on the Comfy Registry, search for `ComfyUI-Trusapien`, install it, and restart ComfyUI.

**comfy-cli:** once the pack is published on the Comfy Registry:

```bash
comfy node install trusapien-creative-validation
```

**By hand:**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/trusapien/ComfyUI-Trusapien.git
pip install -r ComfyUI-Trusapien/requirements.txt
```

On the Windows portable build, install the requirements with ComfyUI's own Python:

```cmd
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-Trusapien\requirements.txt
```

Restart ComfyUI. The node is under **Trusapien → Trusapien Creative Validation**.

## Your API key

There is no self-serve sign-up. Request a key from Trusapien at [trusapien.com](https://trusapien.com) and mention ComfyUI.

Give it to the node through the environment variable `TRUSAPIEN_API_KEY`, set before ComfyUI starts, and leave the node's `api_key` field empty:

```bash
export TRUSAPIEN_API_KEY=your-key
```

A key typed into `api_key` is used instead of the environment variable, and it is **saved in the workflow file and in the metadata of the PNG images ComfyUI writes** (they embed the workflow). Anyone you share either with has your key.

## Node: `Trusapien Creative Validation`

### Inputs

| Name | Type | Required | Default | What it is |
| --- | --- | --- | --- | --- |
| `image` | `IMAGE` | yes | | The image, or a batch of up to 8. |
| `heatmap` | choice | yes | `Attention` | Which map to return: `Attention`, `Fog`, `Cognitive Demand`, `Engagement`, `Memory`, `Clarity`, `Trust`, `Intent`, `Avoidance`. |
| `api_key` | `STRING` | no | empty | Your key. Leave empty to use the `TRUSAPIEN_API_KEY` environment variable. |
| `objectives_json` | `STRING` | no | empty | What the creative is for (see [Objectives](#objectives)). |

### Outputs

| Name | Type | What it is |
| --- | --- | --- |
| `heatmap` | `IMAGE` | The chosen map, one per input image, at the input's size. |
| `image` | `IMAGE` | The input, unchanged, for chaining. |
| `metrics_json` | `STRING` | The analysis as JSON (below). A list, one entry per image, when the batch has more than one image. |
| `status` | `STRING` | `Analysed 1 image.`, `Analysed 2 images.`, ... |

Not every analysis has to produce every map. If the one you chose is missing, the error names the maps the analysis does have.

### `metrics_json`

```json
{
  "validation_id": "...",
  "metrics": { "...": "..." },
  "objectives": null,
  "objectives_error": null,
  "benchmarks": null,
  "impact": null,
  "maps": ["Attention", "Fog", "..."]
}
```

- `validation_id`: the analysis's id at the API.
- `metrics`: passed on exactly as the service returns it. It may contain `focus`, `clarity`, `cognitive_demand`, `engagement`, `engagement_new`, `memory`, `trust`, `intent`, `avoidance`, `focus_first_two`, `focus_last_two`.
- `objectives`, `objectives_error`, `benchmarks`, `impact`: as the service returns them (see [Objectives](#objectives)).
- `maps`: the maps this analysis has, by their `heatmap` name; a map the node does not offer appears under its own name.

### Objectives

`benchmarks` and `impact` are read against what the creative is for. `objectives_json` takes all six fields, each non-empty, or nothing:

```json
{
  "purpose": "...",
  "industry_category": "...",
  "industry_subcategory": "...",
  "usecase_category": "...",
  "usecase_subcategory": "...",
  "platform": "..."
}
```

The accepted values are a fixed set; the list is not published here yet. When the service does not accept the objectives, it gives the reason in `objectives_error`; the node does not stop on it and returns the map and metrics it received.

## Example workflow

[`trusapien_example_workflow.json`](trusapien_example_workflow.json) is a workflow in ComfyUI's save format; open it in ComfyUI. It holds:

- **Load Image** with `example.png` (the sample image in ComfyUI's own `input/` folder; pick your own),
- **Trusapien Creative Validation** set to `Attention`, with `api_key` and `objectives_json` empty, so the key comes from `TRUSAPIEN_API_KEY`,
- two **Preview Image** nodes, "Heat map" and "Image",
- a **Note** about the key and the cost.

Queueing it is one analysis; queueing it again with the same image is none.

## Errors you may see

Every error stops the prompt and starts with `[Trusapien]`.

| Message | What to do |
| --- | --- |
| `No Trusapien API key. Set the TRUSAPIEN_API_KEY environment variable ...` | Set `TRUSAPIEN_API_KEY` and restart ComfyUI, or fill `api_key`. |
| `The Trusapien API key was not recognised.` | Check the key; ask for a new one if it was replaced. |
| `The image was not accepted: ...` | The reason follows (format or size). |
| `N images in one batch. Each image is one paid analysis; send at most 8 at a time.` | Split the batch. Nothing was sent. |
| `The image has shape [...]; expected height x width x 1 to 4 channels.` | The node feeding `image` gives frames that are not height × width × channels; check what is connected. |
| `objectives_json is not valid JSON.` | Fix the JSON, or empty the field. |
| `objectives_json needs all six fields; missing: ...` | Add the fields named. |
| `The analysis did not finish in 300 seconds. It is still running; queue the workflow again to pick up the result without a second charge.` | Queue it again later. |
| `Too many of your validations are still being processed. Try again shortly.` | Wait for the running ones to finish. |
| `The analysis has no ... map for this image. Maps it does have: ...` | Pick one of the maps named. Queueing again reads the same analysis. |
| `The analysis lists a ... map, but it could not be downloaded. ...` | Queue it again; the analysis is not charged again. |
| `The ... map the API returned could not be read as an image.` | Queue it again; if it persists, tell Trusapien. |
| `The creative could not be analysed. (...)` | The analysis failed; the service's own message may appear instead, with its code in brackets. Queueing again asks afresh. |
| `The Trusapien API answered with an error: ...` | The API's reason follows. |
| `The Trusapien API could not be reached: ...` | Network, or the service is down. |

## Service address

The pack sets the address of the Trusapien API. To point the node at another one (a test deployment, or a local stand-in such as `tools/stub_service.py` while developing), set `TRUSAPIEN_API_URL` before ComfyUI starts:

```bash
export TRUSAPIEN_API_URL=http://127.0.0.1:8765
```

## Your data

Each image you run is uploaded to the Trusapien API, and Trusapien passes it to a third-party provider that performs the analysis. Results are kept for 30 days. Do not send images you are not allowed to share with a processor.

## Not supported yet

- Video input. The node takes still images (`IMAGE`) only.

## Development

```bash
pip install -r requirements.txt pytest
pip install tomli            # only on Python < 3.11, for tests/test_packaging.py (it skips without it)
pytest tests                 # no ComfyUI or torch needed
```

`tests/test_live.py` runs against a real API when `TRUSAPIEN_TEST_API_URL` and `TRUSAPIEN_TEST_API_KEY` are set; each run is one analysis.

`tools/` is for development and is not imported by the node:

- `tools/stub_service.py` answers like the API (it analyses nothing) and can be told to fail in specific ways.
- `tools/run_in_comfyui.py` drives the node through a running ComfyUI's HTTP API against the stub; `--example` runs the example workflow.
- `tools/comfyui_dev_nodes/` holds two helper nodes the harness needs, for a test ComfyUI only.

The node has been run inside a headless ComfyUI (CPU) against that stub, not against the production service. The exact setup is in [`CLAUDE.md`](CLAUDE.md) ("Verified inside ComfyUI").

## License

MIT. See [`LICENSE`](LICENSE).
