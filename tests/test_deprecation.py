"""Removed administrative actions cannot mutate resources in the 3.0 API."""

import asyncio

import pytest

from proxy_mock.client import AsyncProxyMock


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/proxy_mock"),
        ("POST", "/configure_mock"),
        ("PATCH", "/configure_mock"),
        ("GET", "/storage"),
        ("DELETE", "/storage"),
        ("POST", "/storage/clean"),
        ("GET", "/traffic"),
        ("DELETE", "/traffic"),
        ("POST", "/traffic/clean"),
        ("POST", "/traffic/settings"),
        ("GET", "/storage/snapshot"),
        ("POST", "/storage/snapshot"),
        ("POST", "/cache/clean"),
    ],
)
def test_legacy_operations_are_removed(client, method, path):
    client.configure_mock(path="/kept", body="kept")
    response = client.execute_request(method, path, json={"path": "/unexpected"})
    assert response.status_code == 404
    assert "Deprecation" not in response.headers
    assert list(client.get_storage()["data"]) == ["/kept"]


def test_resource_deletions_and_partial_settings(client, restore_traffic_settings):
    client.configure_mock(path="/test", body="ok")
    client.execute_request("GET", "/test")
    response = client.execute_request("DELETE", "/__admin/traffic")
    assert response.status_code == 200
    assert "Deprecation" not in response.headers
    assert client.get_traffic()["count"] == 0
    original = client.get_traffic_settings()["data"]["record_unknown_traffic"]
    response = client.execute_request("PATCH", "/__admin/settings", json={"max_items": 17})
    assert response.status_code == 200
    assert response.json()["data"] == {"record_unknown_traffic": original, "max_items": 17}
    assert "Deprecation" not in response.headers


@pytest.mark.parametrize("suffix", ["/mocks", "/traffic", "/settings", "/snapshot"])
def test_no_post_action_aliases_remain(client, suffix):
    response = client.execute_request("POST", "/__admin" + suffix, json={})
    assert response.status_code == 405
    assert "POST" not in response.headers["Allow"]
    assert response.json()["success"] is False


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize("argument", ["keyword-path", "keyword-none", "positional-path"])
def test_removed_clean_storage_selector_cannot_delete_mocks(client, asynchronous, argument):
    client.configure_mock("/kept", body="kept")
    args = ("/kept",) if argument == "positional-path" else ()
    kwargs = {} if args else {"path": None if argument == "keyword-none" else "/kept"}
    if asynchronous:

        async def scenario():
            async with AsyncProxyMock(client.host) as admin:
                with pytest.raises(TypeError):
                    await admin.clean_storage(*args, **kwargs)

        asyncio.run(scenario())
    else:
        with pytest.raises(TypeError):
            client.clean_storage(*args, **kwargs)
    assert client.get_storage("/kept")["data"]["mock_data"]["body"] == "kept"
