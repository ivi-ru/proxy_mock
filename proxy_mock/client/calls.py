"""What every client method sends, shared by the sync and async transports.

Each builder returns the HTTP method, the route and the request options; the clients only
execute the call. Keeping this in one place stops the two clients from drifting apart.
"""

from http import HTTPMethod
from typing import Any
from urllib.parse import urlencode

import msgpack

from proxy_mock.client.migration import normalize_mock_path, sequence_query, service_endpoint
from proxy_mock.client.service_endpoints import Endpoints

CONFIGURE_CONTENT_TYPE = "application/octet-stream"
# Marks an argument the caller did not pass, so a partial update can send an explicit None.
UNSET: Any = object()

Call = tuple[HTTPMethod, str, dict[str, Any]]


def mock_payload(
    path: str,
    *,
    include_none: bool = False,
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
) -> dict:
    """Build a mock document; None is sent only for a partial update (`include_none`)."""
    if "cache_time" in kwargs:
        raise TypeError("cache_time has been removed; use recording for upstream record/replay")

    def given(value: Any) -> bool:
        return value is not UNSET and (include_none or value is not None)

    mock_data: dict[str, Any] = {} if body is UNSET else {"body": body}
    mock_data.update(
        {name: value for name, value in (("status_code", status_code), ("headers", headers)) if given(value)}
    )

    payload: dict[str, Any] = {"path": normalize_mock_path(path)}
    if given(methods):
        payload["methods"] = methods
    if mock_data:
        payload["mock_data"] = mock_data
    fields = {
        "extra_info": extra_info,
        "proxy_host": proxy_host,
        "timeout": timeout,
        "rules": rules,
        "sequence": sequence,
        "recording": recording,
    }
    payload.update({name: value for name, value in fields.items() if given(value)})
    payload.update(kwargs)
    return payload


def _route(prefix: str, endpoint: str, query: dict | str | None = None) -> str:
    route = service_endpoint(endpoint, prefix)
    if query is None:
        return route
    return f"{route}?{query if isinstance(query, str) else urlencode(query)}"


def _recording_query(path: str, recording_id: str | None) -> dict:
    query = {"path": normalize_mock_path(path)}
    if recording_id is not None:
        query["id"] = recording_id
    return query


def service_info(prefix: str) -> Call:
    return HTTPMethod.GET, _route(prefix, Endpoints.PROXY_MOCK), {}


def configure(prefix: str, method: HTTPMethod, payload: dict) -> Call:
    route = _route(prefix, Endpoints.CONFIGURE_MOCK, {"path": payload["path"]})
    return method, route, {"content": msgpack.packb(payload), "headers": {"Content-Type": CONFIGURE_CONTENT_TYPE}}


def get_mocks(prefix: str, path: str | None = None) -> Call:
    query = {"path": normalize_mock_path(path)} if path is not None else {}
    return HTTPMethod.GET, _route(prefix, Endpoints.STORAGE, query), {}


def delete_mocks(prefix: str, path: str | None = None) -> Call:
    query = {"path": normalize_mock_path(path)} if path is not None else None
    return HTTPMethod.DELETE, _route(prefix, Endpoints.STORAGE, query), {}


def export_snapshot(prefix: str) -> Call:
    return HTTPMethod.GET, _route(prefix, Endpoints.STORAGE_SNAPSHOT), {}


def import_snapshot(prefix: str, snapshot: dict, mode: str) -> Call:
    if mode not in {"merge", "replace"}:
        raise ValueError("mode must be 'merge' or 'replace'")
    method = HTTPMethod.PATCH if mode == "merge" else HTTPMethod.PUT
    return method, _route(prefix, Endpoints.STORAGE_SNAPSHOT), {"json": snapshot}


def get_traffic(prefix: str, path: str | None, method: str | None, limit: int | None) -> Call:
    query = {
        **({"path": path} if path else {}),
        **({"method": method} if method else {}),
        **({"limit": limit} if limit is not None else {}),
    }
    return HTTPMethod.GET, _route(prefix, Endpoints.TRAFFIC, query), {}


def clean_traffic(prefix: str) -> Call:
    return HTTPMethod.DELETE, _route(prefix, Endpoints.TRAFFIC), {}


def get_traffic_settings(prefix: str) -> Call:
    return HTTPMethod.GET, _route(prefix, Endpoints.TRAFFIC_SETTINGS), {}


def set_traffic_settings(prefix: str, record_unknown_traffic: bool | None, max_items: int | None) -> Call:
    # The endpoint accepts a partial update, so fields that were not supplied are left out.
    payload = {}
    if record_unknown_traffic is not None:
        payload["record_unknown_traffic"] = record_unknown_traffic
    if max_items is not None:
        payload["max_items"] = max_items
    return HTTPMethod.PATCH, _route(prefix, Endpoints.TRAFFIC_SETTINGS), {"json": payload}


def get_sequence_state(prefix: str, path: str, rule_index: int | None) -> Call:
    return HTTPMethod.GET, _route(prefix, Endpoints.SEQUENCE_STATE, sequence_query(path, rule_index)), {}


def reset_sequence(prefix: str, path: str, rule_index: int | None) -> Call:
    route = _route(prefix, Endpoints.SEQUENCE_STATE, sequence_query(path, rule_index))
    return HTTPMethod.PATCH, route, {"json": {"position": 0}}


def get_recordings(prefix: str, path: str, recording_id: str | None) -> Call:
    return HTTPMethod.GET, _route(prefix, Endpoints.RECORDINGS, _recording_query(path, recording_id)), {}


def delete_recordings(prefix: str, path: str, recording_id: str | None) -> Call:
    return HTTPMethod.DELETE, _route(prefix, Endpoints.RECORDINGS, _recording_query(path, recording_id)), {}
