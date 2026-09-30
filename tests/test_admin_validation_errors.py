"""Invalid binary input must not break the administrative error representation."""

import msgpack
import pytest


def binary_request(client, method, resource, data):
    return client.execute_request(
        method,
        "/__admin" + resource,
        content=msgpack.packb(data),
        headers={"Content-Type": "application/octet-stream"},
    )


def assert_validation_error(response):
    assert response.status_code == 422, response.text
    data = response.json()
    assert data["success"] is False
    assert isinstance(data["error"]["code"], str)
    assert isinstance(data["error"]["message"], str)
    return data["error"]


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
@pytest.mark.parametrize(
    "invalid",
    [
        {b"unexpected": 1, "another": 2},
        {b"\xff": 1},
        {"mock_data": {b"\xff": 1}},
        {"sequence": {"responses": [{"status_code": b"\xff"}]}},
        {"rules": [{"input_data": {"methods": [b"\xff"]}}]},
        {"recording": {"mode": b"\xff"}},
        {"proxy_host": "invalid"},
    ],
)
def test_invalid_msgpack_mock_preserves_the_existing_mock(client, method, invalid):
    assert client.configure_mock("/kept", body=b"\x00\xff", headers={"X-Kept": "yes"})["success"]
    before = client.export_mocks()
    error = assert_validation_error(binary_request(client, method, "/mocks?path=/kept", invalid))
    assert error["code"] == "invalid_mock"
    assert client.export_mocks() == before
    response = client.execute_request("GET", "/kept")
    assert response.content == b"\x00\xff"
    assert response.headers["X-Kept"] == "yes"


@pytest.mark.parametrize("invalid", [{"max_items": b"\xff"}, {"record_unknown_traffic": b"\xff"}])
def test_invalid_msgpack_settings_preserve_settings(client, invalid):
    before = client.get_traffic_settings()
    error = assert_validation_error(binary_request(client, "PATCH", "/settings", invalid))
    assert error["code"] == "invalid_settings"
    assert client.get_traffic_settings() == before


@pytest.mark.parametrize("invalid", [{"position": b"\xff"}, {b"\xff": 0}])
def test_invalid_msgpack_sequence_reset_preserves_the_cursor(client, invalid):
    assert client.configure_mock("/sequence", sequence={"responses": [{"body": "first"}, {"body": "second"}]})[
        "success"
    ]
    assert client.execute_request("GET", "/sequence").text == "first"
    before = client.get_sequence_state("/sequence")
    error = assert_validation_error(binary_request(client, "PATCH", "/sequence-state?path=/sequence", invalid))
    assert error["code"] == "invalid_sequence_state"
    assert client.get_sequence_state("/sequence") == before
    assert client.execute_request("GET", "/sequence").text == "second"


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_invalid_msgpack_snapshot_preserves_all_mocks(client, method):
    assert client.configure_mock("/kept", body=b"\x00\xff")["success"]
    before = client.export_mocks()
    snapshot = {
        "format": 2,
        "mocks": [
            {"path": "/valid", "mock_data": {"body": "valid"}},
            {"path": "/invalid", "sequence": {"responses": [{"status_code": b"\xff"}]}},
        ],
    }
    error = assert_validation_error(binary_request(client, method, "/snapshot", snapshot))
    assert error["code"] == "invalid_snapshot"
    assert error["details"]["mock_index"] == 1
    assert client.export_mocks() == before
    assert client.execute_request("GET", "/kept").content == b"\x00\xff"


def test_msgpack_response_bytes_remain_supported(client):
    response = binary_request(client, "PUT", "/mocks?path=/binary", {"mock_data": {"body": b"\x00\xff"}})
    assert response.status_code == 201, response.text
    assert client.execute_request("GET", "/binary").content == b"\x00\xff"
    response = binary_request(client, "PATCH", "/mocks?path=/binary", {"mock_data": {"body": b"\xff\x00"}})
    assert response.status_code == 200, response.text
    assert client.execute_request("GET", "/binary").content == b"\xff\x00"
