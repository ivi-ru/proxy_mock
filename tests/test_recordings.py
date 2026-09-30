"""Record real loopback HTTP replies, then replay without making an upstream request."""

import asyncio
import base64
import gzip
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlencode

import httpx2
import pytest

from proxy_mock.client import AsyncProxyMock, ProxyMock
from tests.test_admin_migration import admin_server as admin_server


@pytest.fixture
def upstream():
    state = SimpleNamespace(
        calls=[], status=200, body=b"\x00\xffrecorded", headers=[], entered=threading.Event(), gate=None
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = self.rfile.read(int(self.headers.get("content-length", 0)))
            state.calls.append((self.command, self.path, body))
            status, response_body, headers = state.status, state.body, list(state.headers)
            state.entered.set()
            if state.gate is not None:
                assert state.gate.wait(5), "The test did not release the upstream response"
            self.send_response(status)
            for name, value in headers:
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response_body)

        do_POST = do_GET
        do_HEAD = do_GET

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.host = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        if state.gate is not None:
            state.gate.set()
        server.shutdown()
        server.server_close()
        thread.join(5)


def configure(client, upstream, path="/recorded", **recording):
    result = client.configure_mock(path, proxy_host=upstream.host, recording={"mode": "record", **recording})
    assert result["success"], result


def replay(client, path="/recorded", **recording):
    result = client.patch_mock(path, recording={"mode": "replay", **recording})
    assert result["success"], result


def test_binary_response_and_duplicate_headers_round_trip(client, upstream):
    upstream.status = 201
    upstream.headers = [("Set-Cookie", "a=1"), ("Set-Cookie", "b=2"), ("Content-Type", "application/octet-stream")]
    configure(client, upstream)
    first = client.execute_request("POST", "/recorded?x=1&x=2", content=b"\xff\x00")
    assert first.status_code == 201 and first.content == upstream.body
    assert first.headers["X-Proxy-Mock-Recording"] == "stored"
    entries = client.get_recordings("/recorded")["data"]
    assert len(entries) == 1
    entry = entries[0]
    assert base64.b64decode(entry["request"]["body_b64"]) == b"\xff\x00"
    assert entry["request"]["query"] == "x=1&x=2"
    assert base64.b64decode(entry["response"]["body_b64"]) == upstream.body
    assert [v for k, v in entry["response"]["headers"] if k == "set-cookie"] == ["a=1", "b=2"]
    assert client.get_recordings("/recorded", entry["id"])["data"] == entry
    replay(client)
    upstream.body = b"must not be fetched"
    for _ in range(2):
        response = client.execute_request("POST", "/recorded?x=1&x=2", content=b"\xff\x00")
        assert response.status_code == 201 and response.content == first.content
        assert response.headers.get_list("Set-Cookie") == ["a=1", "b=2"]
        assert "X-Proxy-Mock-Recording" not in response.headers
    assert len(upstream.calls) == 1


@pytest.mark.parametrize("status", [204, 302, 404, 500, 502, 504])
def test_http_responses_including_upstream_errors_are_recorded(client, upstream, status):
    upstream.status = status
    upstream.body = b"" if status == 204 else b"upstream reply"
    upstream.headers = [("Location", "/other")] if status == 302 else []
    configure(client, upstream)
    original = client.execute_request("GET", "/recorded", follow_redirects=False)
    assert original.status_code == status
    assert len(client.get_recordings("/recorded")["data"]) == 1
    replay(client)
    response = client.execute_request("GET", "/recorded", follow_redirects=False)
    assert response.status_code == status and response.content == original.content
    assert response.headers.get("Location") == original.headers.get("Location")
    assert len(upstream.calls) == 1


