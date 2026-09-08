import json
import time
from http import HTTPMethod

import pytest

from proxy_mock.client import ProxyMock
from tests.constants import (
    EMPTY_BYTE_RESPONSE,
    EXPECTED_RESPONSE,
    EXPECTED_STATUSES,
    INCOMPLETE_PROXY_HOST,
    MOCK_METHODS,
    MOCK_PATHS,
    PROXY_HOST_DATA,
    TEST_RULES_DATA,
)


class TestConfigure:
    @pytest.mark.parametrize("mock_path", MOCK_PATHS)
    def test_any_paths(self, client: ProxyMock, mock_path, configure_mock_data):
        configure_response = client.configure_mock(mock_path, configure_mock_data["body"])
        assert configure_response.get("success")

        mock_path = mock_path.replace("{arg}", "any_value")
        mock_path = mock_path.replace("{arg2}", "any_value2")
        test_response = client.execute_request_and_get_response_body(HTTPMethod.GET, mock_path)
        assert test_response == configure_mock_data["body"]

    @pytest.mark.parametrize("expected_response", EXPECTED_RESPONSE)
    def test_any_responses(self, client: ProxyMock, expected_response, configure_mock_data):
        configure_response = client.configure_mock(path=configure_mock_data["path"], body=expected_response)

        assert configure_response.get("success")

        test_response = client.execute_request_and_get_response_body(HTTPMethod.GET, configure_mock_data["path"])
        assert test_response == expected_response

    @pytest.mark.parametrize("expected_status", EXPECTED_STATUSES)
    def test_any_statuses(self, client: ProxyMock, expected_status, configure_mock_data):
        configure_response = client.configure_mock(
            path=configure_mock_data["path"], body=configure_mock_data["body"], status_code=expected_status
        )

        assert configure_response.get("success")

        test_response = client.execute_request(HTTPMethod.GET, configure_mock_data["path"])
        assert test_response.status_code == expected_status

    @pytest.mark.parametrize("request_methods", MOCK_METHODS)
    def test_any_methods(self, client: ProxyMock, request_methods, configure_mock_data):
        configure_response = client.configure_mock(
            path=configure_mock_data["path"], body=configure_mock_data["body"], methods=request_methods
        )

        assert configure_response.get("success")

        if request_methods:
            for method in request_methods:
                assert client.execute_request(method, configure_mock_data["path"])
        else:
            assert client.execute_request(HTTPMethod.GET, configure_mock_data["path"])

    def test_save_traffic_by_new_request(self, client: ProxyMock, configure_mock_data):
        configure_response = client.configure_mock(**configure_mock_data)
        assert configure_response.get("success")

        mock_response = client.execute_request(HTTPMethod.GET, configure_mock_data["path"])
        assert mock_response.json() == configure_mock_data["body"]
        assert mock_response.status_code == configure_mock_data["status_code"]

        traffic_response = client.get_traffic()
        assert traffic_response.get("data")
        for req_param in traffic_response["data"]:
            assert req_param["extra_info"] == configure_mock_data["extra_info"]

    def test_proxying_to_host(self, client: ProxyMock, configure_mock_data):
        proxy_host, path = PROXY_HOST_DATA

        configure_mock_data["proxy_host"] = proxy_host
        configure_mock_data["path"] = path

        configure_response = client.configure_mock(**configure_mock_data)
        assert configure_response.get("success")

        mock_response = client.execute_request(HTTPMethod.GET, configure_mock_data["path"])
        assert mock_response.content
        assert mock_response.ok

    def test_self_proxy_loop_is_broken(self, client: ProxyMock, configure_mock_data):
        # The mock proxies to itself, so the request comes back to us and must be stopped.
        configure_mock_data["path"] = "/self-proxy-loop"
        configure_mock_data["proxy_host"] = client.host

        configure_response = client.configure_mock(**configure_mock_data)
        assert configure_response.get("success")

        response = client.execute_request(HTTPMethod.GET, configure_mock_data["path"])
        assert response.status_code == 508

    def test_proxy_host_blocked_by_allowlist(self, client: ProxyMock, configure_mock_data, monkeypatch):
        monkeypatch.setenv("PROXY_MOCK_ALLOWED_PROXY_HOSTS", "allowed.example.com")

        proxy_host, path = PROXY_HOST_DATA
        configure_mock_data["proxy_host"] = proxy_host
        configure_mock_data["path"] = path

        configure_response = client.configure_mock(**configure_mock_data)
        assert configure_response.get("success")

        mock_response = client.execute_request(HTTPMethod.GET, configure_mock_data["path"])
        assert mock_response.status_code == 403

    def test_timeout(self, client: ProxyMock, configure_mock_data):
        configure_mock_data["timeout"] = 0.57

        configure_response = client.configure_mock(**configure_mock_data)
        assert configure_response.get("success")

        start_time = time.time()
        mock_response = client.execute_request(HTTPMethod.GET, configure_mock_data["path"])
        end_time = time.time()
        elapsed_time = end_time - start_time

        assert elapsed_time >= configure_mock_data["timeout"]
        assert mock_response.json() == configure_mock_data["body"]
        assert mock_response.status_code == configure_mock_data["status_code"]

    def test_custom_headers(self, client: ProxyMock, configure_mock_data):
        configure_response = client.configure_mock(**configure_mock_data)
        assert configure_response.get("success")

        mock_response = client.execute_request(HTTPMethod.GET, configure_mock_data["path"])

        for key, value in configure_mock_data["headers"].items():
            assert mock_response.headers[key] == value

        assert mock_response.json() == configure_mock_data["body"]
        assert mock_response.status_code == configure_mock_data["status_code"]

    def test_bad_proxy_host(self, client: ProxyMock, configure_mock_data):
        proxy_host, path = INCOMPLETE_PROXY_HOST

        configure_mock_data["proxy_host"] = proxy_host
        configure_mock_data["path"] = path

        configure_response = client.configure_mock(**configure_mock_data)
        assert not configure_response.get("success")
        assert configure_response.get("error"), configure_response

    @pytest.mark.parametrize("rule_data", TEST_RULES_DATA)
    def test_rules(self, client: ProxyMock, rule_data, configure_mock_data):
        if rule_data["input_data"].get("proxy_host"):
            configure_mock_data["path"] = PROXY_HOST_DATA[1]

        configure_mock_data["rules"] = [rule_data]

        configure_response = client.configure_mock(**configure_mock_data)
        assert configure_response.get("success")

        input_data_body = rule_data["input_data"].get("body")
        input_data_method = rule_data["input_data"].get("methods")

        test_response = client.execute_request(
            input_data_method[0] if input_data_method else HTTPMethod.POST,
            configure_mock_data["path"],
            params=rule_data["input_data"].get("query"),
            data=input_data_body if isinstance(input_data_body, bytes) else json.dumps(input_data_body),
            headers=rule_data["input_data"].get("headers"),
        )

        if rule_data["input_data"].get("proxy_host"):
            assert test_response.content
            assert test_response.ok
            return

        assert test_response.elapsed.total_seconds() >= rule_data["input_data"].get("timeout", 0)

        if isinstance(rule_data["output_data"]["body"], bytes):
            assert test_response.content == rule_data["output_data"]["body"]
        else:
            assert test_response.json() == rule_data["output_data"]["body"]

        assert test_response.status_code == rule_data["output_data"]["status_code"]
        assert test_response.headers.items() >= rule_data["output_data"]["headers"].items()

    @pytest.mark.parametrize("rule_data", TEST_RULES_DATA)
    def test_rules_negative(self, client: ProxyMock, rule_data, configure_mock_data):
        configure_mock_data["rules"] = [rule_data]

        configure_response = client.configure_mock(**configure_mock_data)
        assert configure_response.get("success")

        test_response = client.execute_request(
            HTTPMethod.POST,
            configure_mock_data["path"],
            json={"other_data": "test"},
            headers={"unknown": "test"},
        )

        assert test_response.json() != rule_data["output_data"]["body"]
        assert test_response.status_code != rule_data["output_data"]["status_code"]
        assert not rule_data["output_data"]["headers"].items() >= test_response.headers.items()

    def test_many_rules(self, client: ProxyMock, configure_mock_data):
        rule_data = [TEST_RULES_DATA[0], TEST_RULES_DATA[2]]
        configure_mock_data["rules"] = rule_data

        configure_response = client.configure_mock(**configure_mock_data)
        assert configure_response.get("success")

        test_response = client.execute_request(
            HTTPMethod.POST,
            configure_mock_data["path"],
            json=rule_data[0]["input_data"]["body"],
        )
        assert test_response.json() == rule_data[0]["output_data"]["body"]

        test_response = client.execute_request(
            HTTPMethod.POST,
            configure_mock_data["path"],
            headers=rule_data[1]["input_data"]["headers"],
        )
        assert test_response.json() == rule_data[1]["output_data"]["body"]

    def test_empty_response(self, client: ProxyMock, configure_mock_data):
        configure_mock_data["body"] = EMPTY_BYTE_RESPONSE

        configure_response = client.configure_mock(**configure_mock_data)
        assert configure_response.get("success")

        mock_response = client.execute_request(HTTPMethod.GET, configure_mock_data["path"])
        assert mock_response.content == EMPTY_BYTE_RESPONSE
