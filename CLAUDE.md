# ComfyUI-Trusapien

A ComfyUI custom node pack with one node, `Trusapien Creative Validation`: an
image in, a heat map and the analysis metrics out. It is a client of the
Trusapien Creative Validation API and holds no logic of its own beyond that.
**Public repository** (MIT): nothing internal belongs in it.

## Status
- 2026-11-19: connected to the API (it was a placeholder that returned the input
  image and said "processed successfully"). Checked against a local copy of the
  service.
- 2026-11-22: **run inside a real, headless ComfyUI** (CPU only) against
  `tools/stub_service.py`, a stub that answers like the service. Two bugs found
  and fixed there (greyscale and bfloat16 frames crashed `to_png`), and one
  found by it (fp16 frames gave different PNG bytes, so the same image was paid
  for twice). See "Verified inside ComfyUI".
- 2026-11-22 (later): map choices checked against the result keys of the
  service's first real run (all nine are among them; labels unchanged). A map
  that is missing, listed but 404, or not an image, and an analysis with no
  maps, each stop the prompt with one `[Trusapien] ...` sentence; rerun inside
  ComfyUI, 18/18.
- 2026-11-22 (example): `trusapien_example_workflow.json` rewritten for the current
  node (LoadImage `example.png` -> node -> two previews, a Note about
  `TRUSAPIEN_API_KEY`, no key anywhere) and run inside ComfyUI against the stub
  with `run_in_comfyui.py --example`: heat map produced at the input size; 18/18
  still pass. `assets/workflow_demo.png` still shows the old placeholder workflow
  (no longer referenced by the README).
- 2026-11-22 (docs): README rewritten for users and checked claim by claim
  against the code (map choices = `MAPS`, batch limit, 300 s, error sentences,
  exactly what makes a rerun free); no service address, no vendor name. The
  three error sentences built from split literals were compared by hand.
  `PUBLISH.md` added: Kaan's registry release steps, checked against the
  registry docs and publish-node-action on that date.
- **Never run against the production API, nor against the real service with its
  analysis vendor.** No GPU, no browser UI.
- `DEFAULT_API_URL` (`https://creative-validation.trusapien.com`) is a proposed
  address, not a live one.

## Layout
- `trusapien_client.py`: the HTTP client. No ComfyUI, no torch. Upload, poll,
  read a result file, turn refusals into sentences.
- `trusapien_node.py`: tensors to PNG and back, the batch limit, the node class.
- `__init__.py`: the mappings ComfyUI scans for. Must stay at the root.
- `tools/`: development only, never imported by the node. `stub_service.py`
  (a stand-in for the API), `run_in_comfyui.py` (drives the node through a
  running ComfyUI's HTTP API; `--example` converts the saved UI-format example
  workflow to an API prompt with `workflow_to_prompt` and runs it),
  `comfyui_dev_nodes/` (two dev nodes that run
  needs: a tensor probe and a dtype/channel cast; symlink into a *test* ComfyUI).
- `tests/`: `pytest tests` (65 pass, 1 skip; `test_stub.py` runs the real
  client against the stub; `test_workflow.py` checks the example workflow's links,
  widget values against `INPUT_TYPES`, that no key is in it, and the converter;
  `test_packaging.py` checks pyproject.toml against
  requirements.txt and `USER_AGENT`, and skips on Python < 3.11 without `tomli`).
  `tests/pytest.ini` keeps pytest's
  root inside `tests/`; with it at the repository root pytest imports the root
  `__init__.py` as a package and its relative import fails.
- `pyproject.toml`: Comfy Registry metadata (field names from
  docs.comfy.org/registry/specifications). Node id `trusapien-creative-validation`,
  permanent once published; it, `PublisherId` and `Icon` are TODO(Kaan).
  `requirements.txt` lists exactly `[project].dependencies` (never torch: ComfyUI
  provides it). `.comfyignore` keeps `tests/`, `tools/`, `.github/` out of the
  registry archive (`comfy node pack` shows what ships).
- `.github/workflows/`: `test.yml` (pytest on 3.10 and 3.12), `publish.yml`
  (on a `v*` tag: checks tag == `v<version>`, runs the tests, then
  `Comfy-Org/publish-node-action@main` with the `REGISTRY_ACCESS_TOKEN` secret).
- `README.md`: for users (install, key, cost, reruns, node reference, errors).
  Every error sentence it quotes must match the code; change both together.
- `PUBLISH.md`: maintainer release steps (publisher, icon, token, secret,
  address, version, tag, verify, failures) and the before-first-publish
  checklist. Release steps live there, not here.

## Rules
- **Every image is one paid analysis.** Keep the idempotency key a hash of the
  image and the objectives, so a re-run reads the earlier result.
- **A failure raises.** The node must not return the input image with a status
  string when nothing was analysed: the workflow would look as if it had run.
- **The README describes what the node does today.** No inputs, outputs,
  certifications or hosting claims that are not true of this code and the
  service behind it.
- The key is read from `TRUSAPIEN_API_KEY` when the widget is empty; a typed key
  ends up in workflow files and image metadata, and the README says so.

## Gotchas
- Map names (`heat`, `fog`, `trust_heat`, ...) are the result-file names the API
  returns under `results.`. `MAPS` offers only names the service returned on its
  first real run (`KNOWN_RESULT_KEYS` in `tests/test_client.py`). The labels are
  stored in saved workflows: do not rename them. `Engagement` is
  `engagement_new_heat` (the `engagement_new` metric).
