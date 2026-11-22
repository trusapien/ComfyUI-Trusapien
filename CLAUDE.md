# ComfyUI-Trusapien

A ComfyUI custom node pack with one node, `Trusapien Creative Validation`: an
image in, a heat map and the analysis metrics out. It is a client of the
Trusapien Creative Validation API and holds no logic of its own beyond that.
**Public repository** (MIT): nothing internal belongs in it.

## Status
- 2026-11-19: connected to the API (it was a placeholder that returned the input
  image and said "processed successfully"). Checked against a local copy of the
  service; **never run inside ComfyUI, and never against the production API**.
- `DEFAULT_API_URL` (`https://creative-validation.trusapien.com`) is a proposed
  address, not a live one.

## Layout
- `trusapien_client.py`: the HTTP client. No ComfyUI, no torch. Upload, poll,
  read a result file, turn refusals into sentences.
- `trusapien_node.py`: tensors to PNG and back, the batch limit, the node class.
- `__init__.py`: the mappings ComfyUI scans for. Must stay at the root.
- `tests/`: `pytest tests` (23 pass, 1 skip). `tests/pytest.ini` keeps pytest's
  root inside `tests/`; with it at the repository root pytest imports the root
  `__init__.py` as a package and its relative import fails.

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
  returns under `results.`.
- `torch` is imported inside `validate_creative`, so the tests run without it
  using a numpy stand-in. That checks the node's logic, not torch.
- The version lives in two places: `pyproject.toml` and `USER_AGENT` in the client.
