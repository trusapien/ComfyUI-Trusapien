"""Loads the node package the way ComfyUI does: by path, as a package.

`torch` is not installed for the tests. The node only uses two of its functions
on the way out (`from_numpy`, `stack`), so a stand-in backed by numpy is enough
to check what the node does; it does not check torch itself.
"""

import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def package():
    torch = types.ModuleType("torch")
    torch.from_numpy = lambda array: array
    torch.stack = lambda arrays: np.stack(arrays)
    sys.modules.setdefault("torch", torch)
    spec = importlib.util.spec_from_file_location(
        "comfyui_trusapien", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["comfyui_trusapien"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def client_module(package):
    return sys.modules["comfyui_trusapien.trusapien_client"]


@pytest.fixture(scope="session")
def node_module(package):
    return sys.modules["comfyui_trusapien.trusapien_node"]


class Response:
    def __init__(self, status_code=200, body=None, content=b""):
        self.status_code = status_code
        self._body = body
        self.content = content

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


class Session:
    """A scripted API: answers in order, and remembers what it was asked."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def scripted():
    return Session, Response
