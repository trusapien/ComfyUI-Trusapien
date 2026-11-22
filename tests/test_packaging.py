"""Packaging metadata: pyproject.toml agrees with requirements.txt and USER_AGENT.

Reads files as text; imports neither the node nor requests. Needs `tomllib`
(Python 3.11+) or `tomli`; skips without either.
"""

import re
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = pytest.importorskip("tomli", reason="needs tomllib (3.11+) or tomli")

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pyproject():
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def _normalise(requirement):
    return re.sub(r"\s+", "", requirement)


def test_requirements_match_pyproject(pyproject):
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    requirements = [
        _normalise(line.split("#", 1)[0]) for line in lines if line.split("#", 1)[0].strip()
    ]
    dependencies = [_normalise(d) for d in pyproject["project"]["dependencies"]]
    assert sorted(requirements) == sorted(dependencies)
    names = {re.split(r"[<>=!~;\[ ]", d, 1)[0].lower() for d in dependencies}
    assert not names & {"torch", "comfyui"}, "ComfyUI provides these; do not list them"


def test_version_matches_user_agent(pyproject):
    source = (ROOT / "trusapien_client.py").read_text(encoding="utf-8")
    match = re.search(r'^USER_AGENT = "ComfyUI-Trusapien/([^"]+)"$', source, re.MULTILINE)
    assert match, "USER_AGENT not found in trusapien_client.py"
    assert match.group(1) == pyproject["project"]["version"]


def test_registry_required_fields(pyproject):
    project = pyproject["project"]
    assert project["name"] and project["version"]
    assert project["urls"]["Repository"]
    assert isinstance(project["license"], dict), "the registry spec rejects a bare string"
    assert pyproject["tool"]["comfy"]["PublisherId"]