def test_compressed_body_and_hop_headers_are_normalized(client, upstream):
    upstream.body = gzip.compress(b"decoded body")
    upstream.headers = [("Content-Encoding", "gzip"), ("Connection", "X-Hop"), ("X-Hop", "discard")]
    configure(client, upstream)
    original = client.execute_request("GET", "/recorded")
    assert original.content == b"decoded body"
    replay(client)
    response = client.execute_request("GET", "/recorded")
    assert response.content == b"decoded body"
    for header in ["Content-Encoding", "Connection", "X-Hop", "Transfer-Encoding"]:
        assert header not in response.headers
    assert int(response.headers["Content-Length"]) == len(response.content)


def test_matching_uses_method_raw_path_query_bytes_and_selected_headers(client, upstream):
    path = "/items/{rest:path}"
    configure(client, upstream, path, match_headers=["X-Key", "x-key"])
    route = "/items/a%2Fb?x=1&x=2&space=a+b"
    headers = {"X-Key": "yes", "X-Ignored": "first"}
    assert client.execute_request("POST", route, content=b'{"a":1}', headers=headers).status_code == 200
    assert upstream.calls == [("POST", route, b'{"a":1}')]
    replay(client, path, match_headers=["x-key"])
    assert (
        client.execute_request("POST", route, content=b'{"a":1}', headers={**headers, "X-Ignored": "other"}).status_code
        == 200
    )
    for method, url, body, selected in [
        ("GET", route, b'{"a":1}', "yes"),
        ("POST", route.replace("%2F", "/"), b'{"a":1}', "yes"),
        ("POST", route.replace("x=1&x=2", "x=2&x=1"), b'{"a":1}', "yes"),
        ("POST", route.replace("a+b", "a%20b"), b'{"a":1}', "yes"),
        ("POST", route, b'{"a": 1}', "yes"),
        ("POST", route, b'{"a":1}', "no"),
    ]:
        response = client.execute_request(method, url, content=body, headers={"X-Key": selected})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "recording_not_found"
    assert len(upstream.calls) == 1


def test_repeat_keys_replace_and_bounds_evict_oldest_write(client, upstream):
    configure(client, upstream, max_items=2)
    for route, body in [("/recorded?a=1", b"first"), ("/recorded?a=2", b"second"), ("/recorded?a=1", b"updated")]:
        upstream.body = body
        assert client.execute_request("GET", route).headers["X-Proxy-Mock-Recording"] == "stored"
    entries = client.get_recordings("/recorded")["data"]
    assert [e["request"]["query"] for e in entries] == ["a=2", "a=1"]
    assert base64.b64decode(entries[-1]["response"]["body_b64"]) == b"updated"
    client.execute_request("GET", "/recorded?a=3")
    assert [e["request"]["query"] for e in client.get_recordings("/recorded")["data"]] == ["a=1", "a=3"]
    replay(client, max_items=2)
    assert client.execute_request("GET", "/recorded?a=2").status_code == 404
    assert len(upstream.calls) == 4


def test_byte_budget_skips_oversize_and_applies_to_total_retained_data(client, upstream):
    configure(client, upstream, max_bytes=900)
    upstream.body = b"x" * 2000
    response = client.execute_request("GET", "/recorded")
    assert response.content == upstream.body
    assert response.headers["X-Proxy-Mock-Recording"] == "too_large"
    assert client.get_recordings("/recorded")["data"] == []
    upstream.body = b"ok"
    for i in range(4):
        assert client.execute_request("GET", f"/recorded?n={i}").headers["X-Proxy-Mock-Recording"] == "stored"
    entries = client.get_recordings("/recorded")["data"]
    assert 0 < len(entries) < 4
    assert entries[-1]["request"]["query"] == "n=3"
    response = client.execute_request("POST", "/recorded", content=b"x" * 2000)
    assert response.headers["X-Proxy-Mock-Recording"] == "too_large"
    assert client.get_recordings("/recorded")["data"] == entries


