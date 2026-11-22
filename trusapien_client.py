"""The Trusapien Creative Validation API, as this node calls it.

No ComfyUI and no torch in here: it takes PNG bytes and returns plain data, so
it can be tested, and used, on its own.

The API is a job API. Creating a validation answers at once; the result is read
by polling. One idempotency key is one analysis, for good: the key here is a
hash of the image (and the objectives), so running the same image again reads
the earlier result instead of paying for a second analysis.
"""

import hashlib
import json
import os
import time

import requests

DEFAULT_API_URL = "https://creative-validation.trusapien.com"
USER_AGENT = "ComfyUI-Trusapien/0.2.0"

#: Heat map choice in the node -> the result file's name at the API (`results.<name>`).
#: Every name here is one the service returned on its first real run. The labels are
#: what saved workflows hold, so they stay as they are. `Engagement` is the
#: `engagement_new_heat` file, the only engagement map the service returns; it goes
#: with the `engagement_new` metric (the metrics carry both `engagement` and
#: `engagement_new`).
MAPS = {
    "Attention": "heat",
    "Fog": "fog",
    "Cognitive Demand": "cognitive_demand_heat",
    "Engagement": "engagement_new_heat",
    "Memory": "memory_heat",
    "Clarity": "clarity_heat",
    "Trust": "trust_heat",
    "Intent": "intent_heat",
    "Avoidance": "avoidance_heat",
}
_LABELS = {name: label for label, name in MAPS.items()}

OBJECTIVE_FIELDS = (
    "purpose",
    "industry_category",
    "industry_subcategory",
    "usecase_category",
    "usecase_subcategory",
    "platform",
)


class TrusapienError(Exception):
    """Something the person running the workflow can read and act on."""


def api_url() -> str:
    return (os.environ.get("TRUSAPIEN_API_URL") or DEFAULT_API_URL).rstrip("/")


def resolve_key(from_widget: str) -> str:
    """The key typed into the node, or TRUSAPIEN_API_KEY from the environment."""
    key = (from_widget or "").strip() or (os.environ.get("TRUSAPIEN_API_KEY") or "").strip()
    if not key:
        raise TrusapienError(
            "No Trusapien API key. Set the TRUSAPIEN_API_KEY environment variable "
            "(recommended: a key typed into the node is saved inside the workflow file "
            "and inside the images ComfyUI writes), or paste it into api_key."
        )
    return key


def parse_objectives(text: str):
    """The six objectives from the node's text box, or None when it is empty."""
    if not (text or "").strip():
        return None
    try:
        value = json.loads(text)
    except ValueError:
        raise TrusapienError("objectives_json is not valid JSON.") from None
    missing = [field for field in OBJECTIVE_FIELDS if not isinstance(value, dict) or not value.get(field)]
    if missing:
        raise TrusapienError(
            "objectives_json needs all six fields; missing: " + ", ".join(missing) + "."
        )
    return {field: str(value[field]) for field in OBJECTIVE_FIELDS}


def idempotency_key(png: bytes, objectives) -> str:
    digest = hashlib.sha256(png)
    digest.update(json.dumps(objectives, sort_keys=True).encode())
    return "comfyui-" + digest.hexdigest()[:48]


def map_label(name: str) -> str:
    """A result file's name as the node's `heatmap` choice, or the name itself if it is not one."""
    return _LABELS.get(name, name)


def map_names(validation: dict) -> list:
    """The maps an analysis has: the node's choice names in choice order, then any other result file."""
    names = {
        (entry.get("key") or "")[len("results."):]
        for entry in validation.get("assets") or []
        if (entry.get("key") or "").startswith("results.")
    }
    offered = [label for label, name in MAPS.items() if name in names]
    return offered + sorted(name for name in names if name not in _LABELS)


def _detail(response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = None
    return detail if isinstance(detail, str) and detail else f"HTTP {response.status_code}"


class Client:
    def __init__(self, api_key: str, base_url=None, session=None, sleep=time.sleep, clock=time.monotonic):
        self.base_url = (base_url or api_url()).rstrip("/")
        self.session = session or requests.Session()
        self.headers = {"Authorization": f"Bearer {api_key}", "User-Agent": USER_AGENT}
        self._sleep = sleep
        self._clock = clock

    def _request(self, method: str, path: str, **kwargs):
        headers = dict(self.headers, **kwargs.pop("headers", {}))
        try:
            response = self.session.request(
                method, self.base_url + path, headers=headers, timeout=kwargs.pop("timeout", 60), **kwargs
            )
        except requests.RequestException as error:
            raise TrusapienError(f"The Trusapien API could not be reached: {error}") from error
        if response.status_code == 401:
            raise TrusapienError("The Trusapien API key was not recognised.")
        if response.status_code == 429:
            raise TrusapienError("Too many of your validations are still being processed. Try again shortly.")
        if response.status_code in (413, 422):
            raise TrusapienError(f"The image was not accepted: {_detail(response)}")
        if response.status_code >= 400:
            raise TrusapienError(f"The Trusapien API answered with an error: {_detail(response)}")
        return response

    def _create(self, png: bytes, file_name: str, objectives, key: str) -> dict:
        data = {"objectives": json.dumps(objectives)} if objectives else {}
        return self._request(
            "POST",
            "/v1/validations/upload",
            files={"file": (file_name, png, "image/png")},
            data=data,
            headers={"Idempotency-Key": key},
            timeout=120,
        ).json()

    def validate(self, png: bytes, objectives=None, file_name="creative.png", deadline=300.0, interval=2.0):
        """Have one image analysed and wait for the result. Returns the validation."""
        key = idempotency_key(png, objectives)
        validation = self._create(png, file_name, objectives, key)
        if validation.get("status") in ("error", "expired"):
            # An earlier run of this same image ended badly, or its result has
            # since been removed. The key would return that forever; ask afresh.
            validation = self._create(png, file_name, objectives, f"{key}-{int(time.time())}")

        give_up = self._clock() + deadline
        while validation.get("status") == "processing":
            if self._clock() >= give_up:
                raise TrusapienError(
                    f"The analysis did not finish in {int(deadline)} seconds. It is still running; "
                    "queue the workflow again to pick up the result without a second charge."
                )
            self._sleep(interval)
            validation = self._request("GET", f"/v1/validations/{validation['id']}").json()

        if validation.get("status") != "done":
            message = validation.get("error_message") or "The creative could not be analysed."
            raise TrusapienError(f"{message} ({validation.get('error_code') or validation.get('status')})")
        return validation

    def asset(self, validation: dict, name: str):
        """One result file's bytes by its name (`heat`, `fog`, ...), or None if there is none."""
        wanted = f"results.{name}"
        for entry in validation.get("assets") or []:
            key = entry.get("key") or ""
            if key == wanted or key.endswith("." + name):
                path = f"/v1/validations/{validation['id']}/assets/{key}"
                try:
                    return self._request("GET", path).content
                except TrusapienError as error:
                    raise TrusapienError(
                        f"The analysis lists a {map_label(name)} map, but it could not be downloaded. {error}"
                    ) from None
        return None


def summary(validation: dict) -> dict:
    """What the node hands on as JSON."""
    return {
        "validation_id": validation.get("id"),
        "metrics": validation.get("metrics"),
        "objectives": validation.get("objectives"),
        "objectives_error": validation.get("objectives_error"),
        "benchmarks": validation.get("benchmarks"),
        "impact": validation.get("impact"),
        "maps": map_names(validation),
    }
