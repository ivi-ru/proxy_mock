"""Ordered responses are reserved atomically and managed through a state resource."""

import asyncio
import time

import httpx2
import pytest

from proxy_mock.client import AsyncProxyMock, ProxyMock
from tests.test_admin_migration import admin_server as admin_server


def sequence(*bodies, on_exhaustion="repeat_last"):
    return {"responses": [{"body": body} for body in bodies], "on_exhaustion": on_exhaustion}


def test_mock_sequence_repeats_last_and_shares_cursor_between_methods(client):
    assert client.configure_mock("/ordered", sequence=sequence("A", "B"))["success"]
    assert client.execute_request("GET", "/ordered").text == "A"
    assert client.execute_request("POST", "/ordered/?page=2").text == "B"
    assert client.execute_request("GET", "/ordered").text == "B"
    assert client.get_sequence_state("ordered/")["data"] == {
        "position": 2,
        "length": 2,
        "exhausted": True,
        "on_exhaustion": "repeat_last",
    }


def test_error_policy_is_terminal_and_reset_is_a_state_patch(client):
    client.configure_mock("/ordered", body="not a fallback", sequence=sequence("only", on_exhaustion="error"))
    assert client.execute_request("GET", "/ordered").text == "only"
    for _ in range(2):
        response = client.execute_request("GET", "/ordered")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "sequence_exhausted"
    assert client.reset_sequence("/ordered")["data"]["position"] == 0
    assert client.execute_request("GET", "/ordered").text == "only"
    response = client.execute_request("POST", "/__admin/sequence-state?path=/ordered", json={"position": 0})
    assert response.status_code == 405
    assert client.get_sequence_state("/ordered")["data"]["position"] == 1


def test_each_sequence_response_keeps_its_body_status_and_headers(client):
    definition = {
        "responses": [
            {
                "body": b"\x00\xff",
                "status_code": 202,
                "headers": {"X-Step": "first", "Content-Type": "application/octet-stream"},
            },
            {"body": {"ok": True}, "status_code": 201, "headers": {"X-Step": "second"}},
            {"body": None, "status_code": 204},
        ]
    }
    client.configure_mock("/typed", sequence=definition)
    first = client.execute_request("GET", "/typed")
    assert first.content == b"\x00\xff"
    assert first.status_code == 202 and first.headers["X-Step"] == "first"
    assert first.headers["Content-Type"] == "application/octet-stream"
    second = client.execute_request("GET", "/typed")
    assert second.json() == {"ok": True}
    assert second.status_code == 201 and second.headers["X-Step"] == "second"
    third = client.execute_request("GET", "/typed")
    assert third.status_code == 204 and third.content == b""


def test_rules_have_independent_cursors_and_keep_matching_priority(client):
    rules = [
        {"priority": 1, "input_data": {"methods": ["POST"]}, "sequence": sequence("low-1", "low-2")},
        {
            "priority": 2,
            "input_data": {"methods": ["POST"], "headers": {"X-High": "yes"}},
            "sequence": sequence("high", on_exhaustion="error"),
        },
    ]
    client.configure_mock("/rules", rules=rules, sequence=sequence("default-1", "default-2"))
    assert client.execute_request("GET", "/rules").text == "default-1"
    assert client.get_sequence_state("/rules", 0)["data"]["position"] == 0
    assert client.execute_request("POST", "/rules", headers={"X-High": "yes"}).text == "high"
    assert client.execute_request("POST", "/rules", headers={"X-High": "yes"}).status_code == 409
    assert client.get_sequence_state("/rules", 0)["data"]["position"] == 0
    assert client.get_sequence_state("/rules")["data"]["position"] == 1
    assert client.execute_request("POST", "/rules").text == "low-1"
    assert client.execute_request("POST", "/rules").text == "low-2"
    client.reset_sequence("/rules", 1)
    assert client.get_sequence_state("/rules", 0)["data"]["position"] == 2
    assert client.execute_request("POST", "/rules", headers={"X-High": "yes"}).text == "high"


def test_unmatched_requests_and_state_reads_do_not_consume_a_response(client):
    client.configure_mock("/only-get", methods=["GET"], sequence=sequence("A", "B"))
    assert client.execute_request("POST", "/only-get").status_code == 405
    assert client.execute_request("GET", "/other").status_code == 404
    for _ in range(2):
        assert client.get_sequence_state("/only-get")["data"]["position"] == 0
        assert client.execute_request("HEAD", "/__admin/sequence-state?path=/only-get").status_code == 200
        assert client.get_storage("/only-get")["data"]["sequence"]["responses"][0]["body"] == "A"
    assert client.execute_request("GET", "/only-get").text == "A"


