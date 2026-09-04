"""Proxy errors must not bubble up to uvicorn.

Regression: an unreachable `proxy_host` (DNS does not resolve, connection refused) used to
kill the handler with an unhandled httpx2.ConnectError. The client got an empty `500` and an
ASGI traceback was left in the logs. Transport errors now become `502`, timeouts `504`.
"""

from http import HTTPMethod

import httpx2
import pytest

from proxy_mock.client import ProxyMock
from proxy_mock.services.proxy_service import PROXY_BAD_GATEWAY, PROXY_GATEWAY_TIMEOUT, ProxyRequestError
from tests.constants import UNREACHABLE_PROXY_HOST


class TestProxyRequestErrorMapping:
    @pytest.mark.parametrize(
        "error",
        [httpx2.ConnectTimeout("timed out"), httpx2.ReadTimeout("timed out"), httpx2.PoolTimeout("no free slot")],
    )
    def test_timeouts_map_to_gateway_timeout(self, error):
        assert ProxyRequestError("http://host", error).code == PROXY_GATEWAY_TIMEOUT

    @pytest.mark.parametrize(
        "error",
        [
            httpx2.ConnectError("[Errno -2] Name or service not known"),
            httpx2.ReadError("broken pipe"),
            httpx2.RemoteProtocolError("bad response"),
            httpx2.InvalidURL("no host"),
        ],
    )
    def test_other_errors_map_to_bad_gateway(self, error):
        assert ProxyRequestError("http://host", error).code == PROXY_BAD_GATEWAY

    def test_detail_names_host_and_cause(self):
        error = ProxyRequestError(UNREACHABLE_PROXY_HOST, httpx2.ConnectError("Name or service not known"))

        assert UNREACHABLE_PROXY_HOST in error.detail
        assert "ConnectError" in error.detail
        assert "Name or service not known" in error.detail


class TestUnreachableProxyHost:
    def test_mock_proxy_host_returns_502(self, client: ProxyMock, configure_mock_data):
        configure_mock_data["path"] = "/unreachable-proxy"
        configure_mock_data["proxy_host"] = UNREACHABLE_PROXY_HOST
        assert client.configure_mock(**configure_mock_data).get("success")

        response = client.execute_request(HTTPMethod.GET, configure_mock_data["path"])

        assert response.status_code == PROXY_BAD_GATEWAY
        assert UNREACHABLE_PROXY_HOST in response.json()["error"]

    def test_rule_proxy_host_returns_502(self, client: ProxyMock, configure_mock_data):
        configure_mock_data["path"] = "/unreachable-rule-proxy"
        configure_mock_data["rules"] = [
            {
                "input_data": {"methods": [HTTPMethod.GET], "proxy_host": UNREACHABLE_PROXY_HOST},
                "output_data": {"body": "should never be reached"},
            }
        ]
        assert client.configure_mock(**configure_mock_data).get("success")

        response = client.execute_request(HTTPMethod.GET, configure_mock_data["path"])

        assert response.status_code == PROXY_BAD_GATEWAY
        assert UNREACHABLE_PROXY_HOST in response.json()["error"]

    def test_failed_proxy_response_is_not_cached(self, client: ProxyMock, configure_mock_data):
        # Unavailability must not be cached: the host may come back up at any moment.
        configure_mock_data["path"] = "/unreachable-proxy-cached"
        configure_mock_data["proxy_host"] = UNREACHABLE_PROXY_HOST
        configure_mock_data["cache_time"] = 60
        assert client.configure_mock(**configure_mock_data).get("success")

        client.execute_request(HTTPMethod.GET, configure_mock_data["path"])

        client.clean_storage(path=configure_mock_data["path"])
        configure_mock_data.pop("proxy_host")
        configure_mock_data["body"] = {"host": "up"}
        assert client.configure_mock(**configure_mock_data).get("success")

        response = client.execute_request(HTTPMethod.GET, configure_mock_data["path"])
        assert response.status_code == configure_mock_data["status_code"]
        assert response.json() == {"host": "up"}

    def test_request_still_lands_in_traffic(self, client: ProxyMock, configure_mock_data):
        configure_mock_data["path"] = "/unreachable-proxy-traffic"
        configure_mock_data["proxy_host"] = UNREACHABLE_PROXY_HOST
        assert client.configure_mock(**configure_mock_data).get("success")

        client.execute_request(HTTPMethod.GET, configure_mock_data["path"])

        traffic = client.get_traffic(path=configure_mock_data["path"])
        assert traffic["count"] == 1
