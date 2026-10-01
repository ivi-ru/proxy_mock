"""Runnable 3.0 REST, sequence, offline replay and asynchronous client examples."""

import asyncio
import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx2

from proxy_mock.client import AsyncProxyMock


def test_rest_mock_lifecycle(proxy_mock, proxy_mock_url):
    resource = proxy_mock.admin_prefix + "/mocks"
    selector = {"path": "/inventory/sku-42"}
    with httpx2.Client(base_url=proxy_mock_url, timeout=5) as http:
        created = http.put(resource, params=selector, json={"mock_data": {"body": {"available": 3}}})
        assert created.status_code == 201
        assert http.get(created.headers["Location"]).json()["data"]["mock_data"]["body"] == {"available": 3}

        updated = http.patch(resource, params=selector, json={"mock_data": {"status_code": 503}})
        assert updated.status_code == 200
        response = http.get("/inventory/sku-42")
        assert response.status_code == 503 and response.json() == {"available": 3}

        assert http.delete(resource, params=selector).status_code == 200
        missing = http.get(resource, params=selector)
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "mock_not_found"


def test_sequence_restart_and_snapshot(proxy_mock):
    proxy_mock.configure_mock(
        "/inventory",
        sequence={
            "responses": [{"status_code": 503, "body": b"retry"}, {"body": {"available": 3}}],
            "on_exhaustion": "error",
        },
    )
    assert proxy_mock.execute_request("GET", "/inventory").status_code == 503
    assert proxy_mock.execute_request("GET", "/inventory").json() == {"available": 3}
    assert proxy_mock.execute_request("GET", "/inventory").status_code == 409
    assert proxy_mock.get_sequence_state("/inventory")["data"]["position"] == 2

    proxy_mock.reset_sequence("/inventory")
    assert proxy_mock.execute_request("GET", "/inventory").content == b"retry"
    snapshot = json.loads(json.dumps(proxy_mock.export_mocks()))
    assert snapshot["format"] == 2
    proxy_mock.clean_storage()
    proxy_mock.import_mocks(snapshot, mode="replace")
    assert proxy_mock.get_sequence_state("/inventory")["data"]["position"] == 0
    assert proxy_mock.execute_request("GET", "/inventory").content == b"retry"


@contextmanager
def local_upstream():
    """A disposable upstream on the same host as the fixture's proxy-mock instance."""
    calls = []

    class Upstream(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            calls.append((self.path, body))
            self.send_response(201)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Set-Cookie", "a=1")
            self.send_header("Set-Cookie", "b=2")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"\xff\x00")

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_recording_snapshot_replays_after_upstream_shutdown(proxy_mock, tmp_path):
    route = "/recorded?x=1&x=2"
    options = {"content": b'{"sku":42}', "headers": {"Accept": "application/octet-stream"}}
    with local_upstream() as (upstream_url, calls):
        proxy_mock.configure_mock(
            "/recorded", proxy_host=upstream_url, recording={"mode": "record", "match_headers": ["Accept"]}
        )
        original = proxy_mock.execute_request("POST", route, **options)
        assert original.status_code == 201 and original.content == b"\xff\x00"
        assert original.headers["X-Proxy-Mock-Recording"] == "stored"
        assert calls == [(route, options["content"])]
        entries = proxy_mock.get_recordings("/recorded")["data"]
        assert len(entries) == 1

        # Retain the matching headers when replacing the recording object in a PATCH.
        proxy_mock.patch_mock("/recorded", recording={"mode": "replay", "match_headers": ["Accept"]})
        snapshot_file = tmp_path / "recordings.json"
        snapshot_file.write_text(json.dumps(proxy_mock.export_mocks()), encoding="utf-8")

    # The upstream has stopped; restoration and replay must work without it.
    proxy_mock.clean_storage()
    proxy_mock.import_mocks(json.loads(snapshot_file.read_text(encoding="utf-8")), mode="replace")
    replayed = proxy_mock.execute_request("POST", route, **options)
    assert replayed.status_code == original.status_code and replayed.content == original.content
    assert replayed.headers.get_list("Set-Cookie") == ["a=1", "b=2"]
    assert calls == [(route, options["content"])]

    missing = proxy_mock.execute_request("POST", route, content=b"different", headers=options["headers"])
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "recording_not_found"
    proxy_mock.delete_recordings("/recorded", entries[0]["id"])
    assert proxy_mock.execute_request("POST", route, **options).status_code == 404


def test_async_client_uses_the_same_administrative_prefix(proxy_mock, proxy_mock_url):
    async def scenario():
        async with AsyncProxyMock(proxy_mock_url, admin_prefix=proxy_mock.admin_prefix) as client:
            assert (await client.configure_mock("/async-inventory", body={"available": 3}))["success"]
            response = await client.execute_request("GET", "/async-inventory")
            assert isinstance(response, httpx2.Response) and response.json() == {"available": 3}
            assert (await client.get_traffic(path="/async-inventory", method="GET"))["count"] == 1
            assert (await client.delete_mock("/async-inventory"))["success"]

    asyncio.run(scenario())
