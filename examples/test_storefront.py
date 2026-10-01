"""Run the Compose application and check scripts on loopback, without container DNS."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx2


def test_storefront_check_scripts(proxy_mock, proxy_mock_url):
    scripts = Path(__file__).parent / "compose"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    app_url = f"http://127.0.0.1:{port}"
    environment = {
        **os.environ,
        "INVENTORY_URL": proxy_mock_url,
        "APP_HOST": "127.0.0.1",
        "APP_PORT": str(port),
        "MOCK_URL": proxy_mock_url,
        "APP_URL": app_url,
        "PROXY_MOCK_ADMIN_PREFIX": proxy_mock.admin_prefix,
    }
    with open(os.devnull, "w") as output:
        app = subprocess.Popen([sys.executable, str(scripts / "app.py")], env=environment, stdout=output, stderr=output)
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                assert app.poll() is None, "storefront exited before becoming ready"
                try:
                    if httpx2.get(app_url + "/health", timeout=0.5).status_code == 200:
                        break
                except httpx2.RequestError:
                    pass
                time.sleep(0.05)
            else:
                raise AssertionError("storefront did not become ready")

            check = subprocess.run(
                [sys.executable, str(scripts / "check.py")], env=environment, capture_output=True, text=True, timeout=15
            )
            assert check.returncode == 0, check.stdout + check.stderr
            assert "PASS: storefront response and captured inventory request" in check.stdout
        finally:
            app.terminate()
            app.wait(timeout=10)
