"""The real client against `tools/stub_service.py`, so the stub keeps answering
the way the client expects (and the way the service does, as far as we know it).
"""

import importlib.util
import io
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def stub_module():
    spec = importlib.util.spec_from_file_location("trusapien_stub_service", ROOT / "tools" / "stub_service.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def stub(stub_module):
    server, state = stub_module.serve(port=0, quiet=True, processing_seconds=0.1)
    yield f"http://127.0.0.1:{server.server_port}", state
    server.shutdown()
    server.server_close()


def png(width=40, height=30, colour=(10, 200, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="PNG")
    return buffer.getvalue()


def test_an_upload_is_processed_then_done_with_every_metric_and_map(client_module, stub_module, stub):
    url, state = stub
    validation = client_module.Client("cv_key", base_url=url).validate(png(), interval=0.05, deadline=5)
    assert validation["status"] == "done"
    assert set(validation["metrics"]) == set(stub_module.METRICS)
    assert client_module.summary(validation)["maps"] == list(client_module.MAPS)  # every choice, in order
    assert set(client_module.MAPS.values()) == set(stub_module.MAPS)
    assert state.stats()["requests"] >= 2  # it was polled at least once


def test_a_map_is_jpeg_at_half_the_images_size(client_module, stub):
    url, _ = stub
    client = client_module.Client("cv_key", base_url=url)
    validation = client.validate(png(40, 30), interval=0.05, deadline=5)
    picture = Image.open(io.BytesIO(client.asset(validation, "trust_heat")))
    assert picture.format == "JPEG" and picture.size == (20, 15)


def test_the_same_image_and_objectives_are_one_analysis(client_module, stub):
    url, state = stub
    client = client_module.Client("cv_key", base_url=url)
    objectives = {field: "x" for field in client_module.OBJECTIVE_FIELDS}
    first = client.validate(png(), interval=0.05, deadline=5)
    again = client.validate(png(), interval=0.05, deadline=5)
    assert again["id"] == first["id"]
    assert state.stats()["analyses"] == 1
    client.validate(png(), objectives, interval=0.05, deadline=5)
    client.validate(png(colour=(0, 0, 0)), interval=0.05, deadline=5)
    assert state.stats()["analyses"] == 3


def test_an_omitted_map_is_none_to_the_client(client_module, stub):
    url, state = stub
    state.mode["omit"] = ["trust_heat"]
    client = client_module.Client("cv_key", base_url=url)
    validation = client.validate(png(), interval=0.05, deadline=5)
    assert client.asset(validation, "trust_heat") is None
    assert "Trust" not in client_module.summary(validation)["maps"]


def test_a_listed_map_the_stub_will_not_serve_is_the_clients_sentence(client_module, stub):
    url, state = stub
    state.mode["missing_files"] = ["trust_heat"]
    client = client_module.Client("cv_key", base_url=url)
    validation = client.validate(png(), interval=0.05, deadline=5)
    assert "Trust" in client_module.summary(validation)["maps"]
    with pytest.raises(client_module.TrusapienError, match=r"lists a Trust map, but it could not be downloaded\. .*No such asset\."):
        client.asset(validation, "trust_heat")


def test_a_corrupt_map_is_served_as_bytes_that_are_no_image(client_module, node_module, stub):
    url, state = stub
    state.mode["corrupt"] = ["trust_heat"]
    client = client_module.Client("cv_key", base_url=url)
    content = client.asset(client.validate(png(), interval=0.05, deadline=5), "trust_heat")
    with pytest.raises(client_module.TrusapienError, match="The Trust map the API returned could not be read"):
        node_module.to_array(content, (40, 30), "Trust")


def test_a_refused_key_is_the_clients_sentence(client_module, stub):
    url, state = stub
    state.mode["reject_all"] = True
    with pytest.raises(client_module.TrusapienError, match="key was not recognised"):
        client_module.Client("cv_key", base_url=url).validate(png(), interval=0.05, deadline=5)
    assert state.stats()["analyses"] == 0
