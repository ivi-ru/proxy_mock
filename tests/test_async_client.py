import asyncio
from http import HTTPMethod

import httpx2
import pytest

from proxy_mock.client import AsyncProxyMock
from proxy_mock.client.async_client import AsyncProxyMockRequestError, AsyncProxyMockResponseError
from proxy_mock.repositories.traffic_store import DEFAULT_TRAFFIC_MAX
from tests import HOST


def run(coro):
    return asyncio.run(coro)


class TestAsyncParseBody:
    def test_empty_body_is_none(self):
        response = httpx2.Response(200, content=b"")
        assert AsyncProxyMock._parse_response_body(response) is None

    def test_json_body(self):
        response = httpx2.Response(200, headers={"Content-Type": "application/json"}, content=b'{"a": 1}')
        assert AsyncProxyMock._parse_response_body(response) == {"a": 1}

    def test_broken_json_falls_back_to_text(self):
        response = httpx2.Response(200, headers={"Content-Type": "application/json"}, content=b"not json")
        assert AsyncProxyMock._parse_response_body(response) == "not json"

    def test_text_body(self):
        response = httpx2.Response(200, headers={"Content-Type": "text/plain"}, content=b"hello")
        assert AsyncProxyMock._parse_response_body(response) == "hello"

    def test_bytes_body(self):
        response = httpx2.Response(200, headers={"Content-Type": "application/octet-stream"}, content=b"\x00\x01")
        assert AsyncProxyMock._parse_response_body(response) == b"\x00\x01"


class TestAsyncClient:
    def test_proxy_mock_handle(self):
        async def scenario():
            async with AsyncProxyMock(HOST) as c:
                return await c.get_proxy_mock()

        assert run(scenario())["success"]

    def test_configure_and_request(self):
        async def scenario():
            async with AsyncProxyMock(HOST) as c:
                await c.clean_storage()
                await c.clean_traffic()
                configure_response = await c.configure_mock(path="/async-test", body={"ok": True}, status_code=201)
                body = await c.execute_request_and_get_response_body(HTTPMethod.GET, "/async-test")
                return configure_response, body

        configure_response, body = run(scenario())
        assert configure_response["success"]
        assert body == {"ok": True}

    def test_configure_all_fields(self):
        async def scenario():
            async with AsyncProxyMock(HOST) as c:
                return await c.configure_mock(
                    path="/async-full",
                    body={"a": 1},
                    headers={"X-H": "1"},
                    status_code=200,
                    extra_info={"svc": "x"},
                    proxy_host="http://example.com",
                    timeout=0.1,
                    rules=[{"input_data": {"body": {"k": 1}}, "output_data": {"body": "r"}}],
                    methods=["GET", "POST"],
                    cache_time=5,
                    custom_kwarg="y",
                )

        assert run(scenario())["success"]

    def test_patch_mock(self):
        async def scenario():
            async with AsyncProxyMock(HOST) as c:
                await c.configure_mock(path="/async-patch", body={"v": 1}, status_code=200)
                await c.patch_mock(path="/async-patch", status_code=418)
                response = await c.execute_request(HTTPMethod.GET, "/async-patch")
                return response.status_code

        assert run(scenario()) == 418

    def test_traffic_and_storage(self):
        async def scenario():
            async with AsyncProxyMock(HOST) as c:
                await c.clean_storage()
                await c.clean_traffic()
                await c.configure_mock(path="/async-traf", body="x")
                await c.execute_request(HTTPMethod.GET, "/async-traf")
                traffic = await c.get_traffic(path="/async-traf", method="GET", limit=10)
                storage = await c.get_storage(path="/async-traf")
                return traffic, storage

        traffic, storage = run(scenario())
        assert traffic["success"] and traffic["data"]
        assert storage["success"]

    def test_clean_cache(self):
        async def scenario():
            async with AsyncProxyMock(HOST) as c:
                return await c.clean_cache()

        assert run(scenario())["success"]

    def test_traffic_settings(self):
        async def scenario():
            async with AsyncProxyMock(HOST) as c:
                original = (await c.get_traffic_settings())["data"]
                disabled = await c.set_traffic_settings(record_unknown_traffic=False)
                current = await c.get_traffic_settings()
                resized = await c.set_traffic_settings(max_items=42)
                restored = await c.set_traffic_settings(**original)
                return disabled, current, resized, restored

        disabled, current, resized, restored = run(scenario())
        assert disabled["data"]["record_unknown_traffic"] is False
        assert current["data"]["record_unknown_traffic"] is False
        assert resized["data"] == {"record_unknown_traffic": False, "max_items": 42}
        assert restored["data"] == {"record_unknown_traffic": True, "max_items": DEFAULT_TRAFFIC_MAX}

    def test_delete_mock(self):
        async def scenario():
            async with AsyncProxyMock(HOST) as c:
                await c.configure_mock(path="/async-del", body={"v": 1})
                delete_response = await c.delete_mock("/async-del")
                storage = await c.get_storage("/async-del")
                return delete_response, storage

        delete_response, storage = run(scenario())
        assert delete_response["success"]
        assert not storage["data"]


class TestAsyncErrors:
    def test_connection_error(self):
        async def scenario():
            c = AsyncProxyMock("http://localhost:59999", timeout=1.0)
            try:
                return await c.get_proxy_mock()
            finally:
                await c.aclose()

        with pytest.raises(AsyncProxyMockRequestError):
            run(scenario())

    def test_raise_for_status(self):
        async def scenario():
            async with AsyncProxyMock(HOST) as c:
                await c.execute_request(HTTPMethod.GET, "/no-such-async-mock", raise_for_status=True)

        with pytest.raises(AsyncProxyMockResponseError):
            run(scenario())
