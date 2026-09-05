"""Export and import of the mock storage as a JSON snapshot."""

import base64

import pytest
import requests

from proxy_mock.client import ProxyMock
from proxy_mock.services.snapshot import SNAPSHOT_FORMAT
from tests import HOST
from tests.constants import BYTE_RESPONSE

SNAPSHOT_URL = f"{HOST}/storage/snapshot"


class TestExport:
    def test_empty_storage_exports_an_empty_snapshot(self, client: ProxyMock):
        snapshot = client.export_mocks()

        assert snapshot["format"] == SNAPSHOT_FORMAT
        assert snapshot["protocol"] == "http"
        assert snapshot["generated_by"].startswith("proxy_mock ")
        assert snapshot["mocks"] == []

    def test_configured_mock_is_exported(self, client: ProxyMock, configure_mock):
        snapshot = client.export_mocks()

        assert len(snapshot["mocks"]) == 1
        exported = snapshot["mocks"][0]
        assert exported["path"] == "/test"
        assert exported["mock_data"]["body"] == configure_mock["body"]

    def test_binary_body_travels_as_base64(self, client: ProxyMock, configure_binary_mock):
        exported = client.export_mocks()["mocks"][0]

        assert "body" not in exported["mock_data"]
        assert base64.b64decode(exported["mock_data"]["body_b64"]) == BYTE_RESPONSE


class TestImport:
    def test_round_trip_restores_a_working_mock(self, client: ProxyMock, configure_mock):
        snapshot = client.export_mocks()
        client.clean_storage()
        assert not client.get_storage()["data"]

        result = client.import_mocks(snapshot)
        assert result["success"]
        assert result["data"]["imported"] == 1
        assert result["data"]["paths"] == ["/test"]

        # The restored mock is not only in the storage, it also answers.
        assert client.execute_request("GET", "/test").json() == configure_mock["body"]

    def test_binary_body_survives_the_round_trip(self, client: ProxyMock, configure_binary_mock):
        snapshot = client.export_mocks()
        client.clean_storage()

        client.import_mocks(snapshot)

        assert client.execute_request("GET", "/test/binary").content == BYTE_RESPONSE

    def test_rules_survive_the_round_trip(self, client: ProxyMock, configure_mock_with_rules):
        snapshot = client.export_mocks()
        client.clean_storage()

        client.import_mocks(snapshot)

        response = client.execute_request("POST", "/test", json={"test": True})
        assert response.text == "success"

    def test_merge_keeps_existing_mocks(self, client: ProxyMock, configure_mock):
        snapshot = client.export_mocks()
        client.clean_storage()
        client.configure_mock(path="/other", body={"other": True})

        client.import_mocks(snapshot, mode="merge")

        assert sorted(client.get_storage()["data"]) == ["/other", "/test"]

    def test_replace_drops_existing_mocks(self, client: ProxyMock, configure_mock):
        snapshot = client.export_mocks()
        client.clean_storage()
        client.configure_mock(path="/other", body={"other": True})

        client.import_mocks(snapshot, mode="replace")

        assert list(client.get_storage()["data"]) == ["/test"]
        # The replaced mock stops answering, not just disappears from the storage.
        assert client.execute_request("GET", "/other").status_code == 404


class TestImportValidation:
    @pytest.mark.parametrize(
        "snapshot",
        [
            {"format": 99, "mocks": []},
            {"format": SNAPSHOT_FORMAT, "protocol": "grpc", "mocks": []},
            {"format": SNAPSHOT_FORMAT, "mocks": {}},
            {"format": SNAPSHOT_FORMAT, "mocks": [{"body": "no path"}]},
            {"format": SNAPSHOT_FORMAT, "mocks": [{"path": "/x", "mock_data": {"body_b64": "not base64!"}}]},
            [],
        ],
    )
    def test_invalid_snapshot_is_rejected(self, client: ProxyMock, snapshot):
        response = requests.post(SNAPSHOT_URL, json=snapshot, timeout=10)

        assert response.status_code == 422
        assert not response.json()["success"]

    def test_broken_json_is_rejected(self, client: ProxyMock):
        response = requests.post(
            SNAPSHOT_URL, data=b"{not json", headers={"Content-Type": "application/json"}, timeout=10
        )

        assert response.status_code == 400

    def test_unknown_mode_is_rejected(self, client: ProxyMock):
        response = requests.post(f"{SNAPSHOT_URL}?mode=wipe", json={"format": 1, "mocks": []}, timeout=10)

        assert response.status_code == 400

    def test_nothing_is_written_when_one_mock_is_invalid(self, client: ProxyMock, configure_mock):
        snapshot = {
            "format": SNAPSHOT_FORMAT,
            "mocks": [
                {"path": "/valid", "mock_data": {"body": "ok"}},
                {"path": "/invalid", "proxy_host": "not-a-url"},
            ],
        }

        response = requests.post(f"{SNAPSHOT_URL}?mode=replace", json=snapshot, timeout=10)

        assert response.status_code == 422
        assert response.json()["error"]["mock_index"] == 1
        # Validation happens before anything is written, so the existing storage is untouched.
        assert list(client.get_storage()["data"]) == ["/test"]
