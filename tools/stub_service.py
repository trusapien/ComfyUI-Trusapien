"""A stand-in for the Trusapien Creative Validation API, for development only.

It answers the three calls `trusapien_client.py` makes, the way the service
does as far as the client relies on it:

    POST /v1/validations/upload            multipart `file` (+ `objectives`), Idempotency-Key
    GET  /v1/validations/{id}              `processing` for a moment, then `done`
    GET  /v1/validations/{id}/assets/{key} result files: JPEG, half the input's size

It analyses nothing: the metrics are made up from the image's bytes and the
maps are gradients. Nothing in the node imports it.

Every new Idempotency-Key counts as one paid analysis, so a test can prove that
running the same image again pays nothing. Failures can be switched on:

    python tools/stub_service.py --port 8765                     # all well
    python tools/stub_service.py --omit trust_heat               # that map is missing
    python tools/stub_service.py --reject-all                    # every key is refused (401)

or while it runs, without a restart:

    POST /_stub/mode   {"omit": ["trust_heat"], "reject_all": false}
    GET  /_stub/stats  {"analyses": distinct keys, "uploads": POSTs, "requests": all API calls}
    POST /_stub/reset  forget everything (validations, counters, mode)
"""

import argparse
import colorsys
import email.parser
import email.policy
import hashlib
import io
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

MAPS = (
    "heat",
    "fog",
    "trust_heat",
    "intent_heat",
    "avoidance_heat",
    "memory_heat",
    "clarity_heat",
    "cognitive_demand_heat",
    "engagement_new_heat",
)

METRICS = (
    "focus",
    "clarity",
    "cognitive_demand",
    "engagement",
    "engagement_new",
    "memory",
    "trust",
    "intent",
    "avoidance",
    "focus_first_two",
    "focus_last_two",
)


class State:
    def __init__(self, processing_seconds=1.0, omit=(), reject_all=False, reject_keys=()):
        self.lock = threading.Lock()
        self.processing_seconds = processing_seconds
        self.default_mode = {"omit": list(omit), "reject_all": reject_all, "reject_keys": list(reject_keys)}
        self.reset()

    def reset(self):
        with self.lock:
            self.mode = json.loads(json.dumps(self.default_mode))
            self.by_key = {}  # Idempotency-Key -> validation id
            self.validations = {}  # id -> stored validation
            self.uploads = 0
            self.requests = 0

    def stats(self):
        with self.lock:
            return {"analyses": len(self.by_key), "uploads": self.uploads, "requests": self.requests}


