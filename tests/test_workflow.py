"""The example workflow loads with the node as it is today.

`trusapien_example_workflow.json` is the file the browser saves (UI format):
nodes with positional `widgets_values`, links as `[id, from, slot, to, slot,
type]`. Nothing here needs ComfyUI; the file is run inside ComfyUI by
`tools/run_in_comfyui.py --example`.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "trusapien_example_workflow.json"
NODE = "TrusapienValidationNode"
LINK_TYPES = {"IMAGE", "MASK", "LATENT", "MODEL", "CLIP", "VAE", "CONDITIONING"}


@pytest.fixture(scope="module")
def workflow():
    return json.loads(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def nodes(workflow):
    return {node["id"]: node for node in workflow["nodes"]}


@pytest.fixture(scope="module")
def harness():
    spec = importlib.util.spec_from_file_location("run_in_comfyui", ROOT / "tools" / "run_in_comfyui.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def widget_names(node_class):
    """The inputs the browser draws as widgets, in INPUT_TYPES order."""
    spec = node_class.INPUT_TYPES()
    return [
        name
        for section in ("required", "optional")
        for name, (kind, *_) in spec.get(section, {}).items()
        if isinstance(kind, list) or kind not in LINK_TYPES
    ]


def test_ids_are_unique_and_within_the_counters(workflow, nodes):
    assert len(nodes) == len(workflow["nodes"])
    link_ids = [link[0] for link in workflow["links"]]
    assert len(set(link_ids)) == len(link_ids)
    assert workflow["last_node_id"] >= max(nodes)
    assert workflow["last_link_id"] >= max(link_ids)


def test_every_link_joins_existing_slots_of_the_same_type(workflow, nodes):
    for link_id, source, source_slot, target, target_slot, kind in workflow["links"]:
        assert source in nodes and target in nodes, link_id
        output = nodes[source]["outputs"][source_slot]
        assert link_id in (output["links"] or []), link_id
        assert output["type"] == kind, link_id
        entry = nodes[target]["inputs"][target_slot]
        assert entry["link"] == link_id, link_id
        assert entry["type"] == kind, link_id


def test_every_link_a_node_names_exists(workflow):
    link_ids = {link[0] for link in workflow["links"]}
    for node in workflow["nodes"]:
        named = [entry["link"] for entry in node.get("inputs", []) if entry.get("link") is not None]
        named += [link for entry in node.get("outputs", []) for link in entry.get("links") or []]
        assert set(named) <= link_ids, node["id"]


def test_the_node_matches_its_inputs_and_outputs(nodes, node_module, client_module):
    node_class = node_module.TrusapienValidationNode
    (node,) = [node for node in nodes.values() if node["type"] == NODE]
    values = dict(zip(widget_names(node_class), node["widgets_values"]))
    assert list(values) == ["heatmap", "api_key", "objectives_json"]
    assert len(node["widgets_values"]) == len(values)
    assert values["heatmap"] in client_module.MAPS
    assert values["api_key"] == ""
    assert values["objectives_json"] == ""
    assert [entry["name"] for entry in node["outputs"]] == list(node_class.RETURN_NAMES)
    assert [entry["type"] for entry in node["outputs"]] == list(node_class.RETURN_TYPES)
    assert [entry["name"] for entry in node["inputs"]] == ["image"]


def test_the_heat_map_is_previewed(workflow, nodes):
    (node,) = [node for node in nodes.values() if node["type"] == NODE]
    targets = [nodes[link[3]]["type"] for link in workflow["links"] if link[1] == node["id"] and link[2] == 0]
    assert targets == ["PreviewImage"]


def test_the_image_is_one_that_ships_with_comfyui(nodes):
    (load,) = [node for node in nodes.values() if node["type"] == "LoadImage"]
    assert load["widgets_values"][0] == "example.png"


def test_no_key_and_no_stray_fields_anywhere():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "widgets_values_named" not in text
    assert "PASTE_YOUR" not in text
    assert not re.search(r'"api_?key"\s*:\s*"[^"]', text, re.IGNORECASE)  # no "api_key": "<something>"
    assert "frontendVersion" not in text  # it was never loaded in a browser here


def test_it_converts_to_the_prompt_comfyui_runs(workflow, harness, node_module):
    # A cut-down /object_info: ComfyUI's two core nodes as it declares them, and ours.
    spec = node_module.TrusapienValidationNode.INPUT_TYPES()
    object_info = {
        "LoadImage": {"input": {"required": {"image": [["example.png"], {"image_upload": True}]}}},
        "PreviewImage": {"input": {"required": {"images": ["IMAGE"]}, "hidden": {"prompt": "PROMPT"}}},
        NODE: {"input": {"required": spec["required"], "optional": spec["optional"]}},
    }
    assert harness.workflow_to_prompt(workflow, object_info) == {
        "1": {"class_type": "LoadImage", "inputs": {"image": "example.png"}},
        "2": {
            "class_type": NODE,
            "inputs": {"image": ["1", 0], "heatmap": "Attention", "api_key": "", "objectives_json": ""},
        },
        "3": {"class_type": "PreviewImage", "inputs": {"images": ["2", 0]}},
        "4": {"class_type": "PreviewImage", "inputs": {"images": ["2", 1]}},
    }


def test_the_converter_refuses_what_it_cannot_run(workflow, harness):
    with pytest.raises(harness.Failed, match="no node type 'LoadImage'"):
        harness.workflow_to_prompt(workflow, {})
