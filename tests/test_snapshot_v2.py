"""Format 2 restores sequences and exact recorded replies without losing legacy import."""

import asyncio
import base64
import json
import threading
from copy import deepcopy

import pytest

from proxy_mock.client import AsyncProxyMock, ProxyMock
from proxy_mock.services.recordings import recording_id
from tests.test_admin_migration import admin_server as admin_server
from tests.test_recordings import configure, replay
from tests.test_recordings import upstream as upstream


def recording_entry(*, query="", method="GET", headers=None, body=b"", response=b"\x00\xffsaved"):
    request = {
        "method": method,
        "path": "/recorded",
        "query": query,
        "body_b64": base64.b64encode(body).decode("ascii"),
        "headers": headers or {},
    }
    return {
        "id": recording_id(request),
        "request": request,
        "response": {
            "status_code": 200,
            "headers": [["content-type", "application/octet-stream"]],
            "body_b64": base64.b64encode(response).decode("ascii"),
        },
    }


def snapshot_with_entry(entry=None, **config):
    return {
        "format": 2,
        "mocks": [
            {"path": "/recorded", "recording": {"mode": "replay", **config}, "recordings": [entry or recording_entry()]}
        ],
    }


def test_sequences_reset_cursors_and_all_binary_body_sections_round_trip(client):
    binary = b"\x00\xff\xfe"
    rules = [
        {
            "input_data": {"methods": ["POST"], "body": binary},
            "output_data": {"body": binary},
            "sequence": {"responses": [{"body": binary}, {"body": "second-rule"}], "on_exhaustion": "error"},
        }
    ]
    client.configure_mock(
        "/ordered", body=binary, rules=rules, sequence={"responses": [{"body": binary}, {"body": "second-default"}]}
    )
    assert client.execute_request("GET", "/ordered").content == binary
    assert client.execute_request("POST", "/ordered", content=binary).content == binary
    snapshot = client.export_mocks()
    assert snapshot["format"] == 2
    mock = snapshot["mocks"][0]
    sections = [
        mock["mock_data"],
        mock["sequence"]["responses"][0],
        mock["rules"][0]["input_data"],
        mock["rules"][0]["output_data"],
        mock["rules"][0]["sequence"]["responses"][0],
    ]
    assert all("body" not in section and base64.b64decode(section["body_b64"]) == binary for section in sections)
    assert "position" not in json.dumps(snapshot)
    # Export is observational: neither cursor was consumed or reset.
    assert client.get_sequence_state("/ordered")["data"]["position"] == 1
    assert client.get_sequence_state("/ordered", 0)["data"]["position"] == 1
    client.clean_storage()
    assert client.import_mocks(json.loads(json.dumps(snapshot)))["success"]
    assert client.get_sequence_state("/ordered")["data"]["position"] == 0
    assert client.get_sequence_state("/ordered", 0)["data"]["position"] == 0
    assert client.execute_request("GET", "/ordered").content == binary
    assert client.execute_request("GET", "/ordered").text == "second-default"
    assert client.execute_request("POST", "/ordered", content=binary).content == binary
    assert client.execute_request("POST", "/ordered", content=binary).text == "second-rule"
    assert client.execute_request("POST", "/ordered", content=binary).status_code == 409


@pytest.mark.parametrize("mode", ["record", "replay"])
def test_real_recordings_survive_json_round_trip_and_replay_without_upstream(client, upstream, mode):
    upstream.headers = [("Set-Cookie", "a=1"), ("Set-Cookie", "b=2"), ("X-Raw", "café".encode().decode("latin-1"))]
    upstream.status = 503
    configure(client, upstream, match_headers=["X-Key"])
    client.execute_request("POST", "/recorded?x=1&x=2", content=b"\xff\x00", headers={"X-Key": "yes"})
    if mode == "replay":
        replay(client, match_headers=["X-Key"])
    entries = client.get_recordings("/recorded")["data"]
    snapshot = json.loads(json.dumps(client.export_mocks()))
    assert snapshot["mocks"][0]["recordings"] == entries
    assert snapshot["mocks"][0]["recording"]["mode"] == mode
    client.clean_storage()
    assert client.import_mocks(snapshot, mode="replace")["success"]
    assert client.get_recordings("/recorded")["data"] == entries
    replay(client, match_headers=["X-Key"])
    response = client.execute_request("POST", "/recorded?x=1&x=2", content=b"\xff\x00", headers={"X-Key": "yes"})
    assert response.status_code == 503 and response.content == upstream.body
    assert response.headers.get_list("Set-Cookie") == ["a=1", "b=2"]
    assert (b"x-raw", "café".encode()) in response.headers.raw
    assert len(upstream.calls) == 1