def test_transport_failures_and_policy_rejections_do_not_create_recordings(client, upstream, monkeypatch):
    from proxy_mock.services.proxy_service import ProxyRequestError

    configure(client, upstream)
    for failure, status in [(httpx2.ConnectError("offline"), 502), (httpx2.ReadTimeout("slow"), 504)]:

        async def fail(*args, error=failure):
            raise ProxyRequestError(upstream.host, error)

        monkeypatch.setattr("proxy_mock.utils.proxy_request_to_host", fail)
        assert client.execute_request("GET", "/recorded").status_code == status
        assert client.get_recordings("/recorded")["data"] == []
    monkeypatch.setenv("PROXY_MOCK_ALLOWED_PROXY_HOSTS", "example.invalid")
    assert client.execute_request("GET", "/recorded").status_code == 403
    assert client.get_recordings("/recorded")["data"] == []
    replay(client)
    # Neither the unavailable transport nor the upstream allowlist participates in replay.
    assert client.execute_request("GET", "/recorded").status_code == 404
    assert upstream.calls == []


@pytest.mark.parametrize("change", ["put", "disable", "headers", "upstream", "delete", "clear"])
def test_recordings_follow_mock_lifecycle(client, upstream, change):
    configure(client, upstream)
    client.execute_request("GET", "/recorded")
    client.patch_mock("/recorded", extra_info={"preserved": True})
    assert len(client.get_recordings("/recorded")["data"]) == 1
    if change == "put":
        configure(client, upstream)
    elif change == "disable":
        client.patch_mock("/recorded", recording=None)
    elif change == "headers":
        client.patch_mock("/recorded", recording={"mode": "record", "match_headers": ["X-New"]})
    elif change == "upstream":
        client.patch_mock("/recorded", proxy_host="http://example.invalid")
    elif change == "delete":
        client.delete_mock("/recorded")
    else:
        client.clean_storage()
    result = client.get_recordings("/recorded")
    if change in {"disable", "delete", "clear"}:
        assert result["error"]["code"] == "recordings_not_found"
    else:
        assert result["data"] == []


def test_delete_individual_and_collection_is_resource_oriented(client, upstream):
    configure(client, upstream)
    client.execute_request("GET", "/recorded?a=1")
    client.execute_request("GET", "/recorded?a=2")
    entry = client.get_recordings("/recorded")["data"][0]
    assert client.delete_recordings("/recorded", entry["id"])["success"]
    assert client.get_recordings("/recorded", entry["id"])["error"]["code"] == "recording_not_found"
    assert client.delete_recordings("/recorded", entry["id"])["error"]["code"] == "recording_not_found"
    assert len(client.get_recordings("/recorded")["data"]) == 1
    for method in ["POST", "PUT", "PATCH"]:
        assert client.execute_request(method, "/__admin/recordings?path=/recorded", json={}).status_code == 405
    assert client.delete_recordings("/recorded")["data"] == []
    assert client.delete_recordings("/recorded")["success"]
    assert client.get_storage("/recorded")["data"]["recording"]["mode"] == "record"


@pytest.mark.parametrize("operation", ["replay", "put", "delete", "clear", "delete_entry"])
def test_inflight_recording_cannot_repopulate_replaced_or_deleted_state(client, upstream, operation):
    configure(client, upstream)
    client.execute_request("GET", "/recorded")
    entry = client.get_recordings("/recorded")["data"][0]
    upstream.entered.clear()
    upstream.gate = threading.Event()

    async def scenario():
        async with AsyncProxyMock(client.host) as admin:
            pending = asyncio.create_task(admin.execute_request("GET", "/recorded"))
            try:
                assert await asyncio.to_thread(upstream.entered.wait, 5)
                assert not pending.done()
                if operation == "replay":
                    assert (await admin.patch_mock("/recorded", recording={"mode": "replay"}))["success"]
                elif operation == "put":
                    await admin.configure_mock("/recorded", proxy_host=upstream.host, recording={"mode": "record"})
                elif operation == "delete":
                    await admin.delete_mock("/recorded")
                else:
                    await admin.delete_recordings("/recorded", entry["id"] if operation == "delete_entry" else None)
                upstream.gate.set()
                response = await pending
                assert response.status_code == 200
                assert response.headers["X-Proxy-Mock-Recording"] == "superseded"
                result = await admin.get_recordings("/recorded")
                if operation == "delete":
                    assert result["error"]["code"] == "recordings_not_found"
                elif operation == "replay":
                    assert result["data"] == [entry]
                else:
                    assert result["data"] == []
            finally:
                upstream.gate.set()
                await asyncio.gather(pending, return_exceptions=True)

    asyncio.run(scenario())


