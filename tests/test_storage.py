from http import HTTPMethod

from proxy_mock.client import ProxyMock


class TestGetStorage:
    def test_get_storage(self, client: ProxyMock):
        response = client.get_storage()

        assert response["success"]
        assert not response["data"]

    def test_get_storage_by_existing_path(self, client: ProxyMock, configure_mock):
        response = client.get_storage(configure_mock["path"])

        assert response["success"]
        assert response["data"]

        data = response["data"]
        assert data["extra_info"] == configure_mock["extra_info"]
        assert data["mock_data"]["body"] == configure_mock["body"]
        assert data["mock_data"]["headers"] == configure_mock["headers"]
        assert data["mock_data"]["status_code"] == configure_mock["status_code"]
        assert data["proxy_host"] == configure_mock["proxy_host"]
        assert data["timeout"] == configure_mock["timeout"] or data["timeout"] == 0.0

    def test_get_storage_by_non_existent_path(self, client: ProxyMock, configure_mock):
        response = client.get_storage(configure_mock["path"] + "/test")

        assert response["success"]
        assert not response["data"]

    def test_get_storage_with_binary_body(self, client: ProxyMock, configure_binary_mock):
        response = client.get_storage()

        assert response["success"]
        assert response["data"]

    def test_get_storage_with_binary_body_by_path(self, client: ProxyMock, configure_binary_mock):
        response = client.get_storage(configure_binary_mock["path"])

        assert response["success"]
        assert response["data"]["mock_data"]["body"] == configure_binary_mock["body"].decode()


class TestClearStorage:
    def test_clear_storage(self, client: ProxyMock, configure_mock, configure_binary_mock):
        storage = client.get_storage()
        assert len(storage["data"]) == 2

        response = client.clean_storage()
        assert response.get("success")

        storage = client.get_storage()
        assert not storage["data"]

    def test_delete_existing_mock(self, client: ProxyMock, configure_mock):
        response = client.clean_storage(configure_mock["path"])
        assert response.get("success")

        storage = client.get_storage(configure_mock["path"])
        assert not storage["data"]

    def test_delete_non_existent_mock(self, client: ProxyMock, configure_mock):
        response = client.clean_storage(configure_mock["path"] + "/test")
        assert not response.get("success")

        storage = client.get_storage(configure_mock["path"])
        assert storage["data"]


class TestDeleteMock:
    def test_delete_single_mock_keeps_others(self, client: ProxyMock, configure_mock_data):
        configure_mock_data["path"] = "/keep-me"
        client.configure_mock(**configure_mock_data)
        configure_mock_data["path"] = "/remove-me"
        client.configure_mock(**configure_mock_data)

        response = client.delete_mock("/remove-me")
        assert response["success"]

        assert not client.get_storage("/remove-me")["data"]
        assert client.get_storage("/keep-me")["data"]

    def test_deleted_mock_route_returns_404(self, client: ProxyMock, configure_mock_data):
        configure_mock_data["path"] = "/gone-soon"
        client.configure_mock(**configure_mock_data)

        assert client.execute_request(HTTPMethod.GET, "/gone-soon").status_code == 201
        client.delete_mock("/gone-soon")
        assert client.execute_request(HTTPMethod.GET, "/gone-soon").status_code == 404

    def test_delete_non_existent_returns_404(self, client: ProxyMock):
        response = client.execute_request(HTTPMethod.DELETE, "/storage?path=/never-existed")
        assert response.status_code == 404
        assert not response.json()["success"]

    def test_delete_without_path_clears_all(self, client: ProxyMock, configure_mock_data):
        configure_mock_data["path"] = "/wipe-a"
        client.configure_mock(**configure_mock_data)
        configure_mock_data["path"] = "/wipe-b"
        client.configure_mock(**configure_mock_data)

        response = client.execute_request(HTTPMethod.DELETE, "/storage")
        assert response.status_code == 200

        assert not client.get_storage()["data"]
        # the routes are gone too, so the paths no longer answer with a mock
        assert client.execute_request(HTTPMethod.GET, "/wipe-a").status_code == 404
        assert client.execute_request(HTTPMethod.GET, "/wipe-b").status_code == 404


class TestClearAllRemovesRoutes:
    def test_clean_storage_all_drops_routes(self, client: ProxyMock, configure_mock_data):
        configure_mock_data["path"] = "/no-zombie"
        client.configure_mock(**configure_mock_data)
        assert client.execute_request(HTTPMethod.GET, "/no-zombie").status_code == 201

        client.clean_storage()  # POST /storage/clean without path
        assert client.execute_request(HTTPMethod.GET, "/no-zombie").status_code == 404
