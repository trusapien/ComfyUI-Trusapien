"""The client against a running Creative Validation API. Opt-in:

    TRUSAPIEN_TEST_API_URL=http://127.0.0.1:8080 TRUSAPIEN_TEST_API_KEY=cv_... pytest tests/test_live.py

Each run sends one new image, which is one analysis.
"""

import io
import os

import pytest
from PIL import Image

URL = os.environ.get("TRUSAPIEN_TEST_API_URL")
KEY = os.environ.get("TRUSAPIEN_TEST_API_KEY")

pytestmark = pytest.mark.skipif(not (URL and KEY), reason="needs TRUSAPIEN_TEST_API_URL and _KEY")


def test_an_image_is_analysed_and_its_map_read_and_a_rerun_is_free(client_module):
    buffer = io.BytesIO()
    Image.frombytes("RGB", (8, 8), os.urandom(8 * 8 * 3)).save(buffer, format="PNG")
    client = client_module.Client(KEY, base_url=URL)
    first = client.validate(buffer.getvalue(), deadline=120, interval=1)
    assert first["status"] == "done" and first["metrics"]
    assert client.asset(first, "heat")
    again = client.validate(buffer.getvalue(), deadline=120, interval=1)
    assert again["id"] == first["id"]