def test_concurrent_recordings_are_atomic(client, upstream):
    configure(client, upstream)

    async def scenario():
        async with AsyncProxyMock(client.host) as admin:
            responses = await asyncio.gather(*(admin.execute_request("GET", f"/recorded?i={i}") for i in range(12)))
            assert all(response.status_code == 200 for response in responses)
            assert len((await admin.get_recordings("/recorded"))["data"]) == 12
            assert (await admin.patch_mock("/recorded", recording={"mode": "replay"}))["success"]
            responses = await asyncio.gather(*(admin.execute_request("GET", f"/recorded?i={i}") for i in range(12)))
            assert all(response.content == upstream.body for response in responses)

    asyncio.run(scenario())
    assert len(upstream.calls) == 12


@pytest.mark.parametrize(
    "configuration",
    [
        {"recording": {"mode": "record"}, "proxy_host": None},
        {"recording": {"mode": "automatic"}},
        {"recording": {"mode": "record", "max_items": 0}},
        {"recording": {"mode": "record", "max_bytes": True}},
        {"recording": {"mode": "record", "max_bytes": "100"}},
        {"recording": {"mode": "record", "match_headers": ["invalid header"]}},
        {"recording": {"mode": "record", "unknown": True}},
        {"cache_time": 60},
        {"rules": [{"output_data": {"body": "ambiguous"}}]},
        {"sequence": {"responses": [{"body": "ambiguous"}]}},
    ],
)
def test_invalid_recording_configuration_is_atomic(client, upstream, configuration):
    configure(client, upstream)
    client.execute_request("GET", "/recorded")
    before = client.get_storage("/recorded")
    entries = client.get_recordings("/recorded")
    response = client.execute_request("PATCH", "/__admin/mocks?path=/recorded", json=configuration)
    assert response.status_code == 422
    assert client.get_storage("/recorded") == before
    assert client.get_recordings("/recorded") == entries


@pytest.mark.parametrize(
    "query",
    [
        "",
        "path=",
        "path=/recorded&id=",
        "path=/recorded&id=bad",
        "path=/recorded&all=true",
        "path=/recorded&path=/other",
    ],
)
def test_invalid_recording_selectors_never_delete_collection(client, upstream, query):
    configure(client, upstream)
    client.execute_request("GET", "/recorded")
    assert client.execute_request("DELETE", "/__admin/recordings?" + query).status_code == 422
    assert len(client.get_recordings("/recorded")["data"]) == 1


def test_clients_custom_prefix_openapi_and_snapshot_formats(admin_server, upstream):
    host, prefix = admin_server
    path = "/items/a+b&c=d"
    with ProxyMock(host, admin_prefix=prefix) as client:
        configure(client, upstream, path)
        client.execute_request("GET", path)
        assert len(client.get_recordings(path)["data"]) == 1
        assert client.execute_request("HEAD", prefix + "/recordings?" + urlencode({"path": path})).status_code == 200
        paths = client.execute_request("GET", prefix + "/openapi.json").json()["paths"]
        assert set(paths[prefix + "/recordings"]) == {"get", "delete"}
        assert not any("replay" in p or "recordings/clear" in p for p in paths)
        exported = client.execute_request("GET", prefix + "/snapshot")
        assert exported.status_code == 200
        assert exported.json()["format"] == 2
        assert len(exported.json()["mocks"][0]["recordings"]) == 1
        snapshot = {"format": 1, "mocks": [{"path": path, "recording": {"mode": "replay"}}]}
        assert client.execute_request("PUT", prefix + "/snapshot", json=snapshot).status_code == 422
        assert len(client.get_recordings(path)["data"]) == 1

    async def scenario():
        async with AsyncProxyMock(host, admin_prefix=prefix) as client:
            entry = (await client.get_recordings(path))["data"][0]
            assert (await client.get_recordings(path, entry["id"]))["data"] == entry
            assert (await client.patch_mock(path, recording={"mode": "replay"}))["success"]
            assert (await client.execute_request("GET", path)).content == upstream.body
            assert (await client.delete_recordings(path, entry["id"]))["success"]
            assert (await client.execute_request("GET", path)).status_code == 404
            assert (await client.delete_recordings(path))["success"]
            await client.clean_storage()

    asyncio.run(scenario())
    assert len(upstream.calls) == 1


