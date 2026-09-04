import json
from typing import Any

import requests


class ProxyMockRequestError(Exception):
    """Error while performing a request to the proxy-mock server."""


class ProxyMockResponseError(Exception):
    """HTTP error returned by the proxy-mock server."""


class Route:
    def __init__(self, host: str, timeout: float = 10.0) -> None:
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _build_url(self, command: str) -> str:
        command = command.strip("/")
        return f"{self.host}/{command}"

    def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        data: bytes | str | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> requests.Response:
        try:
            return self.session.request(
                method=method,
                url=url,
                params=params,
                data=data,
                json=json_data,
                headers=headers,
                timeout=kwargs.pop("timeout", self.timeout),
                **kwargs,
            )
        except (requests.ConnectionError, requests.Timeout) as err:
            raise ProxyMockRequestError(f"Proxy-mock request error:\n{err}") from err

    @staticmethod
    def _parse_response_body(response: requests.Response) -> dict | str | list | bytes | None:
        if not response.content:
            return None

        content_type = response.headers.get("Content-Type", "")
        try:
            if "json" in content_type:
                return response.json()
            if "text" in content_type:
                return response.text
            return response.content
        except json.JSONDecodeError:
            return response.text

    def execute_request(self, method: str, route: str, raise_for_status: bool = False, **kwargs) -> requests.Response:
        url = self._build_url(route)

        # Normalise the json argument: kwargs["json"] is accepted but passed to _request as json_data
        json_payload = kwargs.pop("json", None)

        response = self._request(method=method, url=url, json_data=json_payload, **kwargs)

        if raise_for_status and response.status_code >= 400:
            raise ProxyMockResponseError(f"Proxy-mock returned HTTP {response.status_code}: {response.text}")

        return response

    def execute_request_and_get_response_body(
        self,
        method: str,
        route: str,
        **kwargs,
    ) -> dict | str | list | bytes | None:
        response = self.execute_request(method=method, route=route, **kwargs)
        return self._parse_response_body(response)

    def close(self) -> None:
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
