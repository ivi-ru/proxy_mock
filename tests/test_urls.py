import asyncio
from urllib.parse import urlsplit

import httpx2
import pytest
from pydantic import ValidationError

from proxy_mock.client import AsyncProxyMock
from proxy_mock.domain.models import ConfigureMockRequestSchema, RulesInputDataSchema
from proxy_mock.services.proxy_service import (
    is_proxy_host_allowed,
    make_proxy_request_url,
    proxy_request_to_host,
)
from tests import HOST


@pytest.mark.parametrize("host", ["https://example.com:8443/base", "http://[::1]:8080", "//example.com"])
def test_proxy_host_validation_keeps_absolute_hosts(host):
    assert ConfigureMockRequestSchema(path="/test", proxy_host=host).proxy_host == host
    assert RulesInputDataSchema(proxy_host=host).proxy_host == host


@pytest.mark.parametrize("host", ["example.com", "/relative", "http://", "http://host:bad", "http://[::1"])
def test_proxy_host_validation_rejects_malformed_hosts(host):
    with pytest.raises(ValidationError):
        ConfigureMockRequestSchema(path="/test", proxy_host=host)
    with pytest.raises(ValidationError):
        RulesInputDataSchema(proxy_host=host)


def test_proxy_url_keeps_encoded_delimiters_and_repeated_query_keys():
    url = make_proxy_request_url(
        "http://mock/a%2Fb/%23/%25?q=a%2Bb&q=a+b&empty=",
        "http://user:pass@[::1]:8080/base?discard=1#fragment",
    )
    assert url == "http://user:pass@[::1]:8080/a%2Fb/%23/%25?q=a%2Bb&q=a+b&empty="


def test_proxy_url_does_not_treat_the_request_path_as_a_host():
    url = make_proxy_request_url("http://mock//other.example/path", "https://upstream.example/base")
    assert urlsplit(url).hostname == "upstream.example"
    assert urlsplit(url).path == "//other.example/path"


def test_allowlist_handles_case_ipv6_and_idna(monkeypatch):
    monkeypatch.setenv("PROXY_MOCK_ALLOWED_PROXY_HOSTS", "EXAMPLE.COM,::1,bücher.example,faß.de")
    assert is_proxy_host_allowed("https://Example.Com:8443/base")
    assert is_proxy_host_allowed("http://[::1]:8080/")
    assert is_proxy_host_allowed("https://xn--bcher-kva.example/")
    assert is_proxy_host_allowed("https://xn--fa-hia.de/")
    assert is_proxy_host_allowed("https://faß.de/")
    assert not is_proxy_host_allowed("https://example.com.attacker.test/")


def test_encoded_proxy_url_reaches_the_transport_unchanged():
    from starlette.requests import Request

    async def scenario():
        captured = []

        def upstream(request):
            captured.append(request.url.raw_path)
            return httpx2.Response(200, json={"ok": True})

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "scheme": "http",
                "server": ("mock", 80),
                "path": "/items/sku",
                "raw_path": b"/items%2Fsku",
                "query_string": b"q=a%2Bb&q=a+b",
                "headers": [],
            },
            receive,
        )
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(upstream)) as http_client:
            response = await proxy_request_to_host(request, "http://upstream.example/base", http_client)
        assert response.json() == {"ok": True}
        assert captured == [b"/items%2Fsku?q=a%2Bb&q=a+b"]

    asyncio.run(scenario())


@pytest.mark.parametrize("path", ["/items/a+b&c=d#tag", "/items/ümlaut", "/items/100%"])
def test_sync_client_encodes_path_filters(client, path):
    assert client.configure_mock(path=path, body="found")["success"]
    assert client.get_storage(path=path)["data"]["mock_data"]["body"] == "found"
    assert client.delete_mock(path)["success"]
    assert not client.get_storage(path=path)["data"]


@pytest.mark.parametrize("path", ["/items/a+b&c=d#tag", "/items/ümlaut", "/items/100%"])
def test_async_client_encodes_path_filters(path):
    async def scenario():
        async with AsyncProxyMock(HOST) as client:
            assert (await client.configure_mock(path=path, body="found"))["success"]
            assert (await client.get_storage(path=path))["data"]["mock_data"]["body"] == "found"
            assert (await client.delete_mock(path))["success"]
            assert not (await client.get_storage(path=path))["data"]

    asyncio.run(scenario())
