"""Migration paths exercise the same running server and preserve the legacy contracts."""

import asyncio
import socket
import threading
import time
import warnings

import pytest
import requests
import uvicorn

from proxy_mock.app import create_app
from proxy_mock.client import AsyncProxyMock, ProxyMock
from proxy_mock.core import deprecation


@pytest.fixture
def admin_server(monkeypatch):
    monkeypatch.setenv("PROXY_MOCK_ADMIN_PREFIX", "/test-admin/v3")
    app = create_app()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                server.should_exit = True
                thread.join(timeout=5)
                raise RuntimeError("admin migration test server did not start")
            time.sleep(0.01)
        host = f"http://127.0.0.1:{sock.getsockname()[1]}"
        try:
            yield host
        finally:
            requests.delete(host + "/test-admin/v3/mocks", timeout=5)
            server.should_exit = True
            thread.join(timeout=5)


def test_aliases_are_opt_in_and_do_not_reserve_existing_mock_paths(client, monkeypatch):
    monkeypatch.delenv("PROXY_MOCK_ADMIN_PREFIX", raising=False)
    client.configure_mock(path="/__admin/mocks", body="still a user mock")
    response = client.execute_request("GET", "/__admin/mocks")
    assert response.text == "still a user mock"
    assert "Deprecation" not in response.headers


@pytest.mark.parametrize(
    "prefix",
    ["", "/", "admin", "/admin/", "/admin?x=1", "/admin#x", "/a//b", "/%61dmin", "/traffic", "/storage/sub", "/docs"],
)
def test_invalid_prefix_is_rejected_by_server_and_clients(prefix, monkeypatch):
    monkeypatch.setenv("PROXY_MOCK_ADMIN_PREFIX", prefix)
    with pytest.raises(ValueError, match="admin_prefix"):
        create_app()
    for client_type in (ProxyMock, AsyncProxyMock):
        with pytest.raises(ValueError, match="admin_prefix"):
            client_type("http://localhost", admin_prefix=prefix)


@pytest.mark.parametrize(
    "method,path,payload,status",
    [
        ("GET", "/proxy_mock", None, 200),
        ("POST", "/configure_mock", {"path": "/example"}, 201),
        ("PATCH", "/configure_mock", {"path": "/absent"}, 400),
        ("GET", "/storage", None, 200),
        ("DELETE", "/storage", None, 200),
        ("POST", "/storage/clean", None, 200),
        ("GET", "/traffic", None, 200),
        ("DELETE", "/traffic", None, 200),
        ("POST", "/traffic/clean", None, 200),
        ("GET", "/traffic/settings", None, 200),
        ("PATCH", "/traffic/settings", {"max_items": 100}, 200),
        ("POST", "/traffic/settings", {"max_items": 100}, 200),
        ("GET", "/storage/snapshot", None, 200),
        ("POST", "/storage/snapshot", {"format": 1, "mocks": []}, 200),
        ("POST", "/cache/clean", None, 200),
    ],
)
def test_every_legacy_operation_links_to_migration(admin_server, method, path, payload, status):
    response = requests.request(method, admin_server + path, json=payload, timeout=5)
    assert response.status_code == status
    assert response.headers["Deprecation"] == deprecation.DEPRECATION_DATE
    assert 'rel="deprecation"' in response.headers["Link"]
    assert "MIGRATING.md" in response.headers["Link"]
    assert "Sunset" not in response.headers
    if path != "/cache/clean":
        assert "</test-admin/v3/" in response.headers["Link"] or "</test-admin/v3>" in response.headers["Link"]
        assert 'rel="successor-version"' in response.headers["Link"]


def test_alias_errors_match_legacy_and_user_routes_are_not_marked(admin_server):
    for payload in ({"path": "/missing"}, {}):
        old = requests.patch(admin_server + "/configure_mock", json=payload, timeout=5)
        new = requests.patch(admin_server + "/test-admin/v3/mocks", json=payload, timeout=5)
        assert (new.status_code, new.json()) == (old.status_code, old.json())
        assert "Deprecation" in old.headers
        assert "Deprecation" not in new.headers
    with ProxyMock(admin_server) as client:
        client.configure_mock(path="/storage", methods=["PUT"], body="custom method")
        response = client.execute_request("PUT", "/storage")
        assert response.text == "custom method"
        assert "Deprecation" not in response.headers


