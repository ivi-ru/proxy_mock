"""Endpoints that 3.0 removes keep working, and say so in the response headers."""

import requests

from proxy_mock.client import ProxyMock
from tests import HOST


class TestRestfulReplacements:
    def test_delete_traffic_clears_the_store(self, client: ProxyMock, configure_mock):
        client.execute_request("GET", "/test")
        assert client.get_traffic()["count"] == 1

        response = requests.delete(f"{HOST}/traffic", timeout=10)

        assert response.status_code == 200
        assert "Deprecation" not in response.headers
        assert client.get_traffic()["count"] == 0

    def test_patch_traffic_settings_applies_a_partial_update(self, client: ProxyMock, restore_traffic_settings):
        response = requests.patch(f"{HOST}/traffic/settings", json={"max_items": 17}, timeout=10)

        assert response.status_code == 200
        assert response.json()["data"]["max_items"] == 17
        assert "Deprecation" not in response.headers


class TestDeprecatedAliases:
    def test_post_storage_clean_is_marked(self, client: ProxyMock, configure_mock):
        response = requests.post(f"{HOST}/storage/clean", timeout=10)

        assert response.status_code == 200
        assert response.headers["Deprecation"] == "true"
        assert 'rel="successor-version"' in response.headers["Link"]
        assert "/storage" in response.headers["Link"]

    def test_post_traffic_clean_is_marked(self, client: ProxyMock):
        response = requests.post(f"{HOST}/traffic/clean", timeout=10)

        assert response.status_code == 200
        assert response.headers["Deprecation"] == "true"

    def test_post_traffic_settings_is_marked(self, client: ProxyMock, restore_traffic_settings):
        response = requests.post(f"{HOST}/traffic/settings", json={"max_items": 23}, timeout=10)

        assert response.status_code == 200
        assert response.json()["data"]["max_items"] == 23
        assert response.headers["Deprecation"] == "true"

    def test_post_cache_clean_is_marked(self, client: ProxyMock):
        response = requests.post(f"{HOST}/cache/clean", timeout=10)

        assert response.status_code == 200
        assert response.headers["Deprecation"] == "true"
