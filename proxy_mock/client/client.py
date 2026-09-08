import warnings
from http import HTTPMethod
from typing import Any
from urllib.parse import urlencode

import msgpack

from proxy_mock.client.route import Route
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


class ProxyMock(Route):
    def get_proxy_mock(self):
        return super().execute_request_and_get_response_body(HTTPMethod.GET, Endpoints.PROXY_MOCK)

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

    def _send_configure(self, method: HTTPMethod, payload: dict):
        return super().execute_request_and_get_response_body(
            method=method,
            route=Endpoints.CONFIGURE_MOCK,
            data=msgpack.packb(payload),
            headers={"Content-Type": CONFIGURE_CONTENT_TYPE},
        )

    def configure_mock(
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
            include_body_if_none=True,  # for configure the body may explicitly be None
            **kwargs,
        )
        return self._send_configure(HTTPMethod.POST, payload)

    def patch_mock(
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
            include_body_if_none=False,  # for patch we do not send a body unless one is given
            **kwargs,
        )
        return self._send_configure(HTTPMethod.PATCH, payload)

    def get_traffic(self, path: str | None = None, method: str | None = None, limit: int | None = None):
        query_params = {
            **({"path": path} if path else {}),
            **({"method": method} if method else {}),
            **({"limit": limit} if limit is not None else {}),
        }
        full_path = f"{Endpoints.TRAFFIC}?{urlencode(query_params)}"
        return super().execute_request_and_get_response_body(HTTPMethod.GET, full_path)

    def get_storage(self, path: str | None = None):
        query_params = {**({"path": path} if path else {})}
        full_path = f"{Endpoints.STORAGE}?{urlencode(query_params)}"
        return super().execute_request_and_get_response_body(HTTPMethod.GET, full_path)

    def clean_storage(self, path: str | None = None):
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
            full_path = f"{Endpoints.STORAGE_CLEAN}?{urlencode({'path': path})}"
            return super().execute_request_and_get_response_body(HTTPMethod.POST, full_path)

        return super().execute_request_and_get_response_body(HTTPMethod.DELETE, Endpoints.STORAGE)

    def export_mocks(self):
        """Export every configured mock as a snapshot document."""
        return super().execute_request_and_get_response_body(HTTPMethod.GET, Endpoints.STORAGE_SNAPSHOT)

    def import_mocks(self, snapshot: dict, mode: str = "merge"):
        """Load a snapshot: `merge` keeps the configured mocks, `replace` clears them first."""
        full_path = f"{Endpoints.STORAGE_SNAPSHOT}?{urlencode({'mode': mode})}"
        return super().execute_request_and_get_response_body(HTTPMethod.POST, full_path, json=snapshot)

    def delete_mock(self, path: str):
        full_path = f"{Endpoints.STORAGE}?{urlencode({'path': path})}"
        return super().execute_request_and_get_response_body(HTTPMethod.DELETE, full_path)

    def clean_traffic(self):
        return super().execute_request_and_get_response_body(HTTPMethod.DELETE, Endpoints.TRAFFIC)

    def get_traffic_settings(self):
        return super().execute_request_and_get_response_body(HTTPMethod.GET, Endpoints.TRAFFIC_SETTINGS)

    def set_traffic_settings(self, record_unknown_traffic: bool | None = None, max_items: int | None = None):
        return super().execute_request_and_get_response_body(
            HTTPMethod.PATCH,
            Endpoints.TRAFFIC_SETTINGS,
            json=_build_traffic_settings_payload(record_unknown_traffic, max_items),
        )

    def clean_cache(self):
        """Deprecated: response caching and this endpoint are removed in 3.0."""
        warnings.warn(
            "clean_cache() is deprecated and will be removed in 3.0 together with response caching",
            DeprecationWarning,
            stacklevel=2,
        )
        return super().execute_request_and_get_response_body(HTTPMethod.POST, Endpoints.CACHE_CLEAN)