def test_sync_client_migrates_all_operations_without_changing_response_type(admin_server):
    prefix = "/test-admin/v3"
    with ProxyMock(admin_server, admin_prefix=prefix) as client:
        assert client.get_proxy_mock()["success"]
        assert client.configure_mock(path="/binary", body=b"\x00\xff")["success"]
        response = client.execute_request("GET", "/binary")
        assert isinstance(response, requests.Response)
        assert response.ok and response.content == b"\x00\xff"
        assert client.get_storage("/binary")["success"]
        assert client.patch_mock("/binary", body=b"\x00\xff", status_code=202)["success"]
        assert client.execute_request("GET", "/binary").status_code == 202
        assert client.get_traffic(path="/binary", method="GET", limit=1)["count"] == 1
        assert client.set_traffic_settings(max_items=7)["data"]["max_items"] == 7
        assert client.get_traffic_settings()["data"]["max_items"] == 7
        snapshot = client.export_mocks()
        assert client.clean_storage()["success"]
        assert client.import_mocks(snapshot, mode="replace")["success"]
        assert client.execute_request("GET", "/binary").content == b"\x00\xff"
        assert client.delete_mock("/binary")["success"]
        with pytest.warns(DeprecationWarning, match="clean_storage"):
            assert client.clean_storage(path="/missing")["success"] is False
        with pytest.warns(DeprecationWarning, match="clean_cache"):
            assert client.clean_cache()["success"]
        assert client.clean_traffic()["success"]
        assert client.get_traffic()["count"] == 0
        for path in ("", "/mocks", "/traffic", "/settings", "/snapshot"):
            response = client.execute_request("GET", prefix + path)
            assert response.status_code == 200
            assert "Deprecation" not in response.headers
        # Configuring/deleting a mock at a service path must not remove the alias.
        client.configure_mock(path=prefix + "/mocks", body="shadow")
        assert client.get_storage()["success"]
        client.clean_storage()
        assert client.get_storage()["success"]


def test_async_client_migrates_all_operations(admin_server):
    async def scenario():
        async with AsyncProxyMock(admin_server, admin_prefix="/test-admin/v3") as client:
            assert (await client.get_proxy_mock())["success"]
            assert (await client.configure_mock(path="/async", body=b"\x00\xff"))["success"]
            assert (await client.patch_mock("/async", body=b"\x00\xff", status_code=202))["success"]
            response = await client.execute_request("GET", "/async")
            assert response.status_code == 202 and response.content == b"\x00\xff"
            assert (await client.get_storage("/async"))["success"]
            assert (await client.get_traffic("/async", method="GET", limit=1))["count"] == 1
            assert (await client.set_traffic_settings(max_items=11))["data"]["max_items"] == 11
            assert (await client.get_traffic_settings())["data"]["max_items"] == 11
            snapshot = await client.export_mocks()
            await client.clean_storage()
            assert (await client.import_mocks(snapshot, mode="merge"))["success"]
            assert (await client.delete_mock("/async"))["success"]
            with pytest.warns(DeprecationWarning, match="clean_storage"):
                assert (await client.clean_storage(path="/missing"))["success"] is False
            with pytest.warns(DeprecationWarning, match="clean_cache"):
                assert (await client.clean_cache())["success"]
            await client.clean_traffic()
            assert (await client.get_traffic())["count"] == 0

    asyncio.run(scenario())


def test_python_warnings_use_normal_filtering_and_preserve_cache(client):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default", DeprecationWarning)
        for _ in range(3):
            with ProxyMock(client.host):
                pass
        for _ in range(3):
            client.configure_mock(path="/cached", body="ok", cache_time=60)
    assert len([w for w in caught if "httpx2" in str(w.message)]) == 1
    assert len([w for w in caught if "cache_time" in str(w.message)]) == 1
    assert client.get_storage("/cached")["data"]["cache_time"] == 60
    assert client.execute_request("GET", "/cached").text == "ok"


def test_deprecation_log_is_once_per_operation_and_links_are_preserved(monkeypatch):
    from fastapi import Response

    monkeypatch.setattr(deprecation, "_warned", set())
    messages = []
    monkeypatch.setattr(deprecation.app_logger, "warning", messages.append)
    for _ in range(3):
        response = deprecation.mark_deprecated(Response(headers={"Link": '</page>; rel="next"'}), "GET /storage")
        assert '</page>; rel="next"' in response.headers["Link"]
    assert len(messages) == 1


def test_openapi_marks_only_legacy_admin_operations(admin_server):
    paths = requests.get(admin_server + "/openapi.json", timeout=5).json()["paths"]
    for path, operations in paths.items():
        for operation in operations.values():
            assert bool(operation.get("deprecated")) == (not path.startswith("/test-admin/v3"))
