import asyncio
from http import HTTPMethod

import pytest

from proxy_mock.client import ProxyMock
from proxy_mock.core.settings import RECORD_UNKNOWN_TRAFFIC_ENV, record_unknown_traffic_default
from proxy_mock.repositories.traffic_store import DEFAULT_TRAFFIC_MAX, TrafficStore
from tests.constants import BYTE_RESPONSE


class TestTraffic:
    def test_traffic(self, client: ProxyMock):
        response = client.get_traffic()

        assert response["success"]
        assert not response["data"]

    def test_traffic_by_existing_service(self, client: ProxyMock, configure_mock):
        client.execute_request_and_get_response_body(HTTPMethod.GET, configure_mock["path"])
        response = client.get_traffic()

        assert response["success"]
        assert response["data"]

        for req_param in response["data"]:
            assert req_param["extra_info"] == configure_mock["extra_info"]
            assert req_param["request_body"] is None
            assert req_param["request_headers"]
            assert req_param["request_path"] == configure_mock["path"]

    def test_send_binary_request(self, client: ProxyMock, configure_binary_mock):
        client.execute_request(HTTPMethod.POST, configure_binary_mock["path"], data=BYTE_RESPONSE)

        response = client.get_traffic()

        assert response["success"]
        assert response["data"]

        for req_param in response["data"]:
            assert req_param["request_body"] == BYTE_RESPONSE.decode()
            assert req_param["request_path"] == configure_binary_mock["path"]
            assert req_param["request_headers"]

    def test_send_request_with_headers(self, client: ProxyMock, configure_mock):
        test_header, value = "X-Test-Header", "123"
        client.execute_request(HTTPMethod.POST, configure_mock["path"], headers={test_header: value})

        response = client.get_traffic()

        assert response["success"]
        assert response["data"]

        for req_param in response["data"]:
            assert req_param["request_path"] == configure_mock["path"]
            assert req_param["request_headers"][test_header.lower()] == value

    def test_get_rule_extra_info(self, client: ProxyMock, configure_mock_with_rules):
        client.execute_request(
            HTTPMethod.POST,
            configure_mock_with_rules["path"],
            json=configure_mock_with_rules["rules"][0]["input_data"]["body"],
        )

        response = client.get_traffic()

        assert response["success"]
        assert response["data"]

        for req_param in response["data"]:
            assert req_param["request_path"] == configure_mock_with_rules["path"]
            assert req_param.get("rule_extra_info") == configure_mock_with_rules["rules"][0]["extra_info"]


class TestTraffic404:
    def test_traffic_recorded_for_missing_mock(self, client: ProxyMock):
        client.clean_traffic()

        missing_path = "/definitely-not-a-mock-xyz"
        response = client.execute_request(HTTPMethod.GET, missing_path)
        assert response.status_code == 404

        traffic = client.get_traffic(path=missing_path)
        assert traffic["success"]
        assert traffic["data"]

        for req_param in traffic["data"]:
            assert req_param["request_path"] == missing_path
            assert req_param["request_method"] == HTTPMethod.GET
            assert req_param["extra_info"] == {"status_code": 404}