- Maps are named to the user by their `heatmap` label (`map_names`): in the
  missing-map sentence and in `metrics_json["maps"]`; a result file the node
  does not offer appears under its own name.
- `torch` is imported inside `validate_creative`, so the tests run without it
  using a numpy stand-in. That checks the node's logic, not torch; torch itself
  is checked by `tools/run_in_comfyui.py`.
- `to_png` rounds (it does not truncate) and always writes RGB: the PNG bytes are
  the idempotency key, and an 8-bit image must give the same bytes in float32
  and float16 (`--fp16-intermediates`) and with or without an alpha channel.
- The service's maps are JPEG at its own size; `to_array` resizes them to the
  input's size and returns float32.
- The example workflow is the browser's save format: `widgets_values` are
  positional, in `INPUT_TYPES` order (`heatmap`, `api_key`, `objectives_json`).
  Adding or reordering a widget input breaks it; `tests/test_workflow.py` says so.
  `/prompt` does not take that format; `run_in_comfyui.py --example` converts it.
- The version lives in two places: `pyproject.toml` and `USER_AGENT` in the
  client; `tests/test_packaging.py` checks they match. A release is a `v<version>`
  tag; `publish.yml` refuses any other tag.

## Verified inside ComfyUI
Run on 2026-11-22, headless, in a fresh empty directory outside the repo (`$D`):

- ComfyUI commit `4c2b826d74a1827f5cc4a706608fc4653ed12972` (master,
  2026-11-22), version 0.46.0, frontend package 1.59.11.
- Python 3.12.16 (uv-managed; the machine had no system Python), torch
  2.15.0+cpu, numpy 2.5.4, Pillow 13.0.0, requests 2.34.2, av 19.0.2. Linux x86_64.

```bash
uv python install 3.12
git clone https://github.com/comfyanonymous/ComfyUI $D/ComfyUI
uv venv --python 3.12 $D/venv
uv pip install --python $D/venv torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
uv pip install --python $D/venv -r $D/ComfyUI/requirements.txt -r requirements.txt
ln -s "$PWD" $D/ComfyUI/custom_nodes/ComfyUI-Trusapien
ln -s "$PWD/tools/comfyui_dev_nodes" $D/ComfyUI/custom_nodes/trusapien-dev-nodes
$D/venv/bin/python tools/stub_service.py --port 8765 &
(cd $D/ComfyUI && TRUSAPIEN_API_URL=http://127.0.0.1:8765 TRUSAPIEN_API_KEY=stub-key \
  $D/venv/bin/python main.py --cpu --listen 127.0.0.1 --port 8188) &
$D/venv/bin/python tools/run_in_comfyui.py --comfy http://127.0.0.1:8188 --stub http://127.0.0.1:8765
```

Also run with a second ComfyUI started with `--fp16-intermediates` on port 8189
(LoadImage then hands the node `torch.float16`), and with both against the same
stub: one file analysed by the float32 instance was not paid for again by the
fp16 one.

What it showed: the pack imports as a custom node (relative imports fine, no
"IMPORT FAILED"); `/object_info/TrusapienValidationNode` gives the declared
inputs, outputs and the nine map choices; `run_in_comfyui.py` passes 15/15
(18/18 since the map-failure steps were added, same ComfyUI commit and versions):
float32 `[B,H,W,3]` maps in 0..1 at the input size from half-size JPEGs; batches
of 1, 2, 8 give B maps and B analyses; 9 is refused with no request sent; RGBA
PNG, RGBA/grey/fp16/bf16/non-contiguous tensors work; the same image and
objectives again (node executed, not cached) is no new analysis; a missing map,
no maps at all, a listed map that 404s, a map that is not an image, and a 401
fail the prompt with the `[Trusapien] ...` sentence (a `RuntimeError` whose
traceback stops at the node, no Pillow or requests frames) and no output.

The example workflow (same commit and versions, fresh install, `example.png` from
ComfyUI's own `input/`): `run_in_comfyui.py --example` sends LoadImage ->
Trusapien (`Attention`, empty key, so `TRUSAPIEN_API_KEY` is used) -> two
PreviewImage (the Note is not sent); 2/2: the heat map preview is 768x768 like
`example.png` and differs from it; first run 1 new analysis, a rerun 0. The old
file, run the same way, fails at `original.jpeg` (404).

The stub (`tools/stub_service.py`) is what the client relies on, not the
service's full contract: upload with Idempotency-Key, `processing` for 1 s then
`done`, the nine `results.*` maps as JPEG at half size, the eleven metrics
(made up), `objectives_error`/`benchmarks`/`impact` always null. Modes: `--omit
MAP`, `--missing-file MAP` (listed, 404), `--corrupt MAP` (listed, not an image),
`--reject-all`, or `POST /_stub/mode` at runtime; `GET /_stub/stats`
counts analyses (distinct keys).

**Not done:** never against the production API or the real service (so not the
real ~20 s analysis time, real objectives/benchmarks, or real error bodies); no
GPU (the `.detach().cpu().float()` path is exercised on CPU tensors and a fake
in the unit tests only); no browser UI, no ComfyUI Manager or registry install,
no Windows portable build; `trusapien_example_workflow.json` was never opened in
the browser: `--example` converts it to an API prompt by hand (same nodes, links
and widget values), so how the frontend draws it (node sizes, the Note) is
unchecked.
