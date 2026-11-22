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
    assert tuple(back[0, 0]) == (255, 128, 0)  # 127.5 rounds up


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


def jpeg(width, height, colour=(0, 128, 255)):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="JPEG")
    return buffer.getvalue()


def decoded(png):
    picture = Image.open(io.BytesIO(png))
    return picture.mode, np.asarray(picture)


def test_an_8_bit_image_is_the_same_png_in_float32_and_float16_so_it_is_paid_for_once(node_module):
    pixels = np.random.default_rng(1).integers(0, 256, (16, 16, 3), dtype=np.uint8)
    pixels.flat[:256] = np.arange(256)  # every level
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    as_float32 = pixels.astype(np.float32) / 255.0
    # ComfyUI with --fp16-intermediates; widened again as `tensor.float()` does.
    as_float16 = as_float32.astype(np.float16).astype(np.float32)
    assert node_module.to_png(as_float32) == buffer.getvalue()
    assert node_module.to_png(as_float16) == buffer.getvalue()


@pytest.mark.parametrize("shape", [(3, 5, 1), (3, 5)])
def test_a_grey_frame_goes_out_as_rgb(node_module, shape):
    frame = np.full(shape, 0.5, dtype=np.float32)
    mode, array = decoded(node_module.to_png(frame))
    assert mode == "RGB" and array.shape == (3, 5, 3)
    assert (array == 128).all()


def test_an_rgba_frame_goes_out_as_rgb_without_its_alpha(node_module):
    frame = np.zeros((3, 5, 4), dtype=np.float32)
    frame[..., 0] = 1.0
    frame[..., 3] = 0.25
    mode, array = decoded(node_module.to_png(frame))
    assert mode == "RGB"
    assert tuple(array[0, 0]) == (255, 0, 0)


def test_a_frame_that_is_no_image_is_a_sentence_not_a_crash(node):
    with pytest.raises(RuntimeError, match=r"\[Trusapien\] The image has shape \[4, 4, 5\]"):
        node.validate_creative(np.zeros((1, 4, 4, 5), dtype=np.float32))


class DeviceTensor:
    """Behaves like a torch tensor on a GPU in bfloat16 that requires grad:
    `.numpy()` refuses until it has been detached, moved and widened."""

    def __init__(self, array, detached=False, on_cpu=False, widened=False):
        self.array, self.detached, self.on_cpu, self.widened = array, detached, on_cpu, widened
        self.shape = array.shape

    def detach(self):
        return DeviceTensor(self.array, True, self.on_cpu, self.widened)

    def cpu(self):
        return DeviceTensor(self.array, self.detached, True, self.widened)

    def float(self):
        return DeviceTensor(self.array, self.detached, self.on_cpu, True)

    def numpy(self):
        if not (self.detached and self.on_cpu and self.widened):
            raise TypeError("can't convert this tensor to numpy")
        return self.array


def test_a_tensor_off_the_cpu_in_bfloat16_is_detached_moved_and_widened(node_module):
    frame = np.zeros((2, 3, 3), dtype=np.float32)
    frame[0, 0] = (1.0, 0.5, 0.0)
    _, array = decoded(node_module.to_png(DeviceTensor(frame)))
    assert tuple(array[0, 0]) == (255, 128, 0)


def test_a_jpeg_map_at_another_size_comes_back_float32_at_the_input_size(node_module):
    array = node_module.to_array(jpeg(166, 108), (333, 217))
    assert array.shape == (217, 333, 3)
    assert array.dtype == np.float32 and array.flags["C_CONTIGUOUS"]
    assert 0.0 <= array.min() <= array.max() <= 1.0
    assert abs(float(array[100, 100, 2]) - 1.0) < 0.02


def test_a_map_that_is_not_an_image_is_a_sentence(node_module, client_module):
    with pytest.raises(client_module.TrusapienError, match="could not be read"):
        node_module.to_array(b"<html>not a picture</html>", (4, 4))


def test_the_heatmap_output_is_float32(node):
    heatmap, *_ = node.validate_creative(np.random.rand(2, 6, 8, 3).astype(np.float32))
    assert heatmap.dtype == np.float32 and heatmap.shape == (2, 6, 8, 3)


def test_the_map_choices_are_the_services_result_files(client_module):
    assert set(client_module.MAPS.values()) == {
        "heat", "fog", "trust_heat", "intent_heat", "avoidance_heat", "memory_heat",
        "clarity_heat", "cognitive_demand_heat", "engagement_new_heat",
    }
