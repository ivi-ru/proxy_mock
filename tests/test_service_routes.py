"""The administrative namespace is isolated before user route matching."""

import pytest

from proxy_mock.client import ProxyMock


def test_reserved_paths_cannot_be_configured(client: ProxyMock):
    for path in ("/__admin", "/__admin/mocks", "/__admin/docs", "/__admin/unknown"):
        result = client.configure_mock(path=path, body="shadow")
        assert result["success"] is False
        assert result["error"]["code"] == "invalid_path"
    assert client.get_storage()["data"] == {}
    assert client.get_proxy_mock()["version"]


@pytest.mark.parametrize("path", ["/{rest:path}", "/{segment}", "/__administer"])
def test_wildcards_cannot_shadow_admin_or_capture_unknown_admin_traffic(client, path):
    assert client.configure_mock(path=path, body="shadow")["success"]
    for endpoint in ("/__admin", "/__admin/mocks", "/__admin/docs", "/__admin/openapi.json"):
        response = client.execute_request("GET", endpoint)
        assert response.status_code == 200
        assert response.text != "shadow"
    response = client.execute_request("GET", "/__admin/unknown")
    assert response.status_code == 404
    assert response.json()["success"] is False
    response = client.execute_request("POST", "/__admin/mocks")
    assert response.status_code == 405
    assert {"GET", "PUT", "PATCH", "DELETE"} <= set(response.headers["Allow"].replace(" ", "").split(","))
    assert client.get_traffic()["count"] == 0
    client.delete_mock(path)
    client.clean_storage()
    assert client.execute_request("GET", "/__admin/docs").status_code == 200
    assert client.get_proxy_mock()["version"]


@pytest.mark.parametrize("path", ["/", "/storage", "/traffic", "/configure_mock", "/proxy_mock", "/docs"])
def test_former_service_paths_and_root_are_available_for_mocks(client, path):
    assert client.configure_mock(path=path, body="user response")["success"]
    assert client.execute_request("GET", path).text == "user response"
    assert client.get_proxy_mock()["version"]
    assert client.delete_mock(path)["success"]
    assert client.execute_request("GET", path).status_code == 404


@pytest.mark.parametrize("bad_path", ["/__admin/docs", "/x/{a:unknown}", "/{a}/{a}"])
def test_invalid_snapshot_route_cannot_partially_replace_storage(client, bad_path):
    client.configure_mock(path="/kept", body="kept")
    snapshot = {"format": 1, "mocks": [{"path": "/valid"}, {"path": bad_path}]}
    response = client.execute_request("PUT", "/__admin/snapshot", json=snapshot)
    assert response.status_code == 422
    assert list(client.get_storage()["data"]) == ["/kept"]
    assert client.execute_request("GET", "/kept").text == "kept"
    assert client.execute_request("GET", "/__admin/docs").status_code == 200