def test_unrelated_patch_preserves_cursor_but_replacing_sequence_restarts_it(client):
    definition = sequence("A", "B")
    client.configure_mock("/ordered", sequence=definition)
    assert client.execute_request("GET", "/ordered").text == "A"
    assert client.patch_mock("/ordered", extra_info={"changed": True})["success"]
    assert client.get_sequence_state("/ordered")["data"]["position"] == 1
    assert client.execute_request("GET", "/ordered").text == "B"
    client.patch_mock("/ordered", sequence=definition)
    assert client.execute_request("GET", "/ordered").text == "A"
    client.configure_mock("/ordered", sequence=definition)
    assert client.execute_request("GET", "/ordered").text == "A"
    client.patch_mock("/ordered", sequence=None, body="static")
    assert client.get_sequence_state("/ordered")["error"]["code"] == "sequence_not_found"
    assert client.execute_request("GET", "/ordered").text == "static"


def test_replacing_rules_resets_only_rule_sequences(client):
    rules = [{"input_data": {"methods": ["POST"]}, "sequence": sequence("rule-1", "rule-2")}]
    client.configure_mock("/rules", rules=rules, sequence=sequence("default-1", "default-2"))
    assert client.execute_request("GET", "/rules").text == "default-1"
    assert client.execute_request("POST", "/rules").text == "rule-1"
    client.patch_mock("/rules", timeout=0.01)
    assert client.get_sequence_state("/rules", 0)["data"]["position"] == 1
    client.patch_mock("/rules", rules=rules)
    assert client.execute_request("POST", "/rules").text == "rule-1"
    assert client.execute_request("GET", "/rules").text == "default-2"
    client.patch_mock("/rules", rules=[])
    assert client.get_sequence_state("/rules", 0)["error"]["code"] == "sequence_not_found"


@pytest.mark.parametrize("rule", [False, True])
def test_concurrent_requests_each_reserve_one_response(client, rule):
    count = 30
    definition = sequence(*range(count), on_exhaustion="error")
    # Response bodies follow the existing mock contract: JSON objects, lists, strings, bytes or null.
    definition["responses"] = [{"body": {"index": i}} for i in range(count)]
    configuration = {"rules": [{"sequence": definition}]} if rule else {"sequence": definition}
    assert client.configure_mock("/concurrent", timeout=0.03, **configuration)["success"]

    async def scenario():
        async with httpx2.AsyncClient(base_url=client.host, timeout=10) as http:
            responses = await asyncio.gather(*(http.get("/concurrent") for _ in range(count + 5)))
            assert sorted(r.json()["index"] for r in responses if r.status_code == 200) == list(range(count))
            assert sum(r.status_code == 409 for r in responses) == 5

    asyncio.run(scenario())
    assert client.get_sequence_state("/concurrent", 0 if rule else None)["data"]["position"] == count


@pytest.mark.parametrize("operation", ["reset", "replace", "delete"])
def test_inflight_reservations_do_not_modify_new_state(client, operation):
    client.configure_mock("/inflight", timeout=0.2, sequence=sequence("old-1", "old-2"))

    async def scenario():
        async with AsyncProxyMock(client.host) as admin:
            pending = asyncio.create_task(admin.execute_request("GET", "/inflight"))
            try:
                deadline = time.monotonic() + 5
                while (await admin.get_sequence_state("/inflight"))["data"]["position"] != 1:
                    assert time.monotonic() < deadline, "The response was not reserved"
                    await asyncio.sleep(0.005)
                assert not pending.done(), "The reserved response must still be in flight"
                if operation == "reset":
                    await admin.reset_sequence("/inflight")
                elif operation == "replace":
                    await admin.configure_mock("/inflight", sequence=sequence("new-1", "new-2"))
                else:
                    await admin.delete_mock("/inflight")
                assert (await pending).text == "old-1"
                if operation == "delete":
                    assert (await admin.get_sequence_state("/inflight"))["error"]["code"] == "sequence_not_found"
                    assert (await admin.execute_request("GET", "/inflight")).status_code == 404
                else:
                    assert (await admin.get_sequence_state("/inflight"))["data"]["position"] == 0
                    expected = "old-1" if operation == "reset" else "new-1"
                    assert (await admin.execute_request("GET", "/inflight")).text == expected
            finally:
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "configuration",
    [
        {"sequence": {"responses": []}},
        {"sequence": {"responses": [{"body": "ok"}], "on_exhaustion": "cycle"}},
        {"sequence": {"responses": [{"unknown": True}]}},
        {"sequence": {"responses": [{"status_code": None}]}},
        {"sequence": sequence("A"), "cache_time": 60},
        {"sequence": sequence("A"), "proxy_host": "http://example.test"},
        {"rules": [{"sequence": sequence("A")}], "cache_time": 60},
        {"rules": [{"sequence": sequence("A")}], "proxy_host": "http://example.test"},
        {"rules": [{"input_data": {"proxy_host": "http://example.test"}, "sequence": sequence("A")}]},
    ],
)
def test_invalid_sequence_configuration_is_atomic(client, configuration):
    client.configure_mock("/unchanged", body="kept")
    before = client.get_storage("/unchanged")
    response = client.execute_request("PUT", "/__admin/mocks?path=/unchanged", json=configuration)
    assert response.status_code == 422
    assert client.get_storage("/unchanged") == before
    assert client.execute_request("GET", "/unchanged").text == "kept"


