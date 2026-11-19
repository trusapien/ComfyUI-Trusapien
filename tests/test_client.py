import json

import pytest
import requests

PNG = b"\x89PNG fake"
DONE = {
    "id": "v-1",
    "status": "done",
    "metrics": {"focus": 78},
    "impact": None,
    "assets": [{"key": "original"}, {"key": "results.heat"}, {"key": "results.fog"}],
}


def client_for(client_module, session, **kwargs):
    ticks = iter(range(10_000))
    return client_module.Client(
        "cv_key", base_url="https://api.test/", session=session, sleep=lambda _: None,
        clock=lambda: next(ticks), **kwargs
    )


def test_the_key_comes_from_the_node_or_the_environment(client_module, monkeypatch):
    monkeypatch.delenv("TRUSAPIEN_API_KEY", raising=False)
    with pytest.raises(client_module.TrusapienError, match="TRUSAPIEN_API_KEY"):
        client_module.resolve_key("  ")
    monkeypatch.setenv("TRUSAPIEN_API_KEY", "cv_env")
    assert client_module.resolve_key("") == "cv_env"
    assert client_module.resolve_key(" cv_typed ") == "cv_typed"


def test_objectives_are_all_six_or_nothing(client_module):
    assert client_module.parse_objectives("") is None
    with pytest.raises(client_module.TrusapienError, match="valid JSON"):
        client_module.parse_objectives("{nope")
    with pytest.raises(client_module.TrusapienError, match="platform"):
        client_module.parse_objectives(json.dumps({"purpose": "awareness"}))
    full = {field: "x" for field in client_module.OBJECTIVE_FIELDS}
    assert client_module.parse_objectives(json.dumps(full)) == full


def test_the_same_image_is_the_same_key_and_another_image_is_not(client_module):
    key = client_module.idempotency_key
    assert key(PNG, None) == key(PNG, None)
    assert key(PNG, None) != key(PNG + b"!", None)
    assert key(PNG, None) != key(PNG, {"purpose": "awareness"})


def test_an_image_is_uploaded_once_and_polled_to_its_result(client_module, scripted):
    Session, Response = scripted
    session = Session(
        Response(202, {"id": "v-1", "status": "processing"}),
        Response(200, {"id": "v-1", "status": "processing"}),
        Response(200, DONE),
    )
    result = client_for(client_module, session).validate(PNG)
    assert result["metrics"] == {"focus": 78}
    method, url, sent = session.requests[0]
    assert (method, url) == ("POST", "https://api.test/v1/validations/upload")
    assert sent["headers"]["Authorization"] == "Bearer cv_key"
    assert sent["headers"]["Idempotency-Key"] == client_module.idempotency_key(PNG, None)
    assert [request[0] for request in session.requests] == ["POST", "GET", "GET"]


def test_objectives_ride_the_upload(client_module, scripted):
    Session, Response = scripted
    session = Session(Response(200, DONE))
    objectives = {field: "x" for field in client_module.OBJECTIVE_FIELDS}
    client_for(client_module, session).validate(PNG, objectives)
    assert json.loads(session.requests[0][2]["data"]["objectives"]) == objectives


@pytest.mark.parametrize("stale", ["error", "expired"])
def test_an_earlier_runs_dead_end_is_asked_afresh_once(client_module, scripted, stale):
    Session, Response = scripted
    session = Session(
        Response(200, {"id": "v-0", "status": stale, "error_code": "upstream_failed"}),
        Response(202, {"id": "v-1", "status": "processing"}),
        Response(200, DONE),
    )
    assert client_for(client_module, session).validate(PNG)["id"] == "v-1"
    first, second = (request[2]["headers"]["Idempotency-Key"] for request in session.requests[:2])
    assert second.startswith(first + "-")


def test_an_analysis_that_fails_says_why(client_module, scripted):
    Session, Response = scripted
    failed = {"id": "v-1", "status": "error", "error_code": "analysis_failed", "error_message": "Could not be analysed."}
    session = Session(Response(202, {"id": "v-1", "status": "processing"}), Response(200, failed))
    with pytest.raises(client_module.TrusapienError, match=r"Could not be analysed. \(analysis_failed\)"):
        client_for(client_module, session).validate(PNG)


def test_a_slow_analysis_stops_waiting_and_says_it_can_be_picked_up(client_module, scripted):
    Session, Response = scripted
    processing = Response(200, {"id": "v-1", "status": "processing"})
    session = Session(Response(202, {"id": "v-1", "status": "processing"}), *[processing] * 5)
    with pytest.raises(client_module.TrusapienError, match="without a second charge"):
        client_for(client_module, session).validate(PNG, deadline=3)


@pytest.mark.parametrize(
    "answer, says",
    [
        ((401, {"detail": "The key was not recognised."}), "key was not recognised"),
        ((422, {"detail": "a.png: unsupported format."}), "unsupported format"),
        ((413, {"detail": "too large"}), "too large"),
        ((429, {"detail": "busy"}), "still being processed"),
        ((503, None), "HTTP 503"),
    ],
)
def test_a_refusal_reads_as_a_sentence(client_module, scripted, answer, says):
    Session, Response = scripted
    with pytest.raises(client_module.TrusapienError, match=says):
        client_for(client_module, Session(Response(*answer))).validate(PNG)


def test_an_unreachable_api_reads_as_a_sentence(client_module, scripted):
    Session, _ = scripted
    with pytest.raises(client_module.TrusapienError, match="could not be reached"):
        client_for(client_module, Session(requests.ConnectionError("dns"))).validate(PNG)


def test_a_map_is_found_by_its_name_and_a_missing_one_is_none(client_module, scripted):
    Session, Response = scripted
    session = Session(Response(200, content=b"fog-bytes"))
    client = client_for(client_module, session)
    assert client.asset(DONE, "fog") == b"fog-bytes"
    assert session.requests[0][1] == "https://api.test/v1/validations/v-1/assets/results.fog"
    assert client.asset(DONE, "trust_heat") is None
    assert client_module.summary(DONE)["maps"] == ["fog", "heat"]
