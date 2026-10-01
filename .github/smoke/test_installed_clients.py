"""The base wheel works without server dependencies, including pytest auto-loading.

Run outside the repository in a clean base-install virtualenv. PROXY_MOCK_SERVER_PYTHON
points to a separate server-extra virtualenv used only for external-server integration.
"""

import asyncio
import os
import socket
import subprocess
import sys
import time
from importlib.util import find_spec
from pathlib import Path

import httpx2
import pytest

from proxy_mock.client import AsyncProxyMock, ProxyMock


def test_base_install_has_no_server_dependencies():
    for package in ("fastapi", "starlette", "pydantic", "pydantic_core", "uvicorn"):
        assert find_spec(package) is None, f"unexpected server dependency: {package}"


def test_client_cli_and_plugin_imports_stay_light():
    code = """
import sys
import proxy_mock.client
import proxy_mock.cli
import proxy_mock.pytest_plugin
assert not {'fastapi', 'starlette', 'pydantic', 'uvicorn'}.intersection(sys.modules)
"""
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)


@pytest.mark.parametrize("module", [False, True], ids=["console", "module"])
@pytest.mark.parametrize("option", ["--help", "--version"])
def test_command_information_needs_no_server(module, option):
    command = [sys.executable, "-m", "proxy_mock"] if module else [str(Path(sys.executable).parent / "proxy-mock")]
    result = subprocess.run([*command, option], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "proxy-mock" in result.stdout


@pytest.mark.parametrize("arguments", [[], ["--mocks", "mocks.json"]])
def test_server_command_reports_installation_hint(arguments):
    result = subprocess.run([sys.executable, "-m", "proxy_mock", *arguments], capture_output=True, text=True)
    assert result.returncode == 2
    assert "pip install 'proxy_mock[server]'" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "import_code", ["from proxy_mock.app import create_app", "import proxy_mock; proxy_mock.create_app"]
)
def test_app_factory_reports_installation_hint(import_code):
    code = f"""
from proxy_mock._server import ServerDependenciesMissing
try:
    {import_code}
except ServerDependenciesMissing as err:
    assert "proxy_mock[server]" in str(err)
else:
    raise AssertionError("missing server dependencies must be reported")
"""
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)


def test_pytest_session_without_fixtures_needs_no_server(tmp_path):
    test = tmp_path / "test_plain.py"
    test.write_text("def test_plain():\n    assert True\n", encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(test)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_local_pytest_fixture_reports_installation_hint(tmp_path):
    test = tmp_path / "test_local.py"
    test.write_text("def test_local(proxy_mock_url):\n    pass\n", encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if key != "PROXY_MOCK_URL"}
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(test)], env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert "pip install 'proxy_mock[server]'" in result.stdout
    assert "ModuleNotFoundError" not in result.stdout


@pytest.fixture(scope="session")
def external_server(tmp_path_factory):
    server_python = os.environ["PROXY_MOCK_SERVER_PYTHON"]
    assert Path(server_python).is_file()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    log = tmp_path_factory.mktemp("external-server") / "server.log"
    with log.open("w+") as output:
        process = subprocess.Popen(
            [server_python, "-m", "proxy_mock", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                assert process.poll() is None, log.read_text()
                try:
                    if httpx2.get(url + "/__admin", timeout=0.5).status_code == 200:
                        break
                except httpx2.RequestError:
                    pass
                time.sleep(0.05)
            else:
                pytest.fail("external server failed to become ready: " + log.read_text())
            yield url
        finally:
            process.terminate()
            process.wait(timeout=10)


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
def test_clients_work_with_only_base_dependencies(external_server, asynchronous):
    if asynchronous:

        async def scenario():
            async with AsyncProxyMock(external_server) as client:
                assert (await client.configure_mock("/base-async", body=b"\xff\x00"))["success"]
                response = await client.execute_request("GET", "/base-async")
                assert isinstance(response, httpx2.Response) and response.content == b"\xff\x00"
                snapshot = await client.export_mocks()
                await client.clean_storage()
                assert (await client.import_mocks(snapshot))["success"]
                assert (await client.get_storage("/base-async"))["success"]

        asyncio.run(scenario())
    else:
        with ProxyMock(external_server) as client:
            assert client.configure_mock("/base-sync", body=b"\xff\x00")["success"]
            response = client.execute_request("GET", "/base-sync")
            assert isinstance(response, httpx2.Response) and response.content == b"\xff\x00"
            snapshot = client.export_mocks()
            client.clean_storage()
            assert client.import_mocks(snapshot)["success"]
            assert client.get_storage("/base-sync")["success"]


def test_external_pytest_fixtures_need_no_server_extra(external_server, monkeypatch, request):
    monkeypatch.setenv("PROXY_MOCK_URL", external_server + "/")
    assert request.getfixturevalue("proxy_mock_url") == external_server
    client = request.getfixturevalue("proxy_mock")
    assert client.configure_mock("/base-fixture", body={"base": True})["success"]
    assert client.execute_request("GET", "/base-fixture").json() == {"base": True}
