"""pytest fixtures shipped with proxy-mock, registered through the ``pytest11`` entry point.

Installing the package is enough — no ``pytest_plugins`` line and no fixture boilerplate:

    def test_external_service(proxy_mock):
        proxy_mock.configure_mock(path="/external/api", body={"answer": 42})

Everything the server needs is imported inside the fixtures, so a test session that never asks
for them does not pay for FastAPI and uvicorn.
"""

import os
import socket
import threading
import time

import pytest

READY_TIMEOUT = 10.0
SHUTDOWN_TIMEOUT = 5.0
URL_ENV = "PROXY_MOCK_URL"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def proxy_mock_url() -> str:
    """Base URL of a proxy-mock instance.

    If ``PROXY_MOCK_URL`` is set, the tests run against that instance — useful when the service
    is already up in docker compose. Otherwise a server is started in a background thread on a
    free port and shut down at the end of the session.

    Under pytest-xdist every worker starts its own instance, because the mock and traffic
    stores belong to a process.
    """
    external = os.getenv(URL_ENV, "").strip()
    if external:
        yield external.rstrip("/")
        return

    import uvicorn

    from proxy_mock.app import create_app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + READY_TIMEOUT
    while not server.started:
        if not thread.is_alive():
            raise RuntimeError("proxy-mock stopped before it started serving")
        if time.monotonic() > deadline:
            server.should_exit = True
            raise RuntimeError(f"proxy-mock did not start within {READY_TIMEOUT} seconds")
        time.sleep(0.05)

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=SHUTDOWN_TIMEOUT)


@pytest.fixture
def proxy_mock(proxy_mock_url: str):
    """Client bound to the instance, with mocks and traffic reset after every test.

    The reset keeps tests independent. To keep state across tests, build a client of your own
    from ``proxy_mock_url`` instead.
    """
    from proxy_mock.client import ProxyMock

    client = ProxyMock(proxy_mock_url)
    try:
        yield client
    finally:
        client.clean_storage()
        client.clean_traffic()
        client.close()
