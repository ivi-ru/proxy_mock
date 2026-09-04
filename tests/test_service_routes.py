"""Service endpoints must not be shadowed or removed by user mocks.

These checks hold an "invisible" FastAPI threshold: service routes added via include_router
are nested in _IncludedRouter and therefore never collide with dynamically added mocks.
On older FastAPI versions those routes sit at the top level, and then a mock can shadow a
service endpoint while DELETE /storage can remove it. If these tests fail, the fastapi
dependency was lowered below the safe threshold (see pyproject.toml).
"""

from http import HTTPMethod

from proxy_mock.client import ProxyMock


class TestServiceRoutesProtected:
    def test_mocking_service_path_does_not_override_it(self, client: ProxyMock):
        # Try to mock the service endpoint /proxy_mock: the real endpoint must win.
        configure_response = client.configure_mock(path="/proxy_mock", body={"hacked": True})
        assert configure_response.get("success")

        service_info = client.get_proxy_mock()
        assert service_info["success"]
        assert service_info.get("version")
        assert "hacked" not in service_info

    def test_deleting_service_path_keeps_service_route_alive(self, client: ProxyMock):
        # remove_runtime_routes must not touch the service endpoint /traffic.
        response = client.execute_request(HTTPMethod.DELETE, "/storage?path=/traffic")
        assert response.status_code == 404  # there is no /traffic mock in the storage

        traffic = client.get_traffic()
        assert traffic["success"]  # the /traffic service endpoint still responds
