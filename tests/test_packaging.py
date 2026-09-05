"""What the installed package promises: entry points and a client import that stays light."""

import subprocess
import sys
from importlib import metadata


class TestLazyImport:
    def test_importing_the_client_does_not_import_the_server(self):
        # A project that only talks to a running instance should not pay for FastAPI and uvicorn.
        # Checked in a subprocess, because this test session has the server imported already.
        code = "import sys, proxy_mock.client; print('fastapi' in sys.modules, 'uvicorn' in sys.modules)"
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)

        assert result.stdout.strip() == "False False"

    def test_create_app_is_still_reachable_from_the_package(self):
        import proxy_mock

        assert callable(proxy_mock.create_app)

    def test_unknown_attribute_still_raises(self):
        import proxy_mock

        try:
            proxy_mock.does_not_exist
        except AttributeError as err:
            assert "does_not_exist" in str(err)
        else:
            raise AssertionError("an unknown attribute must raise AttributeError")


class TestEntryPoints:
    def test_console_script_is_registered(self):
        scripts = {entry.name: entry.value for entry in metadata.entry_points(group="console_scripts")}

        assert scripts.get("proxy-mock") == "proxy_mock.cli:main"

    def test_pytest_plugin_is_registered(self):
        plugins = {entry.name: entry.value for entry in metadata.entry_points(group="pytest11")}

        assert plugins.get("proxy_mock") == "proxy_mock.pytest_plugin"
