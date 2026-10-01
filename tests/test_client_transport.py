"""Exercise the shared public transport contract through both clients."""

import asyncio
from contextlib import contextmanager
from http import HTTPMethod

import httpx2
import pytest

from proxy_mock.client import (
    AsyncProxyMock,
    AsyncProxyMockRequestError,
    AsyncProxyMockResponseError,
    ProxyMock,
    ProxyMockRequestError,
    ProxyMockResponseError,
)
from tests import HOST


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def transport_client(request):
    asynchronous = request.param

    @contextmanager
    def build(handler, host="http://mock.test/base", **options):
        native_type = httpx2.AsyncClient if asynchronous else httpx2.Client
        native = native_type(transport=httpx2.MockTransport(handler), **options.pop("native_options", {}))
        wrapper_type = AsyncProxyMock if asynchronous else ProxyMock
        wrapper = wrapper_type(host, http_client=native, **options)

        def execute(route="/item/", method=HTTPMethod.GET, parsed=False, **kwargs):
            call = wrapper.execute_request_and_get_response_body if parsed else wrapper.execute_request
            result = call(method, route, **kwargs)
            return asyncio.run(result) if asynchronous else result

        try:
            yield wrapper, native, execute
        finally:
            if asynchronous:
                asyncio.run(wrapper.aclose())
                assert not native.is_closed
                asyncio.run(native.aclose())
            else:
                wrapper.close()
                assert not native.is_closed
                native.close()

    build.request_error = AsyncProxyMockRequestError if asynchronous else ProxyMockRequestError
    build.response_error = AsyncProxyMockResponseError if asynchronous else ProxyMockResponseError
    return build


@pytest.mark.parametrize(
    ("content_type", "body", "expected"),
    [
        ("Application/JSON", b'{"a":1}', {"a": 1}),
        ("application/json", b"[1,true]", [1, True]),
        ("application/json", b"42", 42),
        ("application/json", b"false", False),
        ("application/json", b"null", None),
        ("application/json", b'"text"', "text"),
        ("application/json", b"invalid", "invalid"),
        ("text/plain", "caf\u00e9".encode(), "caf\u00e9"),
        ("application/octet-stream", b"\xff\x00", b"\xff\x00"),
        ("application/json", b"", None),
    ],
)
def test_response_body_contract(transport_client, content_type, body, expected):
    def handle(request):
        return httpx2.Response(200, headers={"Content-Type": content_type}, content=body)

    with transport_client(handle) as (_, _, execute):
        assert execute(parsed=True) == expected


@pytest.mark.parametrize("status", [200, 302, 400, 503])
def test_http_error_contract(transport_client, status):
    with transport_client(lambda request: httpx2.Response(status, text="reply")) as (_, _, execute):
        response = execute()
        assert isinstance(response, httpx2.Response)
        assert response.is_closed and response.content == b"reply"
        assert bool(response) is True
        assert response.is_success is (status == 200)
        if status >= 400:
            with pytest.raises(transport_client.response_error) as caught:
                execute(raise_for_status=True)
            assert caught.value.response.status_code == status
            assert caught.value.response.text == "reply"
            assert isinstance(caught.value, ProxyMockResponseError)
        else:
            assert execute(raise_for_status=True).status_code == status
        if status != 200:
            with pytest.raises(httpx2.HTTPStatusError):
                response.raise_for_status()


@pytest.mark.parametrize(
    "error_type",
    [
        httpx2.ConnectError,
        httpx2.ReadError,
        httpx2.ConnectTimeout,
        httpx2.ReadTimeout,
        httpx2.WriteTimeout,
        httpx2.PoolTimeout,
        httpx2.RemoteProtocolError,
        httpx2.DecodingError,
        httpx2.UnsupportedProtocol,
    ],
)
def test_request_errors_preserve_native_cause(transport_client, error_type):
    original = None

    def handle(request):
        nonlocal original
        original = error_type("transport failed", request=request)
        raise original

    with transport_client(handle) as (_, _, execute):
        with pytest.raises(transport_client.request_error) as caught:
            execute()
        assert caught.value.__cause__ is original
        assert original.request.url == "http://mock.test/base/item/"
        assert isinstance(caught.value, ProxyMockRequestError)


def test_url_headers_cookies_auth_and_repeated_headers(transport_client):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx2.Response(200, headers=[("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")])

    with transport_client(
        handle,
        native_options={
            "base_url": "http://unrelated.test/wrong",
            "headers": {"X-Default": "yes"},
            "cookies": {"session": "ok"},
            "auth": ("user", "password"),
        },
    ) as (_, _, execute):
        response = execute("/encoded%2Fpath/?a=1&a=2&q=a+b")
        assert seen[0].url == "http://mock.test/base/encoded%2Fpath/?a=1&a=2&q=a+b"
        assert seen[0].headers["X-Default"] == "yes"
        assert "session=ok" in seen[0].headers["Cookie"]
        assert seen[0].headers["Authorization"] == "Basic dXNlcjpwYXNzd29yZA=="
        assert response.headers.get_list("Set-Cookie") == ["a=1", "b=2"]
        assert execute("http://other.test/direct").request.url == "http://other.test/direct"


@pytest.mark.parametrize("timeout", [10.0, None, httpx2.Timeout(3.0, connect=1.0)])
def test_constructor_and_per_request_timeouts(transport_client, timeout):
    seen = []

    def handle(request):
        seen.append(request.extensions["timeout"])
        return httpx2.Response(200)

    with transport_client(handle, timeout=timeout, native_options={"timeout": 99.0}) as (_, _, execute):
        execute()
        assert seen[-1] == httpx2.Timeout(timeout).as_dict()
        execute(timeout=0.25)
        assert set(seen[-1].values()) == {0.25}
        execute(timeout=None)
        assert set(seen[-1].values()) == {None}


