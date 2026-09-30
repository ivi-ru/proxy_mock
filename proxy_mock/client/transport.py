"""Transport behavior shared by the synchronous and asynchronous clients."""

from collections.abc import Mapping

import httpx2

ResponseBody = dict | list | str | bytes | int | float | bool | None


class ProxyMockRequestError(Exception):
    """An httpx2 RequestError, retained as __cause__, prevented a completed response."""


class ProxyMockResponseError(Exception):
    """A completed HTTP error returned when the caller requested raise_for_status."""

    def __init__(self, response: httpx2.Response) -> None:
        self.response = response
        super().__init__(f"Proxy-mock returned HTTP {response.status_code}: {response.text}")


def request_url(host: str, route: str) -> httpx2.URL:
    target = httpx2.URL(route)
    if not target.is_relative_url:
        return target
    # Match httpx2's base-url append semantics, including a host mounted under a path.
    # Build an absolute URL so injected clients cannot redirect relative routes to another base.
    base = httpx2.URL(host.rstrip("/") + "/")
    return base.copy_with(raw_path=base.raw_path + target.raw_path.lstrip(b"/"))


def request_options(kwargs: dict, timeout: float | httpx2.Timeout | None) -> dict:
    if kwargs.get("data") is not None and not isinstance(kwargs["data"], Mapping):
        raise TypeError("Use content= for raw request bodies; data= accepts a form mapping")
    return {"timeout": timeout, **kwargs}


def parse_response_body(response: httpx2.Response) -> ResponseBody:
    if not response.content:
        return None
    content_type = response.headers.get("Content-Type", "").lower()
    if "json" in content_type:
        try:
            return response.json()
        except ValueError:
            return response.text
    if "text" in content_type:
        return response.text
    return response.content
