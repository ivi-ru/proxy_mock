"""The administrative resource API works with default and custom prefixes."""

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


@pytest.fixture
def admin_server(monkeypatch, request):
    prefix = getattr(request, "param", "/test-admin/v3")
    if prefix is None:
        monkeypatch.delenv("PROXY_MOCK_ADMIN_PREFIX", raising=False)
        prefix = "/__admin"
    else:
        monkeypatch.setenv("PROXY_MOCK_ADMIN_PREFIX", prefix)
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
                raise RuntimeError("admin test server did not start")
            time.sleep(0.01)
        host = f"http://127.0.0.1:{sock.getsockname()[1]}"
        try:
            yield host, prefix
        finally:
            try:
                requests.delete(host + prefix + "/mocks", timeout=5)
            finally:
                server.should_exit = True
                thread.join(timeout=5)


def assert_error(response, status):
    assert response.status_code == status, response.text
    payload = response.json()
    assert payload["success"] is False
    assert isinstance(payload["error"], dict)
    assert isinstance(payload["error"]["code"], str) and payload["error"]["code"]
    assert isinstance(payload["error"]["message"], str) and payload["error"]["message"]
    assert "Deprecation" not in response.headers
    assert "Sunset" not in response.headers


@pytest.mark.parametrize("admin_server", [None, "/test-admin/v3", "/traffic", "/storage/sub", "/docs"], indirect=True)
def test_default_and_custom_prefixes_expose_resources(admin_server):
    host, prefix = admin_server
    for suffix in ("", "/mocks", "/traffic", "/settings", "/snapshot"):
        response = requests.get(host + prefix + suffix, timeout=5)
        assert response.status_code == 200
        assert "Deprecation" not in response.headers
        assert "Sunset" not in response.headers
        assert 'rel="deprecation"' not in response.headers.get("Link", "")
    assert requests.get(host + prefix, timeout=5).json()["version"]


@pytest.mark.parametrize(
    "prefix", ["", "/", "admin", "/admin/", "/admin?x=1", "/admin#x", "/a//b", "/%61dmin", "/a{path}"]
)
def test_invalid_prefix_is_rejected_by_server_and_clients(prefix, monkeypatch):
    monkeypatch.setenv("PROXY_MOCK_ADMIN_PREFIX", prefix)
    with pytest.raises(ValueError, match="admin_prefix"):
        create_app()
    for client_type in (ProxyMock, AsyncProxyMock):
        with pytest.raises(ValueError, match="admin_prefix"):
            client_type("http://localhost", admin_prefix=prefix)


def test_mock_resource_create_replace_read_and_delete(admin_server):
    host, prefix = admin_server
    url = host + prefix + "/mocks"
    response = requests.put(url, params={"path": "example/"}, json={"mock_data": {"body": "first"}}, timeout=5)
    assert response.status_code == 201
    assert response.json()["success"]
    assert requests.get(host + "/example", timeout=5).text == "first"
    response = requests.put(
        url, params={"path": "/example"}, json={"path": "example/", "mock_data": {"body": "second"}}, timeout=5
    )
    assert response.status_code == 200
    response = requests.get(url, params={"path": "/example"}, timeout=5)
    assert response.status_code == 200
    assert response.json()["data"]["mock_data"]["body"] == "second"
    assert list(requests.get(url, timeout=5).json()["data"]) == ["/example"]
    assert requests.delete(url, params={"path": "/example"}, timeout=5).status_code == 200
    assert_error(requests.get(url, params={"path": "/example"}, timeout=5), 404)
    assert requests.get(host + "/example", timeout=5).status_code == 404


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_missing_mock_is_not_found(admin_server, method):
    host, prefix = admin_server
    response = requests.request(method, host + prefix + "/mocks", params={"path": "/absent"}, json={}, timeout=5)
    assert_error(response, 404)


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
def test_empty_mock_path_is_invalid_and_never_clears_storage(admin_server, method):
    host, prefix = admin_server
    with ProxyMock(host, admin_prefix=prefix) as client:
        assert client.configure_mock(path="/kept", body="kept")["success"]
        response = requests.request(method, host + prefix + "/mocks", params={"path": ""}, json={}, timeout=5)
        assert_error(response, 422)
        assert client.execute_request("GET", "/kept").text == "kept"
        assert list(client.get_storage()["data"]) == ["/kept"]


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_mutations_require_query_path_and_matching_body_path(admin_server, method):
    host, prefix = admin_server
    url = host + prefix + "/mocks"
    with ProxyMock(host, admin_prefix=prefix) as client:
        client.configure_mock(path="/kept", body="kept")
        assert_error(requests.request(method, url, json={"path": "/kept"}, timeout=5), 422)
        assert_error(requests.request(method, url, params={"path": "/kept"}, json={"path": "/other"}, timeout=5), 422)
        assert client.execute_request("GET", "/kept").text == "kept"
        assert list(client.get_storage()["data"]) == ["/kept"]


