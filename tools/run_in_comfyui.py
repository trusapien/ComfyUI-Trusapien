"""Run the Trusapien node inside a running ComfyUI, against `tools/stub_service.py`.

Development only. ComfyUI must have been started with this repository in
`custom_nodes/ComfyUI-Trusapien`, `tools/comfyui_dev_nodes` in
`custom_nodes/trusapien-dev-nodes`, and TRUSAPIEN_API_URL pointing at the stub
(see CLAUDE.md, "Verified inside ComfyUI"). Then:

    python tools/run_in_comfyui.py --comfy http://127.0.0.1:8188 --stub http://127.0.0.1:8765

Everything goes through ComfyUI's HTTP API, the way the browser would send it:
upload images, queue API-format prompts, read /history. Exits 0 only if every
check passes. Needs Pillow and numpy; nothing from ComfyUI or torch.
"""

import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import numpy as np
from PIL import Image

NODE = "TrusapienValidationNode"
MAPS = [
    "Attention", "Fog", "Cognitive Demand", "Engagement", "Memory", "Clarity", "Trust", "Intent", "Avoidance",
]
WIDTH, HEIGHT = 333, 217  # odd on purpose: the stub's maps come back at half size
OBJECTIVES = json.dumps({
    "purpose": "awareness",
    "industry_category": "retail",
    "industry_subcategory": "fashion",
    "usecase_category": "social",
    "usecase_subcategory": "feed",
    "platform": "instagram",
})


class Failed(AssertionError):
    pass


def check(condition, message):
    if not condition:
        raise Failed(message)