def test_head_recording_is_distinct_and_keeps_representation_length(client, upstream):
    configure(client, upstream)
    first = client.execute_request("HEAD", "/recorded")
    assert first.status_code == 200 and first.content == b""
    assert int(first.headers["Content-Length"]) == len(upstream.body)
    replay(client)
    response = client.execute_request("HEAD", "/recorded")
    assert response.content == b"" and response.headers["Content-Length"] == first.headers["Content-Length"]
    assert client.execute_request("GET", "/recorded").status_code == 404
    assert len(upstream.calls) == 1


def test_replay_hit_ignores_upstream_policy_and_failed_record_keeps_previous_reply(client, upstream, monkeypatch):
    from proxy_mock.services.proxy_service import ProxyRequestError

    configure(client, upstream)
    client.execute_request("GET", "/recorded")

    async def fail(*args):
        raise ProxyRequestError(upstream.host, httpx2.ReadTimeout("offline"))

    monkeypatch.setattr("proxy_mock.utils.proxy_request_to_host", fail)
    assert client.execute_request("GET", "/recorded").status_code == 504
    assert len(client.get_recordings("/recorded")["data"]) == 1
    replay(client)
    monkeypatch.setenv("PROXY_MOCK_ALLOWED_PROXY_HOSTS", "example.invalid")
    assert client.execute_request("GET", "/recorded").content == upstream.body
    assert len(upstream.calls) == 1


def test_reducing_limits_keeps_newest_entries_and_matching_headers_are_case_insensitive(client, upstream):
    configure(client, upstream, match_headers=["X-Key"], max_items=3)
    for i in range(3):
        client.execute_request("GET", f"/recorded?i={i}", headers={"x-key": "A"})
    replay(client, match_headers=["x-key"], max_items=1)
    assert [e["request"]["query"] for e in client.get_recordings("/recorded")["data"]] == ["i=2"]
    assert client.execute_request("GET", "/recorded?i=2", headers={"X-KEY": "A"}).status_code == 200
    assert client.execute_request("GET", "/recorded?i=2").status_code == 404
    assert client.execute_request("GET", "/recorded?i=2", headers={"X-Key": ""}).status_code == 404
    assert len(upstream.calls) == 3


def test_mock_method_rejection_and_admin_requests_are_not_recorded(client, upstream):
    assert client.configure_mock("/recorded", proxy_host=upstream.host, methods=["GET"], recording={"mode": "record"})[
        "success"
    ]
    assert client.execute_request("POST", "/recorded").status_code == 405
    assert client.execute_request("HEAD", "/__admin/recordings?path=/recorded").status_code == 200
    assert client.get_recordings("/recorded")["data"] == []
    assert upstream.calls == []


def test_header_octets_survive_transport_decoding(client, upstream):
    # The upstream sends UTF-8 octets; HTTP header values must survive unchanged.
    raw_value = "café".encode("utf-8").decode("latin-1")
    upstream.headers = [("X-Raw", raw_value)]
    configure(client, upstream)
    first = client.execute_request("GET", "/recorded")
    assert first.status_code == 200
    assert (b"x-raw", raw_value.encode("latin-1")) in first.headers.raw
    replay(client)
    response = client.execute_request("GET", "/recorded")
    assert (b"x-raw", raw_value.encode("latin-1")) in response.headers.raw
    assert len(upstream.calls) == 1
