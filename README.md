# ComfyUI-Trusapien

A ComfyUI node that sends an image to the [Trusapien](https://trusapien.com) Creative Validation API and brings back a predicted-attention heat map and the analysis metrics, so an ad creative can be checked inside the workflow that made it.

> **Private beta.** The node needs a Trusapien API key, and keys are not self-serve yet. Ask for one at [trusapien.com](https://trusapien.com) and mention ComfyUI.

```text
[ Sampler / Load Image ] ──► [ Trusapien Creative Validation ] ──┬──► heatmap  (IMAGE)
                                                                 ├──► image    (IMAGE, unchanged)
                                                                 ├──► metrics_json (STRING)
                                                                 └──► status   (STRING)
```

## What it does

- Uploads each image in the batch as a PNG and waits for the analysis, up to five minutes.
- Returns the chosen heat map at the input image's size, the untouched image, and the metrics as JSON.
- **The same image is analysed once.** Running a workflow again with an unchanged image reads the earlier result; it is not charged a second time.
- Stops the workflow with a readable error when there is no key, the key is refused, or the analysis fails. It never passes the image on as if it had been analysed.

Each image is one paid analysis. A batch is limited to 8 images.

## Node: `Trusapien Creative Validation`

### Inputs

| Name | Type | Required | Default | What it is |
| --- | --- | --- | --- | --- |
| `image` | `IMAGE` | yes | | The image, or a batch of up to 8. |
| `heatmap` | choice | yes | `Attention` | Which map to return: `Attention`, `Fog`, `Cognitive Demand`, `Engagement`, `Memory`, `Clarity`, `Trust`, `Intent`, `Avoidance`. |
| `api_key` | `STRING` | no | empty | Your key. Leave empty to use the `TRUSAPIEN_API_KEY` environment variable. |
| `objectives_json` | `STRING` | no | empty | What the creative is for (see below). With it, the result also carries benchmarks and an impact score. |

### Outputs

| Name | Type | What it is |
| --- | --- | --- |
| `heatmap` | `IMAGE` | The chosen map, one per input image, at the input's size. |
| `image` | `IMAGE` | The input, unchanged, for chaining. |
| `metrics_json` | `STRING` | `validation_id`, `metrics`, `objectives`, `benchmarks`, `impact`, and the names of the maps the analysis produced. A list when the batch has more than one image. |
| `status` | `STRING` | For example `Analysed 1 image.` |

Not every analysis produces every map. If the one you chose is missing, the error names the maps that exist.

### Objectives

Benchmarks and the impact score are read against what the creative is for. `objectives_json` takes all six fields or none:

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

The accepted values are a fixed set and not every combination exists; the list is not published here yet. A combination that is not accepted does not cost the analysis: the metrics and maps still come back, with the reason under `objectives_error`.

## Your API key

Prefer the environment variable, set before ComfyUI starts:

```bash
export TRUSAPIEN_API_KEY=cv_...
```

A key typed into the node is saved in the workflow file and in the metadata of the images ComfyUI writes. If you share either, you share the key.

## Install

**ComfyUI Manager:** search for `ComfyUI-Trusapien`, install, restart ComfyUI.

**By hand:**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/trusapien/ComfyUI-Trusapien.git
pip install -r ComfyUI-Trusapien/requirements.txt
```

On the Windows portable build:

```cmd
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-Trusapien\requirements.txt
```

Restart ComfyUI. `trusapien_example_workflow.json` is a three-node workflow to start from: Load Image, the Trusapien node, Preview Image.

## Errors you may see

| Message | What to do |
| --- | --- |
| `No Trusapien API key` | Set `TRUSAPIEN_API_KEY` or fill `api_key`. |
| `The Trusapien API key was not recognised` | Check the key; ask for a new one if it was replaced. |
| `The image was not accepted: ...` | The reason follows (format or size). |
| `The analysis did not finish in 300 seconds` | It is still running. Queue the workflow again to pick up the result without a second charge. |
| `Too many of your validations are still being processed` | Wait for the running ones to finish. |
| `The Trusapien API could not be reached` | Network, or the service is down. |

## Your data

Images you send are stored by Trusapien together with their results for 30 days, then deleted. The analysis itself is performed by a third-party provider that Trusapien passes the image to; its copy is deleted at the same time. Do not send images you are not allowed to share with a processor.

## Development

```bash
pip install requests pillow numpy pytest
pytest tests                 # no ComfyUI or torch needed
```

`tests/test_live.py` runs against a real API when `TRUSAPIEN_TEST_API_URL` and `TRUSAPIEN_TEST_API_KEY` are set. `TRUSAPIEN_API_URL` points the node itself at another address.

## License

MIT. See [`LICENSE`](LICENSE).
