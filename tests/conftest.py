import time
from copy import deepcopy
from threading import Thread

import pytest

from proxy_mock.any_catcher import app
from proxy_mock.client import ProxyMock
from tests import HOST
from tests.constants import BYTE_RESPONSE, TEST_CONFIGURE_DATA


@pytest.fixture(scope="session")
def client():
    return ProxyMock(HOST)


def run_server():
    import uvicorn

    uvicorn.run(app, port=5001, log_level="warning")


@pytest.fixture(scope="session", autouse=True)
def start_app():
    server_thread = Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1)


@pytest.fixture
def configure_mock(client: ProxyMock, configure_mock_data):
    configure_response = client.configure_mock(**configure_mock_data)
    assert configure_response.get("success")

    return configure_mock_data


@pytest.fixture
def configure_mock_with_rules(client: ProxyMock, configure_mock_data):
    configure_mock_data["rules"] = [
        {
            "input_data": {"body": {"test": True}},
            "output_data": {"body": "success"},
            "extra_info": {
                "extra": True,
                "is_valid": {
                    "valid": "yes",
                    "count": 1,
                },
            },
        }
    ]
    configure_response = client.configure_mock(**configure_mock_data)
    assert configure_response.get("success")

    return configure_mock_data


@pytest.fixture
def configure_binary_mock(client: ProxyMock, configure_mock_data):
    configure_mock_data["path"] += "/binary"
    configure_mock_data["body"] = BYTE_RESPONSE
    configure_response = client.configure_mock(**configure_mock_data)
    assert configure_response.get("success")

    return configure_mock_data


@pytest.fixture(autouse=True)
def setup_server(client: ProxyMock):
    client.clean_storage()
    client.clean_traffic()


@pytest.fixture
def configure_mock_data():
    return deepcopy(TEST_CONFIGURE_DATA)


@pytest.fixture
def restore_traffic_settings(client: ProxyMock):
    """The server is started once per session, and traffic settings are global instance state.

    Without restoring them, disabled recording or a lowered limit would leak into other tests.
    """
    original = client.get_traffic_settings()["data"]
    yield
    client.set_traffic_settings(**original)