def _map_jpeg(name: str, size) -> bytes:
    """A gradient in a colour of its own per map, at `size`, as JPEG."""
    width, height = size
    hue = MAPS.index(name) / len(MAPS) if name in MAPS else 0.0
    picture = Image.new("RGB", (width, height))
    pixels = picture.load()
    for x in range(width):
        level = (x + 1) / width
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, level)
        for y in range(height):
            pixels[x, y] = (int(r * 255), int(g * 255), int(b * 255))
    buffer = io.BytesIO()
    picture.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def _parse_multipart(content_type: str, body: bytes) -> dict:
    message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
        b"Content-Type: " + content_type.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )
    fields = {}
    if not message.is_multipart():
        return fields
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name:
            fields[name] = (part.get_filename(), part.get_payload(decode=True) or b"")
    return fields


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TrusapienStub/1"

        def log_message(self, format, *args):  # quieter than the default
            if not getattr(self.server, "quiet", False):
                super().log_message(format, *args)

        # -- helpers ---------------------------------------------------------
        def _send(self, status, body=None, content=None, content_type="application/json"):
            payload = content if content is not None else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(length) if length else b""

        def _authorised(self) -> bool:
            header = self.headers.get("Authorization") or ""
            key = header[len("Bearer "):].strip() if header.startswith("Bearer ") else ""
            mode = state.mode
            if not key or mode["reject_all"] or key in mode["reject_keys"]:
                self._send(401, {"detail": "The key was not recognised."})
                return False
            return True

        def _render(self, validation: dict) -> dict:
            done = time.monotonic() - validation["created"] >= state.processing_seconds
            out = {
                "id": validation["id"],
                "status": "done" if done else "processing",
                "created_at": validation["created_at"],
                "objectives": validation["objectives"],
                "objectives_error": None,
                "benchmarks": None,
                "impact": None,
                "metrics": None,
                "assets": [],
            }
            if done:
                out["metrics"] = validation["metrics"]
                out["assets"] = [{"key": "original", "content_type": "image/png"}] + [
                    {"key": f"results.{name}", "content_type": "image/jpeg"}
                    for name in MAPS
                    if name not in state.mode["omit"]
                ]
            return out

        # -- routes ----------------------------------------------------------
        def do_GET(self):
            parts = self.path.split("?")[0].strip("/").split("/")
            if parts == ["_stub", "stats"]:
                return self._send(200, state.stats())
            if parts[:2] != ["v1", "validations"] or len(parts) not in (3, 5):
                return self._send(404, {"detail": "Not found."})
            with state.lock:
                state.requests += 1
            if not self._authorised():
                return None
            validation = state.validations.get(parts[2])
            if validation is None:
                return self._send(404, {"detail": "No such validation."})
            if len(parts) == 3:
                return self._send(200, self._render(validation))
            if parts[3] != "assets":
                return self._send(404, {"detail": "Not found."})
            rendered = self._render(validation)
            if parts[4] not in {entry["key"] for entry in rendered["assets"]}:
                return self._send(404, {"detail": "No such asset."})
            if parts[4] == "original":
                return self._send(200, content=validation["original"], content_type="image/png")
            name = parts[4][len("results."):]
            width, height = validation["size"]
            jpeg = _map_jpeg(name, (max(1, width // 2), max(1, height // 2)))
            return self._send(200, content=jpeg, content_type="image/jpeg")

        def do_POST(self):
            path = self.path.split("?")[0].rstrip("/")
            body = self._body()
            if path == "/_stub/reset":
                state.reset()
                return self._send(200, state.stats())
            if path == "/_stub/mode":
                change = json.loads(body or b"{}")
                with state.lock:
                    for field in ("omit", "reject_all", "reject_keys"):
                        if field in change:
                            state.mode[field] = change[field]
                return self._send(200, state.mode)
            if path != "/v1/validations/upload":
                return self._send(404, {"detail": "Not found."})
            with state.lock:
                state.requests += 1
                state.uploads += 1
            if not self._authorised():
                return None
            key = self.headers.get("Idempotency-Key")
            if not key:
                return self._send(422, {"detail": "Idempotency-Key header is required."})
            fields = _parse_multipart(self.headers.get("Content-Type") or "", body)
            if "file" not in fields:
                return self._send(422, {"detail": "file is required."})
            file_name, content = fields["file"]
            try:
                picture = Image.open(io.BytesIO(content))
                picture.load()
            except Exception:
                return self._send(422, {"detail": f"{file_name}: unsupported format."})
            objectives = json.loads(fields["objectives"][1]) if "objectives" in fields else None
            with state.lock:
                existing = state.by_key.get(key)
                if existing is not None:
                    return self._send(200, self._render(state.validations[existing]))
                digest = hashlib.sha256(content).digest()
                validation = {
                    "id": str(uuid.uuid4()),
                    "created": time.monotonic(),
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "size": picture.size,
                    "original": content,
                    "objectives": objectives,
                    "metrics": {name: round(40 + digest[i] / 255 * 50, 1) for i, name in enumerate(METRICS)},
                }
                state.validations[validation["id"]] = validation
                state.by_key[key] = validation["id"]
            return self._send(202, self._render(validation))

    return Handler


def serve(host="127.0.0.1", port=8765, quiet=False, **state_options):
    """A running stub in a background thread. Returns (server, state)."""
    state = State(**state_options)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    server.quiet = quiet
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, state


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--processing-seconds", type=float, default=1.0)
    parser.add_argument("--omit", action="append", default=[], choices=MAPS, help="leave this map out")
    parser.add_argument("--reject-all", action="store_true", help="answer 401 to every key")
    parser.add_argument("--reject-key", action="append", default=[], help="answer 401 to this key")
    options = parser.parse_args()
    state = State(options.processing_seconds, options.omit, options.reject_all, options.reject_key)
    server = ThreadingHTTPServer((options.host, options.port), make_handler(state))
    print(f"Trusapien stub on http://{options.host}:{server.server_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
