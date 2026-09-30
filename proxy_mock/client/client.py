import warnings
from http import HTTPMethod
from typing import Any
from urllib.parse import urlencode

import msgpack

from proxy_mock.client.migration import normalize_mock_path, sequence_query
from proxy_mock.client.route import Route
from proxy_mock.client.service_endpoints import Endpoints

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


class ProxyMock(Route):
    def get_proxy_mock(self):
        return super().execute_request_and_get_response_body(
            HTTPMethod.GET, self._service_endpoint(Endpoints.PROXY_MOCK)
        )

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

    def _send_configure(self, method: HTTPMethod, payload: dict):
        query = urlencode({"path": payload["path"]})
        return super().execute_request_and_get_response_body(
            method=method,
            route=f"{self._service_endpoint(Endpoints.CONFIGURE_MOCK)}?{query}",
            content=msgpack.packb(payload),
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
        return self._send_configure(HTTPMethod.PUT, payload)

    def patch_mock(
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
        return self._send_configure(HTTPMethod.PATCH, payload)

    def get_traffic(self, path: str | None = None, method: str | None = None, limit: int | None = None):
        query_params = {
            **({"path": path} if path else {}),
            **({"method": method} if method else {}),
            **({"limit": limit} if limit is not None else {}),
        }
        full_path = f"{self._service_endpoint(Endpoints.TRAFFIC)}?{urlencode(query_params)}"
        return super().execute_request_and_get_response_body(HTTPMethod.GET, full_path)

    def get_storage(self, path: str | None = None):
        query_params = {"path": normalize_mock_path(path)} if path is not None else {}
        full_path = f"{self._service_endpoint(Endpoints.STORAGE)}?{urlencode(query_params)}"
        return super().execute_request_and_get_response_body(HTTPMethod.GET, full_path)

    def clean_storage(self, path: str | None = None):
        """Delete mocks: all of them, or the one at `path`.

        Passing a path is deprecated — use `delete_mock()`. Both report a missing mock with `404`.
        """
        if path is not None:
            warnings.warn(
                "clean_storage(path=...) is deprecated and will be removed in 3.0; use delete_mock(path)",
                DeprecationWarning,
                stacklevel=2,
            )
            return self.delete_mock(path)

        return super().execute_request_and_get_response_body(
            HTTPMethod.DELETE, self._service_endpoint(Endpoints.STORAGE)
        )

    def export_mocks(self):
        """Export every configured mock as a snapshot document."""
        return super().execute_request_and_get_response_body(
            HTTPMethod.GET, self._service_endpoint(Endpoints.STORAGE_SNAPSHOT)
        )

    def import_mocks(self, snapshot: dict, mode: str = "merge"):
        """Load a snapshot: `merge` keeps the configured mocks, `replace` clears them first."""
        if mode not in {"merge", "replace"}:
            raise ValueError("mode must be 'merge' or 'replace'")
        method = HTTPMethod.PATCH if mode == "merge" else HTTPMethod.PUT
        return super().execute_request_and_get_response_body(
            method, self._service_endpoint(Endpoints.STORAGE_SNAPSHOT), json=snapshot
        )

    def delete_mock(self, path: str):
        query = urlencode({"path": normalize_mock_path(path)})
        full_path = f"{self._service_endpoint(Endpoints.STORAGE)}?{query}"
        return super().execute_request_and_get_response_body(HTTPMethod.DELETE, full_path)

    def clean_traffic(self):
        return super().execute_request_and_get_response_body(
            HTTPMethod.DELETE, self._service_endpoint(Endpoints.TRAFFIC)
        )

    def get_traffic_settings(self):
        return super().execute_request_and_get_response_body(
            HTTPMethod.GET, self._service_endpoint(Endpoints.TRAFFIC_SETTINGS)
        )

    def set_traffic_settings(self, record_unknown_traffic: bool | None = None, max_items: int | None = None):
        return super().execute_request_and_get_response_body(
            HTTPMethod.PATCH,
            self._service_endpoint(Endpoints.TRAFFIC_SETTINGS),
            json=_build_traffic_settings_payload(record_unknown_traffic, max_items),
        )

    def get_sequence_state(self, path: str, rule_index: int | None = None) -> dict:
        """Read the cursor of a mock sequence, or a rule by its zero-based configuration index."""
        query = sequence_query(path, rule_index)
        route = f"{self._service_endpoint(Endpoints.SEQUENCE_STATE)}?{query}"
        return super().execute_request_and_get_response_body(HTTPMethod.GET, route)

    def reset_sequence(self, path: str, rule_index: int | None = None) -> dict:
        """Restart a sequence through a partial update of its state resource."""
        query = sequence_query(path, rule_index)
        route = f"{self._service_endpoint(Endpoints.SEQUENCE_STATE)}?{query}"
        return super().execute_request_and_get_response_body(HTTPMethod.PATCH, route, json={"position": 0})

    def get_recordings(self, path: str, recording_id: str | None = None) -> dict:
        """Inspect recorded requests and responses; binary bodies are base64 strings."""
        query = {"path": normalize_mock_path(path)}
        if recording_id is not None:
            query["id"] = recording_id
        route = f"{self._service_endpoint(Endpoints.RECORDINGS)}?{urlencode(query)}"
        return super().execute_request_and_get_response_body(HTTPMethod.GET, route)

    def delete_recordings(self, path: str, recording_id: str | None = None) -> dict:
        """Delete one recorded response or the entire collection belonging to a mock."""
        query = {"path": normalize_mock_path(path)}
        if recording_id is not None:
            query["id"] = recording_id
        route = f"{self._service_endpoint(Endpoints.RECORDINGS)}?{urlencode(query)}"
        return super().execute_request_and_get_response_body(HTTPMethod.DELETE, route)
