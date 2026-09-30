from http import HTTPMethod

import httpx2

from proxy_mock.client.migration import service_endpoint, validate_admin_prefix
from proxy_mock.client.transport import (
    ProxyMockRequestError,
    ProxyMockResponseError,
    ResponseBody,
    parse_response_body,
    request_options,
    request_url,
)


class Route:
    def __init__(
        self,
        host: str,
        timeout: float | httpx2.Timeout | None = 10.0,
        *,
        admin_prefix: str | None = None,
        http_client: httpx2.Client | None = None,
    ) -> None:
        self.admin_prefix = validate_admin_prefix(admin_prefix)
        if http_client is not None and not isinstance(http_client, httpx2.Client):
            raise TypeError("http_client must be an httpx2.Client")
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._owns_http_client = http_client is None
        self.http_client = (
            http_client if http_client is not None else httpx2.Client(base_url=self.host, timeout=timeout)
        )

    def _service_endpoint(self, endpoint: str) -> str:
        return service_endpoint(endpoint, self.admin_prefix)

    def _build_url(self, command: str) -> httpx2.URL:
        return request_url(self.host, command)

    _parse_response_body = staticmethod(parse_response_body)

    def execute_request(
        self, method: str | HTTPMethod, route: str, raise_for_status: bool = False, **kwargs
    ) -> httpx2.Response:
        try:
            response = self.http_client.request(
                method=str(method), url=self._build_url(route), **request_options(kwargs, self.timeout)
            )
        except httpx2.RequestError as err:
            raise ProxyMockRequestError(f"Proxy-mock request error:\n{err}") from err
        if raise_for_status and response.status_code >= 400:
            raise ProxyMockResponseError(response)
        return response

    def execute_request_and_get_response_body(self, method: str | HTTPMethod, route: str, **kwargs) -> ResponseBody:
        return self._parse_response_body(self.execute_request(method=method, route=route, **kwargs))

    def close(self) -> None:
        if self._owns_http_client:
            self.http_client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
