"""The 3.0 API removes caching and rejects obsolete settings explicitly."""

import asyncio
import time

import msgpack
import pytest

from proxy_mock.client import AsyncProxyMock, ProxyMock
from tests.test_recordings import upstream as upstream


@pytest.mark.parametrize("value", [None, 0, 60])
@pytest.mark.parametrize("method", ["PUT", "PATCH"])
@pytest.mark.parametrize("encoding", ["json", "msgpack"])
def test_removed_cache_field_is_rejected_by_http_without_mutation(client, value, method, encoding):
    client.configure_mock("/unchanged", body="kept")
    before = client.export_mocks()
    payload = {"cache_time": value, "mock_data": {"body": "must not change"}}
    arguments = (
        {"json": payload}
        if encoding == "json"
        else {"content": msgpack.packb(payload), "headers": {"Content-Type": "application/octet-stream"}}
    )
    response = client.execute_request(method, "/__admin/mocks?path=/unchanged", **arguments)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_mock"
    assert client.export_mocks() == before
    assert client.execute_request("GET", "/unchanged").text == "kept"


@pytest.mark.parametrize("method", ["configure_mock", "patch_mock"])
@pytest.mark.parametrize("value", [None, 0, 60])
def test_sync_client_rejects_removed_cache_option_locally(client, method, value):
    client.configure_mock("/unchanged", body="kept")
    before = client.export_mocks()
    with pytest.raises(TypeError, match="cache_time has been removed"):
        getattr(client, method)("/unchanged", cache_time=value)
    assert client.export_mocks() == before


@pytest.mark.parametrize("method", ["configure_mock", "patch_mock"])
@pytest.mark.parametrize("value", [None, 0, 60])
def test_async_client_rejects_removed_cache_option_locally(client, method, value):
    client.configure_mock("/unchanged", body="kept")
    before = client.export_mocks()

    async def scenario():
        async with AsyncProxyMock(client.host) as admin:
            with pytest.raises(TypeError, match="cache_time has been removed"):
                await getattr(admin, method)("/unchanged", cache_time=value)

    asyncio.run(scenario())
    assert client.export_mocks() == before


def test_cache_client_method_and_openapi_resource_are_removed(client):
    assert not hasattr(ProxyMock, "clean_cache")
    assert not hasattr(AsyncProxyMock, "clean_cache")
    schema = client.execute_request("GET", "/__admin/openapi.json").json()
    assert "/__admin/cache" not in schema["paths"]
    assert "cache_time" not in str(schema["paths"]["/__admin/mocks"])
    assert "cache_time" not in str(schema["paths"]["/__admin/snapshot"])


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
def test_removed_cache_endpoint_is_an_admin_404_and_cannot_be_shadowed(client, method):
    client.configure_mock("/{rest:path}", body="wildcard")
    response = client.execute_request(method, "/__admin/cache")
    assert response.status_code == 404
    if method != "HEAD":
        assert response.json()["error"]["code"] == "http_404"
    assert client.get_traffic()["count"] == 0
    assert client.execute_request("GET", "/ordinary").text == "wildcard"


def test_static_delay_applies_to_every_request(client):
    assert client.configure_mock("/delayed", body={"message": "same reply"}, timeout=0.05)["success"]
    for _ in range(2):
        started = time.monotonic()
        response = client.execute_request("GET", "/delayed")
        assert response.json() == {"message": "same reply"}
        assert time.monotonic() - started >= 0.05


@pytest.mark.parametrize("rule", [False, True])
def test_every_proxied_request_fetches_a_fresh_upstream_response(client, upstream, rule):
    config = {"rules": [{"input_data": {"proxy_host": upstream.host}}]} if rule else {"proxy_host": upstream.host}
    assert client.configure_mock("/fresh", **config)["success"]
    upstream.body = b"first"
    assert client.execute_request("GET", "/fresh").content == b"first"
    upstream.body = b"second"
    assert client.execute_request("GET", "/fresh").content == b"second"
    assert len(upstream.calls) == 2
    assert "cache_time" not in client.get_storage("/fresh")["data"]
    assert "cache_time" not in client.export_mocks()["mocks"][0]


@pytest.mark.parametrize("format", [1, 2])
@pytest.mark.parametrize("value", [None, 0])
def test_snapshots_with_disabled_legacy_cache_settings_remain_readable(client, format, value):
    snapshot = {"format": format, "mocks": [{"path": "/legacy", "mock_data": {"body": "kept"}, "cache_time": value}]}
    assert client.import_mocks(snapshot)["success"]
    assert client.execute_request("GET", "/legacy").text == "kept"
    assert "cache_time" not in client.get_storage("/legacy")["data"]
    assert "cache_time" not in client.export_mocks()["mocks"][0]


@pytest.mark.parametrize("format", [1, 2])
@pytest.mark.parametrize("mode", ["merge", "replace"])
@pytest.mark.parametrize("value", [60, -1, "0", False])
def test_active_or_invalid_cache_settings_in_snapshots_fail_atomically(client, format, mode, value):
    client.configure_mock("/ordered", sequence={"responses": [{"body": "A"}, {"body": "B"}]})
    client.execute_request("GET", "/ordered")
    before = client.export_mocks()
    snapshot = {
        "format": format,
        "mocks": [
            {"path": "/valid-first", "mock_data": {"body": "must not be installed"}},
            {"path": "/legacy", "cache_time": value},
        ],
    }
    result = client.import_mocks(snapshot, mode=mode)
    assert result["success"] is False
    assert "cache_time has been removed" in str(result["error"]["details"])
    assert client.export_mocks() == before
    assert client.get_sequence_state("/ordered")["data"]["position"] == 1
    assert client.execute_request("GET", "/valid-first").status_code == 404