def test_patch_retains_omitted_values_and_clears_explicit_nulls(admin_server):
    host, prefix = admin_server
    url = host + prefix + "/mocks"
    original = {
        "mock_data": {"body": "kept", "status_code": 202, "headers": {"X-Test": "kept"}},
        "extra_info": {"source": "test"},
        "timeout": 0.01,
        "proxy_host": "http://example.test",
    }
    assert requests.put(url, params={"path": "/partial"}, json=original, timeout=5).status_code == 201
    patch = {"extra_info": None, "timeout": None, "proxy_host": None}
    response = requests.patch(url, params={"path": "/partial"}, json=patch, timeout=5)
    assert response.status_code == 200
    saved = requests.get(url, params={"path": "/partial"}, timeout=5).json()["data"]
    assert saved["mock_data"] == original["mock_data"]
    for field in patch:
        assert saved[field] is None
    assert requests.get(host + "/partial", timeout=5).text == "kept"
    response = requests.patch(url, params={"path": "/partial"}, json={"mock_data": {"body": None}}, timeout=5)
    assert response.status_code == 200
    response = requests.get(host + "/partial", timeout=5)
    assert response.content == b""
    assert response.status_code == 202
    assert response.headers["X-Test"] == "kept"


def test_patch_rules_replace_the_list_and_empty_list_clears_it(admin_server):
    host, prefix = admin_server
    url = host + prefix + "/mocks"
    first = {"input_data": {"methods": ["GET"]}, "output_data": {"body": "first"}}
    second = {"input_data": {"methods": ["POST"]}, "output_data": {"body": "second"}}
    with ProxyMock(host, admin_prefix=prefix) as client:
        client.configure_mock(path="/rules", body="fallback", rules=[first])
        assert requests.patch(url, params={"path": "/rules"}, json={"rules": [second]}, timeout=5).status_code == 200
        assert len(client.get_storage("/rules")["data"]["rules"]) == 1
        assert client.execute_request("GET", "/rules").text == "fallback"
        assert client.execute_request("POST", "/rules").text == "second"
        assert requests.patch(url, params={"path": "/rules"}, json={"rules": []}, timeout=5).status_code == 200
        assert client.get_storage("/rules")["data"]["rules"] == []
        assert client.execute_request("POST", "/rules").text == "fallback"


def test_snapshot_put_replaces_and_patch_merges(admin_server):
    host, prefix = admin_server
    url = host + prefix + "/snapshot"
    snapshot = {"format": 1, "protocol": "http", "mocks": [{"path": "/loaded", "mock_data": {"body": "loaded"}}]}
    with ProxyMock(host, admin_prefix=prefix) as client:
        client.configure_mock(path="/existing", body="existing")
        assert requests.patch(url, json=snapshot, timeout=5).status_code == 200
        assert sorted(client.get_storage()["data"]) == ["/existing", "/loaded"]
        assert requests.put(url, json=snapshot, timeout=5).status_code == 200
        assert list(client.get_storage()["data"]) == ["/loaded"]
        assert client.execute_request("GET", "/existing").status_code == 404
        exported = requests.get(url, timeout=5).json()
        assert exported["format"] == 2
        assert exported["mocks"][0]["path"] == "/loaded"


@pytest.mark.parametrize(
    "method,suffix,payload,content_type,status",
    [
        ("PUT", "/mocks?path=/invalid", b"{", "application/json", 400),
        ("PUT", "/mocks?path=/invalid", b"invalid", "text/plain", 415),
        ("PUT", "/mocks?path=/invalid", b"[]", "application/json", 422),
        ("PATCH", "/settings", b'{"max_items": 0}', "application/json", 422),
        ("PUT", "/snapshot", b'{"format": 99, "mocks": []}', "application/json", 422),
    ],
)
def test_admin_errors_have_a_consistent_envelope(admin_server, method, suffix, payload, content_type, status):
    host, prefix = admin_server
    response = requests.request(
        method, host + prefix + suffix, data=payload, headers={"Content-Type": content_type}, timeout=5
    )
    assert_error(response, status)


