from http import HTTPMethod
from typing import Any
from urllib.parse import urlencode

import httpx2
import msgpack

from proxy_mock.client.migration import (
    normalize_mock_path,
    sequence_query,
    service_endpoint,
    validate_admin_prefix,
)
from proxy_mock.client.service_endpoints import Endpoints
from proxy_mock.client.transport import (
    ProxyMockRequestError,
    ProxyMockResponseError,
    ResponseBody,
    parse_response_body,
    request_options,
    request_url,
)

CONFIGURE_CONTENT_TYPE = "application/octet-stream"
_UNSET = object()


def _build_traffic_settings_payload(record_unknown_traffic: bool | None, max_items: int | None) -> dict:
    """The endpoint accepts a partial update, so fields that were not supplied are left out."""
    payload = {}
    if record_unknown_traffic is not None:
        payload["record_unknown_traffic"] = record_unknown_traffic
    if max_items is not None:
        payload["max_items"] = max_items
    return payload


class AsyncProxyMockRequestError(ProxyMockRequestError):
    """Error while performing an async request to the proxy-mock server."""


class AsyncProxyMockResponseError(ProxyMockResponseError):
    """HTTP error returned by the proxy-mock server."""


class AsyncProxyMock:
    def __init__(
        self,
        host: str,
        timeout: float | httpx2.Timeout | None = 10.0,
        *,
        admin_prefix: str | None = None,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self.admin_prefix = validate_admin_prefix(admin_prefix)
        if http_client is not None and not isinstance(http_client, httpx2.AsyncClient):
            raise TypeError("http_client must be an httpx2.AsyncClient")
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._owns_http_client = http_client is None
        self.http_client = (
            http_client if http_client is not None else httpx2.AsyncClient(base_url=self.host, timeout=timeout)
        )

    def _service_endpoint(self, endpoint: str) -> str:
        return service_endpoint(endpoint, self.admin_prefix)

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self.http_client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()

    _parse_response_body = staticmethod(parse_response_body)

    async def execute_request(
        self,
        method: str | HTTPMethod,
        route: str,
        raise_for_status: bool = False,
        **kwargs,
    ) -> httpx2.Response:
        try:
            response = await self.http_client.request(
                method=str(method), url=request_url(self.host, route), **request_options(kwargs, self.timeout)
            )
        except httpx2.RequestError as err:
            raise AsyncProxyMockRequestError(f"Proxy-mock request error:\n{err}") from err

        if raise_for_status and response.status_code >= 400:
            raise AsyncProxyMockResponseError(response)
        return response

    async def execute_request_and_get_response_body(
        self,
        method: str | HTTPMethod,
        route: str,
        json: dict | None = None,
        **kwargs,
    ) -> ResponseBody:
        response = await self.execute_request(method=method, route=route, json=json, **kwargs)
        return self._parse_response_body(response)

    def _build_mock_request_data(
        self,
        path: str,
        body: Any = _UNSET,
        headers: dict | None = None,
        status_code: int | None = None,
        extra_info: dict | None = None,
        proxy_host: str | None = None,
        timeout: float | None = None,
        rules: list[dict] | None = None,
        methods: list[str] | None = None,
        sequence: dict | None = None,
        recording: dict | None = None,
        include_none: bool = False,
        **kwargs,
    ) -> dict:
        if "cache_time" in kwargs:
            raise TypeError("cache_time has been removed; use recording for upstream record/replay")
        mock_data = {}
        if body is not _UNSET:
            mock_data["body"] = body
        if status_code is not _UNSET and (include_none or status_code is not None):
            mock_data["status_code"] = status_code
        if headers is not _UNSET and (include_none or headers is not None):
            mock_data["headers"] = headers

        request_data = {"path": normalize_mock_path(path)}
        if methods is not _UNSET and (include_none or methods is not None):
            request_data["methods"] = methods
        if mock_data:
            request_data["mock_data"] = mock_data
        if extra_info is not _UNSET and (include_none or extra_info is not None):
            request_data["extra_info"] = extra_info
        if proxy_host is not _UNSET and (include_none or proxy_host is not None):
            request_data["proxy_host"] = proxy_host
        if timeout is not _UNSET and (include_none or timeout is not None):
            request_data["timeout"] = timeout
        if rules is not _UNSET and (include_none or rules is not None):
            request_data["rules"] = rules
        if sequence is not _UNSET and (include_none or sequence is not None):
            request_data["sequence"] = sequence

        if recording is not _UNSET and (include_none or recording is not None):
            request_data["recording"] = recording

        request_data.update(kwargs)
        return request_data

    async def _send_configure(self, method: HTTPMethod, payload: dict):
        query = urlencode({"path": payload["path"]})
        return await self.execute_request_and_get_response_body(
            method=method,
            route=f"{self._service_endpoint(Endpoints.CONFIGURE_MOCK)}?{query}",
            content=msgpack.packb(payload),
            headers={"Content-Type": CONFIGURE_CONTENT_TYPE},
        )

    async def get_proxy_mock(self):
        return await self.execute_request_and_get_response_body(
            HTTPMethod.GET, self._service_endpoint(Endpoints.PROXY_MOCK)
        )

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
        sequence: dict | None = None,
        recording: dict | None = None,
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
            sequence=sequence,
            recording=recording,
            **kwargs,
        )
        return await self._send_configure(HTTPMethod.PUT, payload)

    async def patch_mock(
        self,
        path: str,
        body: Any = _UNSET,
        headers: dict | None = _UNSET,
        status_code: int | None = _UNSET,
        extra_info: dict | None = _UNSET,
        proxy_host: str | None = _UNSET,
        timeout: float | None = _UNSET,
        rules: list[dict] | None = _UNSET,
        methods: list[str] | None = _UNSET,
        sequence: dict | None = _UNSET,
        recording: dict | None = _UNSET,
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
            sequence=sequence,
            recording=recording,
            include_none=True,
            **kwargs,
        )
        return await self._send_configure(HTTPMethod.PATCH, payload)

    async def get_traffic(self, path: str | None = None, method: str | None = None, limit: int | None = None):
        query_params = {
            **({"path": path} if path else {}),
            **({"method": method} if method else {}),
            **({"limit": limit} if limit is not None else {}),
        }
        full_path = f"{self._service_endpoint(Endpoints.TRAFFIC)}?{urlencode(query_params)}"
        return await self.execute_request_and_get_response_body(HTTPMethod.GET, full_path)

    async def get_storage(self, path: str | None = None):
        query_params = {"path": normalize_mock_path(path)} if path is not None else {}
        full_path = f"{self._service_endpoint(Endpoints.STORAGE)}?{urlencode(query_params)}"
        return await self.execute_request_and_get_response_body(HTTPMethod.GET, full_path)

    async def clean_storage(self):
        """Delete all mocks. Use delete_mock(path) to delete one mock."""
        return await self.execute_request_and_get_response_body(
            HTTPMethod.DELETE, self._service_endpoint(Endpoints.STORAGE)
        )

    async def export_mocks(self):
        """Export every configured mock as a snapshot document."""
        return await self.execute_request_and_get_response_body(
            HTTPMethod.GET, self._service_endpoint(Endpoints.STORAGE_SNAPSHOT)
        )

    async def import_mocks(self, snapshot: dict, mode: str = "merge"):
        """Load a snapshot: `merge` keeps the configured mocks, `replace` clears them first."""
        if mode not in {"merge", "replace"}:
            raise ValueError("mode must be 'merge' or 'replace'")
        method = HTTPMethod.PATCH if mode == "merge" else HTTPMethod.PUT
        return await self.execute_request_and_get_response_body(
            method, self._service_endpoint(Endpoints.STORAGE_SNAPSHOT), json=snapshot
        )

    async def delete_mock(self, path: str):
        query = urlencode({"path": normalize_mock_path(path)})
        full_path = f"{self._service_endpoint(Endpoints.STORAGE)}?{query}"
        return await self.execute_request_and_get_response_body(HTTPMethod.DELETE, full_path)

    async def clean_traffic(self):
        return await self.execute_request_and_get_response_body(
            HTTPMethod.DELETE, self._service_endpoint(Endpoints.TRAFFIC)
        )

    async def get_traffic_settings(self):
        return await self.execute_request_and_get_response_body(
            HTTPMethod.GET, self._service_endpoint(Endpoints.TRAFFIC_SETTINGS)
        )

    async def set_traffic_settings(self, record_unknown_traffic: bool | None = None, max_items: int | None = None):
        return await self.execute_request_and_get_response_body(
            HTTPMethod.PATCH,
            self._service_endpoint(Endpoints.TRAFFIC_SETTINGS),
            json=_build_traffic_settings_payload(record_unknown_traffic, max_items),
        )

    async def get_sequence_state(self, path: str, rule_index: int | None = None) -> dict:
        """Read the cursor of a mock sequence, or a rule by its zero-based configuration index."""
        query = sequence_query(path, rule_index)
        route = f"{self._service_endpoint(Endpoints.SEQUENCE_STATE)}?{query}"
        return await self.execute_request_and_get_response_body(HTTPMethod.GET, route)

    async def reset_sequence(self, path: str, rule_index: int | None = None) -> dict:
        """Restart a sequence through a partial update of its state resource."""
        query = sequence_query(path, rule_index)
        route = f"{self._service_endpoint(Endpoints.SEQUENCE_STATE)}?{query}"
        return await self.execute_request_and_get_response_body(HTTPMethod.PATCH, route, json={"position": 0})

    async def get_recordings(self, path: str, recording_id: str | None = None) -> dict:
        """Inspect recorded requests and responses; binary bodies are base64 strings."""
        query = {"path": normalize_mock_path(path)}
        if recording_id is not None:
            query["id"] = recording_id
        route = f"{self._service_endpoint(Endpoints.RECORDINGS)}?{urlencode(query)}"
        return await self.execute_request_and_get_response_body(HTTPMethod.GET, route)

    async def delete_recordings(self, path: str, recording_id: str | None = None) -> dict:
        """Delete one recorded response or the entire collection belonging to a mock."""
        query = {"path": normalize_mock_path(path)}
        if recording_id is not None:
            query["id"] = recording_id
        route = f"{self._service_endpoint(Endpoints.RECORDINGS)}?{urlencode(query)}"
        return await self.execute_request_and_get_response_body(HTTPMethod.DELETE, route)