@pytest.mark.parametrize(
    "state",
    [
        {},
        {"position": 1},
        {"position": -1},
        {"position": False},
        {"position": "0"},
        {"position": None},
        {"position": 0, "unknown": True},
    ],
)
def test_invalid_state_update_keeps_the_cursor(client, state):
    client.configure_mock("/ordered", sequence=sequence("A", "B"))
    client.execute_request("GET", "/ordered")
    response = client.execute_request("PATCH", "/__admin/sequence-state?path=/ordered", json=state)
    assert response.status_code == 422
    assert client.get_sequence_state("/ordered")["data"]["position"] == 1


@pytest.mark.parametrize(
    "query,status",
    [
        ("", 422),
        ("path=", 422),
        ("path=/absent", 404),
        ("path=/ordered&rule=-1", 422),
        ("path=/ordered&rule=0", 404),
        ("path=/ordered&rule=0&rule=1", 422),
    ],
)
def test_sequence_resource_rejects_invalid_or_missing_selectors(client, query, status):
    client.configure_mock("/ordered", sequence=sequence("A", "B"))
    assert client.execute_request("GET", "/__admin/sequence-state?" + query).status_code == status
    assert client.get_sequence_state("/ordered")["data"]["position"] == 0


def test_both_clients_manage_sequences_with_a_custom_prefix(admin_server):
    host, prefix = admin_server
    with ProxyMock(host, admin_prefix=prefix) as sync:
        sync.configure_mock("/items/a+b&c=d#tag", sequence=sequence("A", "B"))
        assert sync.get_sequence_state("/items/a+b&c=d#tag")["data"]["position"] == 0
        assert sync.reset_sequence("/items/a+b&c=d#tag")["success"]
        assert sync.configure_mock("/async-sequence", sequence=sequence("A", "B"))["success"]

    async def scenario():
        async with AsyncProxyMock(host, admin_prefix=prefix) as client:
            assert (await client.execute_request("GET", "/async-sequence")).text == "A"
            assert (await client.get_sequence_state("/async-sequence"))["data"]["position"] == 1
            await client.reset_sequence("/async-sequence")
            assert (await client.execute_request("GET", "/async-sequence")).text == "A"
            await client.patch_mock("/async-sequence", sequence=sequence("new"))
            assert (await client.execute_request("GET", "/async-sequence")).text == "new"
            await client.clean_storage()
            assert (await client.get_sequence_state("/async-sequence"))["error"]["code"] == "sequence_not_found"

    asyncio.run(scenario())


@pytest.mark.parametrize("rule", [False, True])
def test_format_one_cannot_silently_lose_sequences(client, rule):
    mock = {"path": "/ordered"}
    mock.update({"rules": [{"sequence": sequence("A", "B")}]} if rule else {"sequence": sequence("A", "B")})
    response = client.execute_request("PUT", "/__admin/mocks?path=/ordered", json=mock)
    assert response.status_code == 201
    response = client.execute_request("GET", "/__admin/snapshot")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "unsupported_snapshot"
    response = client.execute_request("PUT", "/__admin/snapshot", json={"format": 1, "mocks": [mock]})
    assert response.status_code == 422
    assert client.get_sequence_state("/ordered", 0 if rule else None)["data"]["position"] == 0


def test_sequence_state_is_documented_without_action_routes(client):
    paths = client.execute_request("GET", "/__admin/openapi.json").json()["paths"]
    resource = paths["/__admin/sequence-state"]
    assert set(resource) == {"get", "patch"}
    assert "application/json" in resource["patch"]["requestBody"]["content"]
    assert not any("reset" in path for path in paths)
