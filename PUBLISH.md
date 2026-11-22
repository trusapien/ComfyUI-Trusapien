# Publishing to the Comfy Registry

Maintainer steps for releasing ComfyUI-Trusapien on the [Comfy Registry](https://registry.comfy.org). Each step ends with something you can check.

Sources, read 2026-11-22: [docs.comfy.org/registry/publishing](https://docs.comfy.org/registry/publishing), [docs.comfy.org/registry/specifications](https://docs.comfy.org/registry/specifications), the [publish-node-action README](https://github.com/Comfy-Org/publish-node-action) and its `action.yml`. If they have changed since, they win over this file.

## Before the first publish

- [ ] **The node has run once against the production API with a real key.** Not done yet: so far it has only run against `tools/stub_service.py` (see CLAUDE.md, "Verified inside ComfyUI"). Each command below is one paid analysis:
  ```bash
  TRUSAPIEN_TEST_API_URL=https://<real address> TRUSAPIEN_TEST_API_KEY=<key> pytest tests/test_live.py
  ```
  Then, in a ComfyUI started with `TRUSAPIEN_API_KEY` set (and `TRUSAPIEN_API_URL` too, until step 5 is done), open `trusapien_example_workflow.json` and queue it. A heat map should appear. Queue it again: the service should show no second analysis.
- [ ] `DEFAULT_API_URL` in `trusapien_client.py` is the real public HTTPS address (step 5).
- [ ] The node id, `name = "trusapien-creative-validation"` in `pyproject.toml`, is the one you want. It appears in registry URLs and in `comfy node install <id>`, and the publishing page calls it "immutable after creation".
- [ ] `PublisherId` and `Icon` are filled in (steps 1–2), and `REGISTRY_ACCESS_TOKEN` is a repository secret (steps 3–4).
- [ ] The GitHub repository is public, and the URLs under `[project.urls]` in `pyproject.toml` open.
- [ ] The archive holds only the node. Run `comfy node pack` and check that `tests/`, `tools/` and `.github/` are not in it (`.comfyignore` excludes them).
- [ ] README.md has been re-read against the live service. Every claim in it must still be true.

## 1. Create the publisher

1. Sign in at <https://registry.comfy.org> and create a publisher.
2. Your publisher id is the part after `@` on the publisher's profile page. It is globally unique and cannot be changed later: it is part of the node's URL.
3. In `pyproject.toml`, set `[tool.comfy] PublisherId` to exactly that id (it is `"trusapien"` now) and remove its `TODO(Kaan)` comment.

Check: the profile page shows `@<PublisherId>`, character for character.

## 2. Icon (and banner, if wanted)

In `[tool.comfy]`:

- `Icon = "https://..."`: a public URL to an SVG, PNG, JPG or GIF. The specification asks for a square image of at most 400 × 400 px; the `comfy node init` template on the publishing page says 800 × 400. A square 400 × 400 image meets both.
- `Banner = "https://..."` (optional): SVG, PNG, JPG or GIF, 21:9.

Check: each URL opens the image in a private browser window, with no sign-in.

## 3. Create a publishing API key

1. Go to <https://registry.comfy.org/nodes> and select the publisher.
2. Create an API key and give it a name.
3. Copy it now. If it is lost, create a new one (and replace the secret in step 4).

This key is only for publishing to the registry.

## 4. Add the key to GitHub

In the GitHub repository: **Settings → Secrets and variables → Actions → New repository secret**.

- Name: `REGISTRY_ACCESS_TOKEN`
- Value: the key from step 3

Check: `REGISTRY_ACCESS_TOKEN` is listed under **Repository secrets**. `.github/workflows/publish.yml` reads that name.

## 5. Set the real service address

When the service's public HTTPS address exists:

1. Set `DEFAULT_API_URL` in `trusapien_client.py` to it.
2. Update the CLAUDE.md line saying that `DEFAULT_API_URL` is a proposed address.
3. Run `pytest tests`.

`TRUSAPIEN_API_URL` still overrides the address.

Check: `pytest tests` passes, and the production run in the checklist above uses this address without `TRUSAPIEN_API_URL`.

## 6. Set the version

The version is in two places, and they must match:

- `version` under `[project]` in `pyproject.toml` (semantic `X.Y.Z`), and
- `USER_AGENT = "ComfyUI-Trusapien/X.Y.Z"` in `trusapien_client.py`.

Change both, run `pytest tests`, and merge to `main`.

Check: `tests/test_packaging.py::test_version_matches_user_agent` passes. It fails if the two differ.

## 7. Tag and push

On the merged commit on `main`:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

The tag has to be `v` followed by the `pyproject.toml` version exactly. The push starts `.github/workflows/publish.yml`, which runs two jobs:

1. **Check tag and run tests.** It fails unless the tag equals `v<version>`, then runs `pytest tests` on Python 3.12.
2. **Publish Custom Node to registry.** It runs `Comfy-Org/publish-node-action@main` with the secret. The action installs the latest `comfy-cli` and runs `comfy node publish --token ...`, which publishes the version in `pyproject.toml`.

The docs' example workflow publishes on every push to `main` that changes `pyproject.toml`. This repository publishes on a `v*` tag instead, so a release is a deliberate step.

## 8. Verify

- [ ] The Actions run is green, and the publish step's log says the version was published, with a link.
- [ ] `https://registry.comfy.org/<PublisherId>/trusapien-creative-validation` shows the new version, the description and the icon.
- [ ] A clean install works. Use a new, empty directory and a fresh Python 3.10+ virtual environment:
  ```bash
  pip install comfy-cli
  comfy install                 # choose the CPU option if there is no GPU
  comfy node install trusapien-creative-validation
  comfy launch
  ```
  (`comfy install --help` and `comfy launch --help` show the flags for a workspace directory and for `--cpu`.)
  - The startup log lists the pack with no `IMPORT FAILED`.
  - `curl http://127.0.0.1:8188/object_info/TrusapienValidationNode` lists the inputs and the nine `heatmap` choices.
  - The installed folder under `custom_nodes/` has no `tests/` or `tools/`.
- [ ] The installed copy runs. From a checkout of this repository, start the stub (`python tools/stub_service.py --port 8765`), launch the clean ComfyUI with `TRUSAPIEN_API_URL=http://127.0.0.1:8765 TRUSAPIEN_API_KEY=stub-key`, and run `python tools/run_in_comfyui.py --comfy http://127.0.0.1:8188 --stub http://127.0.0.1:8765 --example`. It should report 2/2.
- [ ] ComfyUI Manager finds `ComfyUI-Trusapien` when you search for it.

## If the workflow fails

Open the failed run in **Actions** and see which job failed.

- **Check tag and run tests failed.** Nothing was published.
  - Tag mismatch: push the right tag (`v` + the `pyproject.toml` version). If the wrong tag should go, delete it with `git push origin --delete <tag>`; that is safe here because nothing was published from it.
  - Test failure: fix it on `main`, bump the version (step 6) and push the new tag. Do not move the old tag to the fixed commit.
- **Publish Custom Node failed, and the registry page does not show the version** (for example a missing or wrong secret, or a network error):
  - Fix the cause (for example replace the secret).
  - Then either use **Re-run failed jobs** on that run, or **Run workflow** and choose the same tag under "Use workflow from". The workflow refuses to run on a branch.
- **The registry already shows that version, or the fix needs a code change:** bump to the next version (step 6) and tag again. The registry docs do not say that the same version can be published twice, so do not rely on it. Never move or re-push a tag that has been published.

Fallback, if Actions is unavailable: `comfy node publish` from a clean checkout of the tag publishes the same way, and asks for the key from step 3.
