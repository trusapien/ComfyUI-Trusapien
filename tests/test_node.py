import io
import json

import numpy as np
import pytest
from PIL import Image


def heat_png(width, height):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeClient:
    made = []

    def __init__(self, key):
        self.key = key
        self.pngs = []
        FakeClient.made.append(self)

    def validate(self, png, objectives=None, file_name="creative.png"):
        self.pngs.append(png)
        return {
            "id": f"v-{len(self.pngs)}",
            "status": "done",
            "metrics": {"focus": 70 + len(self.pngs)},
            "assets": [{"key": "results.heat"}],
        }

    def asset(self, validation, name):
        return heat_png(4, 4) if name == "heat" else None


@pytest.fixture
def node(node_module, monkeypatch):
    FakeClient.made = []
    monkeypatch.setattr(node_module, "Client", FakeClient)
    monkeypatch.setenv("TRUSAPIEN_API_KEY", "cv_env")
    return node_module.TrusapienValidationNode()


def test_the_node_declares_what_the_readme_says(node_module):
    spec = node_module.TrusapienValidationNode.INPUT_TYPES()
    assert set(spec["required"]) == {"image", "heatmap"}
    assert set(spec["optional"]) == {"api_key", "objectives_json"}
    assert node_module.TrusapienValidationNode.RETURN_NAMES == ("heatmap", "image", "metrics_json", "status")


def test_an_image_goes_out_as_the_png_it_is(node_module):
    frame = np.zeros((2, 3, 3), dtype=np.float32)
    frame[0, 0] = (1.0, 0.5, 0.0)
    back = np.asarray(Image.open(io.BytesIO(node_module.to_png(frame))))
    assert back.shape == (2, 3, 3)
    assert tuple(back[0, 0]) == (255, 127, 0)


def test_one_image_comes_back_with_its_map_at_its_own_size(node):
    image = np.random.rand(1, 6, 8, 3).astype(np.float32)
    heatmap, passthrough, metrics, status = node.validate_creative(image)
    assert heatmap.shape == (1, 6, 8, 3)  # the 4x4 map, resized to the image
    assert np.allclose(heatmap[0, 0, 0], (1.0, 0.0, 0.0))
    assert passthrough is image
    assert json.loads(metrics)["metrics"] == {"focus": 71}
    assert status == "Analysed 1 image."


def test_a_batch_is_one_analysis_per_image(node):
    image = np.random.rand(3, 4, 4, 3).astype(np.float32)
    heatmap, _, metrics, status = node.validate_creative(image)
    assert heatmap.shape[0] == 3
    assert len(FakeClient.made[0].pngs) == 3
    assert [entry["validation_id"] for entry in json.loads(metrics)] == ["v-1", "v-2", "v-3"]
    assert status == "Analysed 3 images."


def test_a_batch_too_large_is_refused_before_anything_is_paid_for(node, node_module):
    image = np.zeros((node_module.MAX_BATCH + 1, 4, 4, 3), dtype=np.float32)
    with pytest.raises(RuntimeError, match="paid analysis"):
        node.validate_creative(image)
    assert FakeClient.made[0].pngs == []


def test_no_key_stops_the_workflow_instead_of_passing_the_image_on(node, monkeypatch):
    monkeypatch.delenv("TRUSAPIEN_API_KEY")
    with pytest.raises(RuntimeError, match=r"\[Trusapien\] No Trusapien API key"):
        node.validate_creative(np.zeros((1, 4, 4, 3), dtype=np.float32))


def test_a_map_the_analysis_does_not_have_is_named(node):
    with pytest.raises(RuntimeError, match="no Trust map.*heat"):
        node.validate_creative(np.zeros((1, 4, 4, 3), dtype=np.float32), heatmap="Trust")
