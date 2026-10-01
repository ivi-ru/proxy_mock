from http import HTTPMethod
from typing import Any

import httpx2

from proxy_mock.client import calls
from proxy_mock.client.calls import UNSET
from proxy_mock.client.migration import service_endpoint, validate_admin_prefix
from proxy_mock.client.transport import (
    ProxyMockRequestError,
    ProxyMockResponseError,
    ResponseBody,
    parse_response_body,
    request_options,
    request_url,
)


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

    async def _call(self, call: calls.Call):
        method, route, options = call
        return await self.execute_request_and_get_response_body(method, route, **options)

    async def get_proxy_mock(self):
        return await self._call(calls.service_info(self.admin_prefix))

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
        payload = calls.mock_payload(
            path,
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
        return await self._call(calls.configure(self.admin_prefix, HTTPMethod.PUT, payload))

    async def patch_mock(
        self,
        path: str,
        body: Any = UNSET,
        headers: dict | None = UNSET,
        status_code: int | None = UNSET,
        extra_info: dict | None = UNSET,
        proxy_host: str | None = UNSET,
        timeout: float | None = UNSET,
        rules: list[dict] | None = UNSET,
        methods: list[str] | None = UNSET,
        sequence: dict | None = UNSET,
        recording: dict | None = UNSET,
        **kwargs,
    ):
        payload = calls.mock_payload(
            path,
            include_none=True,
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
        return await self._call(calls.configure(self.admin_prefix, HTTPMethod.PATCH, payload))

    async def get_traffic(self, path: str | None = None, method: str | None = None, limit: int | None = None):
        return await self._call(calls.get_traffic(self.admin_prefix, path, method, limit))

    async def get_storage(self, path: str | None = None):
        return await self._call(calls.get_mocks(self.admin_prefix, path))

    async def clean_storage(self):
        """Delete all mocks. Use delete_mock(path) to delete one mock."""
        return await self._call(calls.delete_mocks(self.admin_prefix))

    async def export_mocks(self):
        """Export every configured mock as a snapshot document."""
        return await self._call(calls.export_snapshot(self.admin_prefix))

    async def import_mocks(self, snapshot: dict, mode: str = "merge"):
        """Load a snapshot: `merge` keeps the configured mocks, `replace` clears them first."""
        return await self._call(calls.import_snapshot(self.admin_prefix, snapshot, mode))

    async def delete_mock(self, path: str):
        return await self._call(calls.delete_mocks(self.admin_prefix, path))

    async def clean_traffic(self):
        return await self._call(calls.clean_traffic(self.admin_prefix))

    async def get_traffic_settings(self):
        return await self._call(calls.get_traffic_settings(self.admin_prefix))

    async def set_traffic_settings(self, record_unknown_traffic: bool | None = None, max_items: int | None = None):
        return await self._call(calls.set_traffic_settings(self.admin_prefix, record_unknown_traffic, max_items))

    async def get_sequence_state(self, path: str, rule_index: int | None = None) -> dict:
        """Read the cursor of a mock sequence, or a rule by its zero-based configuration index."""
        return await self._call(calls.get_sequence_state(self.admin_prefix, path, rule_index))

    async def reset_sequence(self, path: str, rule_index: int | None = None) -> dict:
        """Restart a sequence through a partial update of its state resource."""
        return await self._call(calls.reset_sequence(self.admin_prefix, path, rule_index))

    async def get_recordings(self, path: str, recording_id: str | None = None) -> dict:
        """Inspect recorded requests and responses; binary bodies are base64 strings."""
        return await self._call(calls.get_recordings(self.admin_prefix, path, recording_id))

    async def delete_recordings(self, path: str, recording_id: str | None = None) -> dict:
        """Delete one recorded response or the entire collection belonging to a mock."""
        return await self._call(calls.delete_recordings(self.admin_prefix, path, recording_id))