@pytest.mark.parametrize("native_follow", [False, True])
def test_redirect_defaults_and_override(transport_client, native_follow):
    def handle(request):
        if request.url.path.endswith("/item/"):
            return httpx2.Response(302, headers={"Location": "/destination"})
        return httpx2.Response(200, text="destination")

    with transport_client(handle, native_options={"follow_redirects": native_follow}) as (_, _, execute):
        assert execute().status_code == (200 if native_follow else 302)
        response = execute(follow_redirects=True)
        assert response.text == "destination" and len(response.history) == 1
        assert execute(follow_redirects=False).status_code == 302


def test_redirect_loop_is_a_request_error(transport_client):
    with transport_client(
        lambda request: httpx2.Response(302, headers={"Location": str(request.url)}),
        native_options={"max_redirects": 2},
    ) as (_, _, execute):
        with pytest.raises(transport_client.request_error) as caught:
            execute(follow_redirects=True)
        assert isinstance(caught.value.__cause__, httpx2.TooManyRedirects)


@pytest.mark.parametrize(
    ("options", "body", "content_type"),
    [
        ({"content": b"\xff\x00"}, b"\xff\x00", None),
        ({"content": "caf\u00e9"}, "caf\u00e9".encode(), None),
        ({"json": {"a": 1}}, b'{"a":1}', "application/json"),
        ({"data": {"a": "a b"}}, b"a=a+b", "application/x-www-form-urlencoded"),
    ],
)
def test_request_body_encoding(transport_client, options, body, content_type):
    def handle(request):
        assert request.content == body
        if content_type:
            assert request.headers["Content-Type"] == content_type
        return httpx2.Response(200)

    with transport_client(handle) as (_, _, execute):
        execute(method=HTTPMethod.POST, **options)


def test_multipart_upload(transport_client):
    def handle(request):
        assert request.headers["Content-Type"].startswith("multipart/form-data; boundary=")
        assert b'filename="sample.bin"' in request.content
        assert b"\xff\x00" in request.content
        return httpx2.Response(200)

    with transport_client(handle) as (_, _, execute):
        execute(method=HTTPMethod.POST, files={"file": ("sample.bin", b"\xff\x00")})


@pytest.mark.parametrize("options", [{"allow_redirects": True}, {"stream": True}, {"data": b"raw"}])
def test_removed_request_arguments_fail_locally(transport_client, options):
    def unexpected(request):
        pytest.fail("invalid arguments must not reach the transport")

    with transport_client(unexpected) as (_, _, execute):
        with pytest.raises(TypeError):
            execute(**options)


def test_invalid_url_keeps_native_exception(transport_client):
    with transport_client(lambda request: httpx2.Response(200)) as (_, _, execute):
        with pytest.raises(httpx2.InvalidURL):
            execute("http://bad.test:invalid/")


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
def test_owned_client_closes_on_context_exception(asynchronous):
    if asynchronous:

        async def scenario():
            client = AsyncProxyMock(HOST)
            with pytest.raises(RuntimeError):
                async with client:
                    raise RuntimeError("caller failed")
            assert client.http_client.is_closed

        asyncio.run(scenario())
    else:
        client = ProxyMock(HOST)
        with pytest.raises(RuntimeError):
            with client:
                raise RuntimeError("caller failed")
        assert client.http_client.is_closed


def test_wrong_native_client_type_is_rejected():
    with httpx2.Client() as native:
        with pytest.raises(TypeError, match="AsyncClient"):
            AsyncProxyMock(HOST, http_client=native)

    async def scenario():
        async with httpx2.AsyncClient() as native:
            with pytest.raises(TypeError, match="httpx2.Client"):
                ProxyMock(HOST, http_client=native)

    asyncio.run(scenario())


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
def test_real_read_timeout_and_override(client, asynchronous):
    client.configure_mock(path="/transport/delayed", body="ready", timeout=0.12)
    if asynchronous:

        async def scenario():
            async with AsyncProxyMock(HOST, timeout=0.02) as c:
                with pytest.raises(AsyncProxyMockRequestError) as caught:
                    await c.execute_request("GET", "/transport/delayed")
                assert isinstance(caught.value.__cause__, httpx2.ReadTimeout)
                assert (await c.execute_request("GET", "/transport/delayed", timeout=None)).text == "ready"

        asyncio.run(scenario())
    else:
        with ProxyMock(HOST, timeout=0.02) as c:
            with pytest.raises(ProxyMockRequestError) as caught:
                c.execute_request("GET", "/transport/delayed")
            assert isinstance(caught.value.__cause__, httpx2.ReadTimeout)
            assert c.execute_request("GET", "/transport/delayed", timeout=None).text == "ready"


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
def test_owned_client_redirect_defaults(client, asynchronous):
    client.configure_mock(path="/transport/redirect", status_code=302, headers={"Location": "/transport/target"})
    client.configure_mock(path="/transport/target", body="target")
    if asynchronous:

        async def scenario():
            async with AsyncProxyMock(HOST) as c:
                assert (await c.execute_request("GET", "/transport/redirect")).status_code == 302
                response = await c.execute_request("GET", "/transport/redirect", follow_redirects=True)
                assert response.text == "target" and len(response.history) == 1

        asyncio.run(scenario())
    else:
        with ProxyMock(HOST) as c:
            assert c.execute_request("GET", "/transport/redirect").status_code == 302
            response = c.execute_request("GET", "/transport/redirect", follow_redirects=True)
            assert response.text == "target" and len(response.history) == 1