def test_recording_order_survives_import_and_controls_future_eviction(client, upstream):
    configure(client, upstream, max_items=2)
    for query in ["x=1", "x=2", "x=1"]:
        client.execute_request("GET", "/recorded?" + query)
    snapshot = client.export_mocks()
    assert [entry["request"]["query"] for entry in snapshot["mocks"][0]["recordings"]] == ["x=2", "x=1"]
    client.import_mocks(snapshot)
    client.execute_request("GET", "/recorded?x=3")
    assert [entry["request"]["query"] for entry in client.get_recordings("/recorded")["data"]] == ["x=1", "x=3"]


@pytest.mark.parametrize("mode", ["merge", "replace"])
def test_import_replaces_supplied_collections_and_preserves_omitted_mocks_only_on_merge(client, mode):
    first = snapshot_with_entry()
    assert client.import_mocks(first)["success"]
    client.configure_mock("/ordered", sequence={"responses": [{"body": "A"}, {"body": "B"}]})
    client.execute_request("GET", "/ordered")
    replacement = snapshot_with_entry(recording_entry(response=b"replacement"))
    assert client.import_mocks(replacement, mode=mode)["success"]
    assert client.execute_request("GET", "/recorded").content == b"replacement"
    if mode == "merge":
        assert client.get_sequence_state("/ordered")["data"]["position"] == 1
        assert client.execute_request("GET", "/ordered").text == "B"
    else:
        assert client.execute_request("GET", "/ordered").status_code == 404
        assert client.get_sequence_state("/ordered")["error"]["code"] == "sequence_not_found"


def test_missing_recording_entries_means_empty_not_preserved_and_empty_replace_cleans_runtime(client):
    client.import_mocks(snapshot_with_entry())
    assert client.import_mocks({"format": 2, "mocks": [{"path": "/recorded", "recording": {"mode": "replay"}}]})[
        "success"
    ]
    assert client.get_recordings("/recorded")["data"] == []
    assert client.execute_request("GET", "/recorded").status_code == 404
    client.configure_mock("/ordered", sequence={"responses": [{"body": "A"}]})
    assert client.import_mocks({"format": 2, "mocks": []}, mode="replace")["success"]
    assert client.get_storage()["data"] == {}
    assert client.get_recordings("/recorded")["error"]["code"] == "recordings_not_found"
    assert client.get_sequence_state("/ordered")["error"]["code"] == "sequence_not_found"


@pytest.mark.parametrize("format", [1, 2])
def test_legacy_static_mock_imports_from_both_formats(client, format):
    snapshot = {
        "format": format,
        "mocks": [
            {
                "path": "/legacy",
                "mock_data": {"body_b64": "/wA="},
                "rules": [{"input_data": {"methods": ["POST"]}, "output_data": {"body": "rule"}}],
            }
        ],
    }
    assert client.import_mocks(snapshot)["success"]
    assert client.execute_request("GET", "/legacy").content == b"\xff\x00"
    assert client.execute_request("POST", "/legacy").text == "rule"
    assert client.export_mocks()["format"] == 2


@pytest.mark.parametrize("bad_format", [True, 1.0, "2", 0, 3, None])
def test_format_version_is_a_supported_integer(client, bad_format):
    response = client.execute_request("PUT", "/__admin/snapshot", json={"format": bad_format, "mocks": []})
    assert response.status_code == 422


@pytest.mark.parametrize("format", [1, 2])
def test_conflicting_binary_body_fields_are_rejected(client, format):
    response = client.execute_request(
        "PUT",
        "/__admin/snapshot",
        json={"format": format, "mocks": [{"path": "/ambiguous", "mock_data": {"body": "text", "body_b64": "eA=="}}]},
    )
    assert response.status_code == 422


def invalid_recording_cases():
    cases = []
    for changes in [
        {"id": "0" * 64},
        {"id": "bad"},
        {"unknown": True},
        {"request": {"method": "INVALID"}},
        {"request": {"path": "relative"}},
        {"request": {"query": "non ascii é"}},
        {"request": {"body_b64": "?"}},
        {"request": {"body_b64": "AB=="}},
        {"request": {"headers": {"X-Key": ["yes"]}}},
        {"response": {"status_code": True}},
        {"response": {"status_code": 199}},
        {"response": {"status_code": 600}},
        {"response": {"status_code": "200"}},
        {"response": {"body_b64": "?"}},
        {"response": {"headers": [["only-name"]]}},
        {"response": {"headers": [["invalid name", "value"]]}},
        {"response": {"headers": [["X-Unsafe", "line\r\nbreak"]]}},
        {"response": {"headers": [["X-Unicode", "\u0100"]]}},
        {"response": {"headers": [["Content-Encoding", "gzip"]]}},
        {"response": {"headers": [["Connection", "close"]]}},
        {"response": {"headers": [["X-Proxy-Mock-Recording", "stored"]]}},
        {"response": {"headers": [["Content-Length", "2"]]}},
        {"response": {"status_code": 204}},
        {"response": {"status_code": 304}},
    ]:
        entry = recording_entry()
        for key, value in changes.items():
            if key in {"request", "response"}:
                entry[key].update(value)
            else:
                entry[key] = value
        cases.append(snapshot_with_entry(entry))
    duplicate = snapshot_with_entry()
    duplicate["mocks"][0]["recordings"] *= 2
    cases += [duplicate, snapshot_with_entry(max_bytes=1), snapshot_with_entry(max_items=0)]
    missing_config = snapshot_with_entry()
    missing_config["mocks"][0].pop("recording")
    cases.append(missing_config)
    null_entries = snapshot_with_entry()
    null_entries["mocks"][0]["recordings"] = None
    cases.append(null_entries)
    unknown = snapshot_with_entry()
    unknown["future"] = True
    cases.append(unknown)
    for length in ["not-a-number", "-1"]:
        entry = recording_entry(method="HEAD", response=b"")
        entry["response"]["headers"] = [["content-length", length]]
        cases.append(snapshot_with_entry(entry))
    entry = recording_entry(method="HEAD", response=b"")
    entry["response"]["headers"] = [["content-length", "1"], ["Content-Length", "1"]]
    cases.append(snapshot_with_entry(entry))
    entry = recording_entry(method="HEAD")
    cases.append(snapshot_with_entry(entry))
    many = snapshot_with_entry(max_items=1)
    many["mocks"][0]["recordings"].append(recording_entry(query="other"))
    cases.append(many)
    selected = snapshot_with_entry(recording_entry(headers={"x-key": ["bad\r\nvalue"]}), match_headers=["X-Key"])
    cases.append(selected)
    return cases