class TestRecordUnknownTrafficSetting:
    missing_path = "/definitely-not-a-mock-toggle"

    def test_default_is_enabled(self, client: ProxyMock):
        response = client.get_traffic_settings()

        assert response["success"]
        assert response["data"]["record_unknown_traffic"] is True

    def test_disabled_skips_recording_but_keeps_404(self, client: ProxyMock, restore_traffic_settings):
        updated = client.set_traffic_settings(record_unknown_traffic=False)
        assert updated["data"]["record_unknown_traffic"] is False

        response = client.execute_request(HTTPMethod.GET, self.missing_path)
        assert response.status_code == 404
        assert response.json() == {"error": f"No mock found for {self.missing_path}"}

        assert not client.get_traffic(path=self.missing_path)["data"]

    def test_enabling_back_resumes_recording(self, client: ProxyMock, restore_traffic_settings):
        client.set_traffic_settings(record_unknown_traffic=False)
        client.execute_request(HTTPMethod.GET, self.missing_path)
        assert not client.get_traffic(path=self.missing_path)["data"]

        client.set_traffic_settings(record_unknown_traffic=True)
        client.execute_request(HTTPMethod.GET, self.missing_path)
        assert client.get_traffic(path=self.missing_path)["data"]

    def test_invalid_payload_returns_422(self, client: ProxyMock):
        response = client.execute_request(
            HTTPMethod.POST, "/traffic/settings", json={"record_unknown_traffic": "not-a-bool"}
        )

        assert response.status_code == 422
        assert not response.json()["success"]

    def test_broken_json_returns_400(self, client: ProxyMock):
        response = client.execute_request(
            HTTPMethod.POST,
            "/traffic/settings",
            data=b"{not json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        assert not response.json()["success"]

    def test_empty_payload_returns_422(self, client: ProxyMock):
        response = client.execute_request(HTTPMethod.POST, "/traffic/settings", json={})

        assert response.status_code == 422
        assert not response.json()["success"]


class TestTrafficMaxItemsSetting:
    def test_default_matches_store_limit(self, client: ProxyMock):
        assert client.get_traffic_settings()["data"]["max_items"] == DEFAULT_TRAFFIC_MAX

    def test_lowering_limit_trims_to_newest(self, client: ProxyMock, configure_mock, restore_traffic_settings):
        for _ in range(5):
            client.execute_request(HTTPMethod.GET, configure_mock["path"])
        assert client.get_traffic()["count"] == 5

        updated = client.set_traffic_settings(max_items=2)
        assert updated["data"]["max_items"] == 2

        # The limit applied to already stored records, keeping the most recent ones.
        assert client.get_traffic()["count"] == 2

    def test_limit_holds_for_new_records(self, client: ProxyMock, configure_mock, restore_traffic_settings):
        client.set_traffic_settings(max_items=3)

        for _ in range(10):
            client.execute_request(HTTPMethod.GET, configure_mock["path"])

        assert client.get_traffic()["count"] == 3

    def test_fields_are_independent(self, client: ProxyMock, restore_traffic_settings):
        client.set_traffic_settings(record_unknown_traffic=False)
        data = client.set_traffic_settings(max_items=7)["data"]

        assert data["max_items"] == 7
        assert data["record_unknown_traffic"] is False  # not reset by an update that only sets max_items

    @pytest.mark.parametrize("value", [0, -1, "many"])
    def test_invalid_max_items_returns_422(self, client: ProxyMock, value):
        response = client.execute_request(HTTPMethod.POST, "/traffic/settings", json={"max_items": value})

        assert response.status_code == 422
        assert not response.json()["success"]


class TestRecordUnknownTrafficEnv:
    def test_default_without_env(self, monkeypatch):
        monkeypatch.delenv(RECORD_UNKNOWN_TRAFFIC_ENV, raising=False)
        assert record_unknown_traffic_default() is True

    @pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "off", " Off "])
    def test_falsy_values(self, monkeypatch, value):
        monkeypatch.setenv(RECORD_UNKNOWN_TRAFFIC_ENV, value)
        assert record_unknown_traffic_default() is False

    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on"])
    def test_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv(RECORD_UNKNOWN_TRAFFIC_ENV, value)
        assert record_unknown_traffic_default() is True

    @pytest.mark.parametrize("value", ["", "maybe"])
    def test_unknown_value_falls_back_to_default(self, monkeypatch, value):
        monkeypatch.setenv(RECORD_UNKNOWN_TRAFFIC_ENV, value)
        assert record_unknown_traffic_default() is True


class TestTrafficTimeFields:
    def test_traffic_has_only_iso_timestamp(self, client: ProxyMock, configure_mock):
        client.clean_traffic()
        client.execute_request_and_get_response_body(HTTPMethod.GET, configure_mock["path"])

        traffic = client.get_traffic()
        assert traffic["data"]

        for req_param in traffic["data"]:
            assert req_param.get("requested_at")
            assert "requested_at_ts" not in req_param


class TestTrafficStoreLimit:
    def test_default_limit_is_1000(self):
        assert DEFAULT_TRAFFIC_MAX == 1000

    def test_store_keeps_only_last_n(self):
        async def scenario():
            store = TrafficStore(max_items=100)
            for i in range(150):
                await store.add({"request_path": f"/p{i}"})
            return await store.list()

        items = asyncio.run(scenario())
        assert len(items) == 100
        assert items[0]["request_path"] == "/p50"
        assert items[-1]["request_path"] == "/p149"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("PROXY_MOCK_TRAFFIC_MAX", "5")

        async def scenario():
            store = TrafficStore()
            for i in range(20):
                await store.add({"request_path": f"/p{i}"})
            return await store.list()

        items = asyncio.run(scenario())
        assert len(items) == 5

    def test_set_max_items_trims_to_newest(self):
        async def scenario():
            store = TrafficStore(max_items=10)
            for i in range(10):
                await store.add({"request_path": f"/p{i}"})
            await store.set_max_items(3)
            return store.max_items, await store.count(), await store.list()

        max_items, count, items = asyncio.run(scenario())
        assert max_items == 3
        assert count == 3
        assert [item["request_path"] for item in items] == ["/p7", "/p8", "/p9"]

    def test_set_max_items_holds_after_resize(self):
        async def scenario():
            store = TrafficStore(max_items=100)
            await store.set_max_items(2)
            for i in range(10):
                await store.add({"request_path": f"/p{i}"})
            return await store.list()

        items = asyncio.run(scenario())
        assert [item["request_path"] for item in items] == ["/p8", "/p9"]

    def test_count_tracks_additions_and_clear(self):
        async def scenario():
            store = TrafficStore(max_items=10)
            empty = await store.count()
            for i in range(4):
                await store.add({"request_path": f"/p{i}"})
            filled = await store.count()
            await store.clear()
            return empty, filled, await store.count()

        assert asyncio.run(scenario()) == (0, 4, 0)


class TestClearTraffic:
    request_test_data = {"test_key": "test_value"}

    def test_clear_traffic(self, client: ProxyMock, configure_mock, configure_binary_mock):
        mock_response = client.execute_request_and_get_response_body(HTTPMethod.GET, configure_mock["path"])
        assert mock_response

        mock_response = client.execute_request_and_get_response_body(HTTPMethod.GET, configure_binary_mock["path"])
        assert mock_response

        traffic_storage = client.get_traffic()
        assert len(traffic_storage["data"]) == 2

        response = client.clean_traffic()
        assert response.get("success")

        traffic_storage = client.get_traffic()
        assert not traffic_storage["data"]