class Http:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def call(self, method, path, body=None, headers=None, raw=False):
        request = urllib.request.Request(self.base + path, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                content = response.read()
        except urllib.error.HTTPError as error:
            raise Failed(f"{method} {path}: HTTP {error.code}: {error.read()[:2000].decode(errors='replace')}")
        return content if raw else json.loads(content or b"null")

    def get(self, path, **kwargs):
        return self.call("GET", path, **kwargs)

    def post(self, path, payload=None):
        return self.call("POST", path, json.dumps(payload or {}).encode(), {"Content-Type": "application/json"})


class Run:
    def __init__(self, comfy, stub):
        self.comfy = Http(comfy)
        self.stub = Http(stub)
        self.client_id = str(uuid.uuid4())
        self.results = []

    # -- ComfyUI ------------------------------------------------------------
    def upload(self, name, picture):
        buffer = io.BytesIO()
        picture.save(buffer, format="PNG")
        boundary = uuid.uuid4().hex
        body = b"".join([
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            "Content-Type: image/png\r\n\r\n".encode(), buffer.getvalue(), b"\r\n",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n".encode(),
            f"--{boundary}--\r\n".encode(),
        ])
        answer = self.comfy.call(
            "POST", "/upload/image", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        return answer["name"]

    def queue(self, prompt, timeout=300):
        """Queue an API-format prompt and wait for its history entry."""
        prompt_id = self.comfy.post("/prompt", {"prompt": prompt, "client_id": self.client_id})["prompt_id"]
        give_up = time.monotonic() + timeout
        while time.monotonic() < give_up:
            history = self.comfy.get(f"/history/{prompt_id}")
            entry = history.get(prompt_id)
            if entry and (entry["status"].get("completed") or entry["status"].get("status_str") == "error"):
                return entry
            time.sleep(0.25)
        raise Failed(f"prompt {prompt_id} did not finish in {timeout} s")

    def view(self, image):
        query = urllib.parse.urlencode(image)
        return Image.open(io.BytesIO(self.comfy.get(f"/view?{query}", raw=True)))

    def free(self):
        # Resets ComfyUI's executor, and with it the cache of node outputs, so
        # an identical prompt runs the node again instead of reusing its output.
        self.comfy.post("/free", {"free_memory": True, "unload_models": True})
        time.sleep(1.0)

    # -- prompts ------------------------------------------------------------
    @staticmethod
    def prompt(images, heatmap="Attention", api_key="", objectives="", cast=None):
        """LoadImage x N -> ImageBatch chain -> [cast] -> Trusapien -> SaveImage + probe."""
        prompt, source = {}, None
        for index, name in enumerate(images):
            node_id = f"load{index}"
            prompt[node_id] = {"class_type": "LoadImage", "inputs": {"image": name}}
            if source is None:
                source = [node_id, 0]
            else:
                prompt[f"batch{index}"] = {
                    "class_type": "ImageBatch", "inputs": {"image1": source, "image2": [node_id, 0]},
                }
                source = [f"batch{index}", 0]
        if cast:
            prompt["cast"] = {"class_type": "TrusapienDevCast", "inputs": {"images": source, "mode": cast}}
            source = ["cast", 0]
        prompt["trusapien"] = {
            "class_type": NODE,
            "inputs": {"image": source, "heatmap": heatmap, "api_key": api_key, "objectives_json": objectives},
        }
        prompt["save"] = {
            "class_type": "SaveImage",
            "inputs": {"images": ["trusapien", 0], "filename_prefix": "trusapien_check"},
        }
        prompt["probe"] = {"class_type": "TrusapienDevProbe", "inputs": {"images": ["trusapien", 0]}}
        return prompt

    @staticmethod
    def error_of(entry):
        for kind, data in entry["status"].get("messages", []):
            if kind == "execution_error":
                return data
        return None

    @staticmethod
    def cached_nodes(entry):
        for kind, data in entry["status"].get("messages", []):
            if kind == "execution_cached":
                return set(data.get("nodes") or [])
        return set()

    def succeeded(self, entry, batch):
        error = self.error_of(entry)
        check(entry["status"].get("status_str") == "success", f"prompt failed: {error and error['exception_message']}")
        probe = entry["outputs"]["probe"]["probe"][0]
        check(probe["dtype"] == "torch.float32", f"heatmap dtype {probe['dtype']}")
        check(probe["shape"] == [batch, HEIGHT, WIDTH, 3], f"heatmap shape {probe['shape']}")
        check(0.0 <= probe["min"] <= probe["max"] <= 1.0, f"heatmap range {probe['min']}..{probe['max']}")
        check(probe["max"] > 0.0, "heatmap is all black")
        saved = entry["outputs"]["save"]["images"]
        check(len(saved) == batch, f"{len(saved)} saved maps for a batch of {batch}")
        size = self.view(saved[0]).size
        check(size == (WIDTH, HEIGHT), f"saved map is {size}, the input is {(WIDTH, HEIGHT)}")
        return probe

    def failed_with(self, entry, sentence):
        check(entry["status"].get("status_str") == "error", "prompt succeeded; it should have failed")
        error = self.error_of(entry)
        check(error is not None, "no execution_error in the history")
        message = error["exception_message"]
        check(message.startswith("[Trusapien] "), f"error is not a [Trusapien] sentence: {message!r}")
        check(sentence in message, f"error {message!r} does not say {sentence!r}")
        check(error["node_id"] == "trusapien", f"error came from node {error['node_id']}")
        check("save" not in entry["outputs"] and "probe" not in entry["outputs"], "outputs exist after a failure")
        return message

    # -- the run --------------------------------------------------------------
    def step(self, name, function):
        started = time.monotonic()
        try:
            detail = function()
        except Failed as failure:
            self.results.append((False, name, str(failure)))
            print(f"FAIL  {name}: {failure}", flush=True)
            return
        self.results.append((True, name, detail))
        print(f"ok    {name} ({time.monotonic() - started:.1f} s){': ' + detail if detail else ''}", flush=True)

    def stats(self):
        return self.stub.get("/_stub/stats")

    def main(self):
        self.stub.post("/_stub/reset")
        rng = np.random.default_rng(20261122)

        def noise(alpha=False):
            channels = 4 if alpha else 3
            array = rng.integers(0, 256, (HEIGHT, WIDTH, channels), dtype=np.uint8)
            if alpha:
                array[..., 3] = np.linspace(0, 255, WIDTH, dtype=np.uint8)[None, :]
            return Image.fromarray(array, "RGBA" if alpha else "RGB")

        uploaded = []

        def fresh(count):
            """`count` images no earlier step has sent, so each one is a new analysis."""
            start = len(uploaded)
            uploaded.extend(self.upload(f"trusapien_check_{start + i}.png", noise()) for i in range(count))
            return uploaded[start:]

        self.free()  # nothing from an earlier run of this script may come from ComfyUI's cache
        names = fresh(9)
        rgba = self.upload("trusapien_check_rgba.png", noise(alpha=True))

        def object_info():
            info = self.comfy.get(f"/object_info/{NODE}")[NODE]
            required, optional = info["input"]["required"], info["input"].get("optional", {})
            check(set(required) == {"image", "heatmap"}, f"required inputs {sorted(required)}")
            check(required["image"][0] == "IMAGE", f"image input is {required['image']}")
            heatmap = required["heatmap"]
            options = heatmap[1]["options"] if heatmap[0] == "COMBO" else heatmap[0]
            check(options == MAPS, f"heatmap choices {options}")
            check(heatmap[1].get("default") == "Attention", f"heatmap default {heatmap[1].get('default')}")
            check(set(optional) == {"api_key", "objectives_json"}, f"optional inputs {sorted(optional)}")
            check(all(optional[name][0] == "STRING" for name in optional), "optional inputs are not STRING")
            check(info["output"] == ["IMAGE", "IMAGE", "STRING", "STRING"], f"outputs {info['output']}")
            check(info["output_name"] == ["heatmap", "image", "metrics_json", "status"], f"names {info['output_name']}")
            check(info["category"] == "Trusapien", f"category {info['category']}")
            check(info["display_name"] == "Trusapien Creative Validation", f"display name {info['display_name']}")
            return "inputs, outputs, map choices as declared"

        def single():
            before = self.stats()
            entry = self.queue(self.prompt(names[:1]))
            probe = self.succeeded(entry, 1)
            after = self.stats()
            check(after["analyses"] - before["analyses"] == 1, f"{after['analyses'] - before['analyses']} analyses")
            return f"{probe['dtype']} {probe['shape']} range {probe['min']:.3f}..{probe['max']:.3f} on {probe['device']}"

        def batch(size):
            def run():
                images = fresh(size)
                before = self.stats()
                entry = self.queue(self.prompt(images))
                self.succeeded(entry, size)
                after = self.stats()
                new = after["analyses"] - before["analyses"]
                check(new == size, f"{new} new analyses for {size} distinct images")
                return f"{size} maps, {new} new analyses"
            return run

        def too_large():
            before = self.stats()
            entry = self.queue(self.prompt(names[:9]))
            message = self.failed_with(entry, "paid analysis")
            after = self.stats()
            check(after == before, f"the stub was called: {before} -> {after}")
            return f"no request sent; {message!r}"

        def alpha_png():
            return f"LoadImage of an RGBA PNG: {self.succeeded(self.queue(self.prompt([rgba])), 1)['shape']}"

        argv = self.comfy.get("/system_stats").get("system", {}).get("argv", [])
        fp16_intermediates = "--fp16-intermediates" in argv

        def cast(mode):
            # names[0] was analysed in the first step. The same pixels in another
            # precision, layout or with an alpha channel are the same image and must
            # not be paid for again; grey is a different image. bfloat16 keeps every
            # 8-bit level coming from float32, but not from float16 (7 of 256 levels
            # move), so under --fp16-intermediates its count is reported, not checked.
            expected = 1 if mode == "grey" else None if (mode == "bf16" and fp16_intermediates) else 0

            def run():
                before = self.stats()
                self.succeeded(self.queue(self.prompt(names[:1], cast=mode)), 1)
                new = self.stats()["analyses"] - before["analyses"]
                check(expected is None or new == expected, f"{new} new analyses, expected {expected}")
                return f"{new} new analyses" + (" (not checked: fp16 -> bf16 loses levels)" if expected is None else "")
            return run

        def rerun_is_free():
            first = self.queue(self.prompt(names[:1], objectives=OBJECTIVES))
            self.succeeded(first, 1)
            self.free()
            before = self.stats()
            again = self.queue(self.prompt(names[:1], objectives=OBJECTIVES))
            self.succeeded(again, 1)
            after = self.stats()
            check("trusapien" not in self.cached_nodes(again), "ComfyUI reused its cache; the node did not run")
            check(after["uploads"] > before["uploads"], "the node did not ask the API again")
            check(after["analyses"] == before["analyses"], f"a rerun created {after['analyses'] - before['analyses']} analyses")
            return f"node executed again, {after['uploads'] - before['uploads']} upload, 0 new analyses"

        def missing_map():
            self.stub.post("/_stub/mode", {"omit": ["trust_heat"]})
            try:
                self.free()
                entry = self.queue(self.prompt(names[:1], heatmap="Trust"))
                return self.failed_with(entry, "The analysis has no Trust map")
            finally:
                self.stub.post("/_stub/mode", {"omit": []})

        def refused_key():
            self.stub.post("/_stub/mode", {"reject_all": True})
            try:
                self.free()
                entry = self.queue(self.prompt(names[:1]))
                return self.failed_with(entry, "The Trusapien API key was not recognised.")
            finally:
                self.stub.post("/_stub/mode", {"reject_all": False})

        self.step("object_info declares the node", object_info)
        self.step("one image: float32 [1,H,W,3] at the input size", single)
        for size in (1, 2, 8):
            self.step(f"batch of {size} distinct images: {size} maps, {size} analyses", batch(size))
        self.step("batch of 9 is refused before any request", too_large)
        self.step("RGBA PNG through LoadImage", alpha_png)
        for mode in ("rgba", "grey", "fp16", "bf16", "noncontiguous"):
            self.step(f"{mode} IMAGE tensor into the node", cast(mode))
        self.step("same image + objectives again: no new analysis", rerun_is_free)
        self.step("a map the analysis lacks fails the prompt", missing_map)
        self.step("a refused key (401) fails the prompt", refused_key)

        passed = sum(1 for ok, *_ in self.results if ok)
        print(f"\n{passed}/{len(self.results)} checks passed. Stub: {json.dumps(self.stats())}")
        return 0 if passed == len(self.results) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--comfy", default="http://127.0.0.1:8188")
    parser.add_argument("--stub", default="http://127.0.0.1:8765")
    options = parser.parse_args()
    sys.exit(Run(options.comfy, options.stub).main())


if __name__ == "__main__":
    main()