@pytest.mark.parametrize("snapshot", invalid_recording_cases())
@pytest.mark.parametrize("mode", ["merge", "replace"])
def test_invalid_recordings_are_rejected_before_any_config_or_cursor_mutation(client, snapshot, mode):
    client.import_mocks(snapshot_with_entry())
    client.configure_mock("/ordered", sequence={"responses": [{"body": "A"}, {"body": "B"}]})
    client.execute_request("GET", "/ordered")
    before = client.export_mocks()
    snapshot = deepcopy(snapshot)
    snapshot["mocks"].insert(0, {"path": "/valid-first", "mock_data": {"body": "must not be installed"}})
    result = client.import_mocks(snapshot, mode=mode)
    assert not result["success"] and result["error"]["code"] == "invalid_snapshot"
    assert client.export_mocks() == before
    assert client.get_sequence_state("/ordered")["data"]["position"] == 1
    assert client.execute_request("GET", "/valid-first").status_code == 404
    assert client.execute_request("GET", "/recorded").content == b"\x00\xffsaved"


def test_head_empty_reply_and_selected_header_values_import(client):
    entry = recording_entry(method="HEAD", headers={"x-key": ["yes"]}, response=b"")
    entry["response"]["headers"] = [["content-length", "99"], ["Set-Cookie", "a=1"], ["Set-Cookie", "b=2"]]
    assert client.import_mocks(snapshot_with_entry(entry, match_headers=["X-Key"]))["success"]
    response = client.execute_request("HEAD", "/recorded", headers={"X-Key": "yes"})
    assert response.status_code == 200 and response.content == b""
    assert response.headers["Content-Length"] == "99"
    assert response.headers.get_list("Set-Cookie") == ["a=1", "b=2"]


def test_snapshot_replace_invalidates_pending_recordings(client, upstream):
    configure(client, upstream)
    client.execute_request("GET", "/recorded")
    snapshot = client.export_mocks()
    upstream.body = b"late"
    upstream.entered.clear()
    upstream.gate = threading.Event()

    async def scenario():
        async with AsyncProxyMock(client.host) as admin:
            pending = asyncio.create_task(admin.execute_request("GET", "/recorded"))
            try:
                assert await asyncio.to_thread(upstream.entered.wait, 5)
                assert not pending.done()
                assert (await admin.import_mocks(snapshot, mode="replace"))["success"]
                upstream.gate.set()
                response = await pending
                assert response.content == b"late"
                assert response.headers["X-Proxy-Mock-Recording"] == "superseded"
                assert (await admin.get_recordings("/recorded"))["data"] == snapshot["mocks"][0]["recordings"]
            finally:
                upstream.gate.set()
                await asyncio.gather(pending, return_exceptions=True)

    asyncio.run(scenario())


def test_both_clients_import_format_two_with_custom_admin_prefix(admin_server):
    host, prefix = admin_server
    with ProxyMock(host, admin_prefix=prefix) as client:
        assert client.import_mocks(snapshot_with_entry())["success"]
        snapshot = client.export_mocks()
        assert snapshot["format"] == 2
        assert client.execute_request("GET", "/recorded").content == b"\x00\xffsaved"
        client.clean_storage()

    async def scenario():
        async with AsyncProxyMock(host, admin_prefix=prefix) as client:
            assert (await client.import_mocks(snapshot, mode="replace"))["success"]
            assert (await client.execute_request("GET", "/recorded")).content == b"\x00\xffsaved"
            assert await client.export_mocks() == snapshot
            await client.clean_storage()

    asyncio.run(scenario())