def test_sync_client_uses_resources_and_preserves_response_type(admin_server):
    host, prefix = admin_server
    with ProxyMock(host, admin_prefix=prefix) as client:
        assert client.get_proxy_mock()["success"]
        assert client.configure_mock(path="/binary", body=b"\x00\xff")["success"]
        response = client.execute_request("GET", "/binary")
        assert isinstance(response, requests.Response)
        assert response.ok and response.content == b"\x00\xff"
        assert client.get_storage("/binary")["success"]
        assert client.patch_mock("/binary", status_code=202)["success"]
        assert client.execute_request("GET", "/binary").content == b"\x00\xff"
        assert client.execute_request("GET", "/binary").status_code == 202
        assert client.get_traffic(path="/binary", method="GET", limit=1)["count"] == 1
        assert client.set_traffic_settings(max_items=7)["data"]["max_items"] == 7
        assert client.get_traffic_settings()["data"]["max_items"] == 7
        snapshot = client.export_mocks()
        assert client.clean_storage()["success"]
        assert client.import_mocks(snapshot, mode="replace")["success"]
        assert client.execute_request("GET", "/binary").content == b"\x00\xff"
        assert client.patch_mock("/binary", body=None)["success"]
        assert client.execute_request("GET", "/binary").content == b""
        assert client.delete_mock("/binary")["success"]
        assert client.delete_mock("/missing")["success"] is False
        with pytest.raises(AttributeError):
            client.clean_cache()
        assert client.clean_traffic()["success"]
        assert client.get_traffic()["count"] == 0


def test_async_client_uses_resources(admin_server):
    host, prefix = admin_server

    async def scenario():
        async with AsyncProxyMock(host, admin_prefix=prefix) as client:
            assert (await client.get_proxy_mock())["success"]
            assert (await client.configure_mock(path="/async", body=b"\x00\xff"))["success"]
            assert (await client.patch_mock("/async", status_code=202))["success"]
            response = await client.execute_request("GET", "/async")
            assert response.status_code == 202 and response.content == b"\x00\xff"
            assert (await client.get_storage("/async"))["success"]
            assert (await client.get_traffic("/async", method="GET", limit=1))["count"] == 1
            assert (await client.set_traffic_settings(max_items=11))["data"]["max_items"] == 11
            assert (await client.get_traffic_settings())["data"]["max_items"] == 11
            snapshot = await client.export_mocks()
            await client.clean_storage()
            assert (await client.import_mocks(snapshot, mode="merge"))["success"]
            assert (await client.patch_mock("/async", body=None))["success"]
            assert (await client.execute_request("GET", "/async")).content == b""
            assert (await client.delete_mock("/async"))["success"]
            assert (await client.delete_mock("/missing"))["success"] is False
            with pytest.raises(AttributeError):
                await client.clean_cache()
            await client.clean_traffic()
            assert (await client.get_traffic())["count"] == 0

    asyncio.run(scenario())


def test_python_transport_warnings_use_normal_filtering(client):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default", DeprecationWarning)
        for _ in range(3):
            with ProxyMock(client.host):
                pass
    assert len([w for w in caught if "httpx2" in str(w.message)]) == 1


def test_openapi_documents_resources_and_request_and_response_contracts(admin_server):
    host, prefix = admin_server
    schema = requests.get(host + prefix + "/openapi.json", timeout=5).json()
    paths = schema["paths"]
    expected = {
        "/mocks": {"get", "put", "patch", "delete"},
        "/traffic": {"get", "delete"},
        "/settings": {"get", "patch"},
        "/snapshot": {"get", "put", "patch"},
    }
    for suffix, methods in expected.items():
        path = prefix + suffix if prefix + suffix in paths else suffix
        assert set(paths[path]) == methods
        for operation in paths[path].values():
            assert not operation.get("deprecated", False)
            assert operation["responses"]
    mocks = paths.get(prefix + "/mocks", paths.get("/mocks"))
    for method in ("put", "patch"):
        operation = mocks[method]
        assert any(p["name"] == "path" and p["in"] == "query" and p["required"] for p in operation["parameters"])
        assert "application/json" in operation["requestBody"]["content"]
        assert "422" in operation["responses"]
    for suffix in ("/docs", "/redoc"):
        response = requests.get(host + prefix + suffix, timeout=5)
        assert response.status_code == 200
        assert prefix + "/openapi.json" in response.text


@pytest.mark.parametrize(
    "changes",
    [
        {"unexpected": True},
        {"mock_data": {"status_cod": 201}},
        {"mock_data": {"status_code": None}},
        {"mock_data": None},
        {"rules": [{"input_data": {"metods": ["GET"]}}]},
        {"rules": [{"output_data": {"status_code": None}}]},
    ],
)
def test_invalid_patch_preserves_the_entire_mock(client, changes):
    client.configure_mock(path="/atomic", body="original", headers={"X-Original": "yes"})
    before = client.get_storage("/atomic")
    response = client.execute_request("PATCH", "/__admin/mocks?path=/atomic", json=changes)
    assert_error(response, 422)
    assert client.get_storage("/atomic") == before
    assert client.execute_request("GET", "/atomic").text == "original"


