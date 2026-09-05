"""Smoke test for the built wheel, run outside the repository.

Unit tests import the package from the working tree, so they never notice a packaging mistake:
a module missing from the wheel, an entry point that is not registered, a console script that
does not start. This file is run against an installed wheel in a clean virtualenv.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import requests


def _console_script() -> str:
    """The installed script, found without relying on the virtualenv being activated."""
    found = shutil.which("proxy-mock")
    if found:
        return found

    candidate = Path(sys.executable).parent / "proxy-mock"
    assert candidate.exists(), f"the console script was not installed at {candidate}"
    return str(candidate)


def test_console_script_reports_a_version():
    result = subprocess.run([_console_script(), "--version"], capture_output=True, text=True, check=True)

    assert result.stdout.startswith("proxy-mock ")


def test_module_entry_point_is_runnable():
    result = subprocess.run([sys.executable, "-m", "proxy_mock", "--help"], capture_output=True, text=True, check=True)

    assert "--mocks" in result.stdout


def test_shipped_fixtures_serve_a_mock(proxy_mock, proxy_mock_url):
    """Uses the fixtures from the pytest11 entry point, which only exist if the wheel ships them."""
    proxy_mock.configure_mock(path="/smoke", body={"installed": True})

    response = requests.get(f"{proxy_mock_url}/smoke", timeout=5)

    assert response.json() == {"installed": True}


def test_snapshot_round_trip(proxy_mock):
    proxy_mock.configure_mock(path="/smoke/snapshot", body={"a": 1})
    snapshot = proxy_mock.export_mocks()

    proxy_mock.clean_storage()
    proxy_mock.import_mocks(snapshot)

    assert list(proxy_mock.get_storage()["data"]) == ["/smoke/snapshot"]
