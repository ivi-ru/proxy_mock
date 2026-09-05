import warnings
from http import HTTPMethod
from typing import Any

import httpx2
import msgpack
from yarl import URL

from proxy_mock.client.service_endpoints import Endpoints

CONFIGURE_CONTENT_TYPE = "application/octet-stream"


def _build_traffic_settings_payload(record_unknown_traffic: bool | None, max_items: int | None) -> dict:
    """The endpoint accepts a partial update, so fields that were not supplied are left out."""
    payload = {}
    if record_unknown_traffic is not None:
        payload["record_unknown_traffic"] = record_unknown_traffic
    if max_items is not None:
        payload["max_items"] = max_items
    return payload


class AsyncProxyMockRequestError(Exception):
    """Error while performing an async request to the proxy-mock server."""


class AsyncProxyMockResponseError(Exception):
    """HTTP error returned by the proxy-mock server."""


class AsyncProxyMock:
    def __init__(self, host: str, timeout: float = 10.0) -> None:
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._client = httpx2.AsyncClient(base_url=self.host, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()

    @staticmethod
    def _parse_response_body(response: httpx2.Response) -> dict | str | list | bytes | None:
        if not response.content:
            return None

        content_type = response.headers.get("Content-Type", "")
        if "json" in content_type:
            try:
                return response.json()
            except Exception:
                return response.text
        if "text" in content_type:
            return response.text
        return response.content

    async def execute_request(
        self,
        method: str | HTTPMethod,
        route: str,
        raise_for_status: bool = False,
        **kwargs,
    ) -> httpx2.Response:
        try:
            response = await self._client.request(method=str(method), url=route, **kwargs)
        except (httpx2.ConnectError, httpx2.TimeoutException) as err:
            raise AsyncProxyMockRequestError(f"Proxy-mock request error:\n{err}") from err

        if raise_for_status and response.status_code >= 400:
            raise AsyncProxyMockResponseError(f"Proxy-mock returned HTTP {response.status_code}: {response.text}")
        return response

    async def execute_request_and_get_response_body(
        self,
        method: str | HTTPMethod,
        route: str,
        json: dict | None = None,
        **kwargs,
    ) -> dict | str | list | bytes | None:
        response = await self.execute_request(method=method, route=route, json=json, **kwargs)
        return self._parse_response_body(response)

    def _build_mock_request_data(
        self,
        path: str,
        body: Any = None,
        headers: dict | None = None,
        status_code: int | None = None,
        extra_info: dict | None = None,
        proxy_host: str | None = None,
        timeout: float | None = None,
        rules: list[dict] | None = None,
        methods: list[str] | None = None,
        cache_time: int | None = None,
        include_body_if_none: bool = True,
        **kwargs,
    ) -> dict:
        mock_data = {}
        if include_body_if_none or body is not None:
            mock_data["body"] = body
        if status_code is not None:
            mock_data["status_code"] = status_code
        if headers is not None:
            mock_data["headers"] = headers

        request_data = {"path": path}
        if methods is not None:
            request_data["methods"] = methods
        if mock_data:
            request_data["mock_data"] = mock_data
        if extra_info is not None:
            request_data["extra_info"] = extra_info
        if proxy_host is not None:
            request_data["proxy_host"] = proxy_host
        if timeout is not None:
            request_data["timeout"] = timeout
        if rules is not None:
            request_data["rules"] = rules
        if cache_time is not None:
            request_data["cache_time"] = cache_time

        request_data.update(kwargs)
        return request_data

    async def _send_configure(self, method: HTTPMethod, payload: dict):
        return await self.execute_request_and_get_response_body(
            method=method,
            route=Endpoints.CONFIGURE_MOCK,
            content=msgpack.packb(payload),
            headers={"Content-Type": CONFIGURE_CONTENT_TYPE},
        )

    async def get_proxy_mock(self):
        return await self.execute_request_and_get_response_body(HTTPMethod.GET, Endpoints.PROXY_MOCK)

    async def configure_mock(
        self,
        path: str,
        body: Any = None,
        headers: dict | None = None,
        status_code: int | None = None,
        extra_info: dict | None = None,
        proxy_host: str | None = None,
        timeout: float | None = None,
        rules: list[dict] | None = None,
        methods: list[str] | None = None,
        cache_time: int | None = None,
        **kwargs,
    ):
        payload = self._build_mock_request_data(
            path=path,
            body=body,
            headers=headers,
            status_code=status_code,
            extra_info=extra_info,
            proxy_host=proxy_host,
            timeout=timeout,
            rules=rules,
            methods=methods,
            cache_time=cache_time,
            include_body_if_none=True,
            **kwargs,
        )
        return await self._send_configure(HTTPMethod.POST, payload)

    async def patch_mock(
        self,
        path: str,
        body: Any = None,
        headers: dict | None = None,
        status_code: int | None = None,
        extra_info: dict | None = None,
        proxy_host: str | None = None,
        timeout: float | None = None,
        rules: list[dict] | None = None,
        methods: list[str] | None = None,
        cache_time: int | None = None,
        **kwargs,
    ):
        payload = self._build_mock_request_data(
            path=path,
            body=body,
            headers=headers,
            status_code=status_code,
            extra_info=extra_info,
            proxy_host=proxy_host,
            timeout=timeout,
            rules=rules,
            methods=methods,
            cache_time=cache_time,
            include_body_if_none=False,
            **kwargs,
        )
        return await self._send_configure(HTTPMethod.PATCH, payload)

    async def get_traffic(self, path: str | None = None, method: str | None = None, limit: int | None = None):
        query_params = {
            **({"path": path} if path else {}),
            **({"method": method} if method else {}),
            **({"limit": limit} if limit is not None else {}),
        }
        full_path = URL().with_path(Endpoints.TRAFFIC).with_query(query_params).human_repr()
        return await self.execute_request_and_get_response_body(HTTPMethod.GET, full_path)

    async def get_storage(self, path: str | None = None):
        query_params = {**({"path": path} if path else {})}
        full_path = URL().with_path(Endpoints.STORAGE).with_query(query_params).human_repr()
        return await self.execute_request_and_get_response_body(HTTPMethod.GET, full_path)

    async def clean_storage(self, path: str | None = None):
        """Delete mocks: all of them, or the one at `path`.

        Passing a path is deprecated — use `delete_mock()`, which reports a missing mock with a
        `404` instead of `success: false`.
        """
        if path:
            warnings.warn(
                "clean_storage(path=...) is deprecated and will be removed in 3.0; use delete_mock(path)",
                DeprecationWarning,
                stacklevel=2,
            )
            full_path = URL().with_path(Endpoints.STORAGE_CLEAN).with_query({"path": path}).human_repr()
            return await self.execute_request_and_get_response_body(HTTPMethod.POST, full_path)

        return await self.execute_request_and_get_response_body(HTTPMethod.DELETE, Endpoints.STORAGE)

    async def export_mocks(self):
        """Export every configured mock as a snapshot document."""
        return await self.execute_request_and_get_response_body(HTTPMethod.GET, Endpoints.STORAGE_SNAPSHOT)

    async def import_mocks(self, snapshot: dict, mode: str = "merge"):
        """Load a snapshot: `merge` keeps the configured mocks, `replace` clears them first."""
        full_path = URL().with_path(Endpoints.STORAGE_SNAPSHOT).with_query({"mode": mode}).human_repr()
        return await self.execute_request_and_get_response_body(HTTPMethod.POST, full_path, json=snapshot)

    async def delete_mock(self, path: str):
        full_path = URL().with_path(Endpoints.STORAGE).with_query({"path": path}).human_repr()
        return await self.execute_request_and_get_response_body(HTTPMethod.DELETE, full_path)

    async def clean_traffic(self):
        return await self.execute_request_and_get_response_body(HTTPMethod.DELETE, Endpoints.TRAFFIC)

    async def get_traffic_settings(self):
        return await self.execute_request_and_get_response_body(HTTPMethod.GET, Endpoints.TRAFFIC_SETTINGS)

    async def set_traffic_settings(self, record_unknown_traffic: bool | None = None, max_items: int | None = None):
        return await self.execute_request_and_get_response_body(
            HTTPMethod.PATCH,
            Endpoints.TRAFFIC_SETTINGS,
            json=_build_traffic_settings_payload(record_unknown_traffic, max_items),
        )

    async def clean_cache(self):
        """Deprecated: response caching and this endpoint are removed in 3.0."""
        warnings.warn(
            "clean_cache() is deprecated and will be removed in 3.0 together with response caching",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.execute_request_and_get_response_body(HTTPMethod.POST, Endpoints.CACHE_CLEAN)