def test_repeated_put_and_snapshot_merge_are_idempotent(client):
    body = {
        "mock_data": {"body": "default"},
        "rules": [{"input_data": {"methods": ["POST"]}, "output_data": {"body": "rule"}}],
    }
    first = client.execute_request("PUT", "/__admin/mocks?path=/idempotent", json=body)
    assert first.status_code == 201
    assert first.headers["Location"] == "/__admin/mocks?path=%2Fidempotent"
    snapshot = client.export_mocks()
    second = client.execute_request("PUT", "/__admin/mocks?path=/idempotent", json=body)
    assert second.status_code == 200
    assert client.export_mocks() == snapshot
    for _ in range(2):
        assert client.import_mocks(snapshot)["success"]
    assert client.export_mocks() == snapshot


@pytest.mark.parametrize("query", ["path=", "path=/x&path=/y", "unknown=x"])
def test_invalid_delete_selector_never_deletes_the_collection(client, query):
    client.configure_mock(path="/kept", body="ok")
    response = client.execute_request("DELETE", "/__admin/mocks?" + query)
    assert_error(response, 422)
    assert list(client.get_storage()["data"]) == ["/kept"]


@pytest.mark.parametrize("query", ["limit=-1", "limit=0", "limit=no", "method=INVALID", "other=1"])
def test_invalid_traffic_filters_are_rejected(client, query):
    assert_error(client.execute_request("GET", "/__admin/traffic?" + query), 422)


def test_delete_traffic_rejects_filters_without_losing_records(client):
    client.configure_mock(path="/kept", body="ok")
    client.execute_request("GET", "/kept")
    assert_error(client.execute_request("DELETE", "/__admin/traffic?path=/kept"), 422)
    assert client.get_traffic()["count"] == 1


def test_invalid_utf8_is_a_client_error(client):
    response = client.execute_request(
        "PUT", "/__admin/mocks?path=/invalid", data=b"\xff", headers={"Content-Type": "application/json"}
    )
    assert_error(response, 400)


def test_json_charset_parameter_is_supported(client):
    response = client.execute_request(
        "PUT", "/__admin/mocks?path=/charset", data=b"{}", headers={"Content-Type": "application/json; charset=utf-8"}
    )
    assert response.status_code == 201


def test_snapshot_with_duplicate_identity_is_atomic(client):
    client.configure_mock(path="/kept", body="ok")
    response = client.execute_request(
        "PUT", "/__admin/snapshot", json={"format": 1, "mocks": [{"path": "/duplicate"}, {"path": "duplicate/"}]}
    )
    assert_error(response, 422)
    assert list(client.get_storage()["data"]) == ["/kept"]


@pytest.mark.parametrize("suffix", ["", "/mocks", "/traffic", "/settings", "/snapshot", "/docs", "/openapi.json"])
def test_head_reads_resource_headers_without_a_body(client, suffix):
    response = client.execute_request("HEAD", "/__admin" + suffix)
    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get_traffic()["count"] == 0


def test_both_clients_can_explicitly_clear_nullable_fields(admin_server):
    host, prefix = admin_server
    setup = {"headers": {"X-Clear": "yes"}, "extra_info": {"a": 1}, "proxy_host": "http://example.test", "timeout": 1}
    clear = dict.fromkeys(setup)

    def check(data):
        assert data["mock_data"]["headers"] == {}
        assert data["mock_data"]["body"] == "kept"
        for key in ("extra_info", "proxy_host", "timeout"):
            assert data[key] is None

    with ProxyMock(host, admin_prefix=prefix) as client:
        assert client.configure_mock("/nullable", body="kept", **setup)["success"]
        assert client.patch_mock("/nullable", **clear)["success"]
        check(client.get_storage("/nullable")["data"])

    async def scenario():
        async with AsyncProxyMock(host, admin_prefix=prefix) as client:
            assert (await client.configure_mock("/nullable", body="kept", **setup))["success"]
            assert (await client.patch_mock("/nullable", **clear))["success"]
            check((await client.get_storage("/nullable"))["data"])

    asyncio.run(scenario())


def test_factory_can_be_mounted_under_a_parent_path(monkeypatch):
    import httpx2
    from fastapi import FastAPI

    monkeypatch.setenv("PROXY_MOCK_ADMIN_PREFIX", "/admin/v3")
    app = create_app()
    parent = FastAPI()
    parent.mount("/embedded", app)

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=parent), base_url="http://test") as client:
                response = await client.put(
                    "/embedded/admin/v3/mocks?path=/mounted", json={"mock_data": {"body": "ok"}}
                )
                assert response.status_code == 201
                assert response.headers["Location"] == "/embedded/admin/v3/mocks?path=%2Fmounted"
                assert (await client.get(response.headers["Location"])).status_code == 200
                assert (await client.get("/embedded/mounted")).text == "ok"
                assert (await client.get("/embedded/admin/v3/missing")).status_code == 404
                assert (await client.get("/embedded/admin/v3/traffic")).json()["count"] == 1
                await client.delete("/embedded/admin/v3/mocks")

    asyncio.run(scenario())
