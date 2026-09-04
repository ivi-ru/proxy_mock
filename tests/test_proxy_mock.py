import platform
import tomllib
from http import HTTPMethod

from proxy_mock.client import ProxyMock
from proxy_mock.repositories.traffic_store import DEFAULT_TRAFFIC_MAX


def test_get_proxy_mock(client: ProxyMock):
    assert client.get_proxy_mock().get("success")


class TestProxyMockDetails:
    def test_version_matches_pyproject(self, client: ProxyMock):
        with open("pyproject.toml", "rb") as file:
            expected = tomllib.load(file)["project"]["version"]

        assert client.get_proxy_mock()["version"] == expected

    def test_python_version_of_running_interpreter(self, client: ProxyMock):
        # The server runs in the same process as the tests, so the versions must match.
        assert client.get_proxy_mock()["python_version"] == platform.python_version()

    def test_counters_follow_storage_and_traffic(self, client: ProxyMock, configure_mock, configure_binary_mock):
        client.clean_traffic()
        assert client.get_proxy_mock()["traffic_count"] == 0

        client.execute_request(HTTPMethod.GET, configure_mock["path"])
        client.execute_request(HTTPMethod.GET, configure_binary_mock["path"])

        details = client.get_proxy_mock()
        assert details["mocks_count"] == 2
        assert details["traffic_count"] == 2
        assert details["traffic_max_items"] == DEFAULT_TRAFFIC_MAX

    def test_counters_are_zero_on_clean_instance(self, client: ProxyMock):
        details = client.get_proxy_mock()

        assert details["mocks_count"] == 0
        assert details["traffic_count"] == 0


def test_catch_unknown_path(client: ProxyMock):
    path = "/unknown"
    response = client.execute_request(HTTPMethod.POST, path)

    assert response.status_code == 404
    assert response.json() == {"error": f"No mock found for {path}"}
