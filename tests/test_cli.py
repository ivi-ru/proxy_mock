"""The console entry point: argument handling and the snapshot preloaded at startup."""

import json
import socket
import subprocess
import sys
import time

import pytest
import requests

from proxy_mock.cli import SnapshotFileError, build_parser, main, read_snapshot

START_TIMEOUT = 20.0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_ready(url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"proxy-mock exited with code {process.returncode}")
        try:
            if requests.get(f"{url}/proxy_mock", timeout=1).status_code == 200:
                return
        except requests.RequestException:
            time.sleep(0.1)
    raise RuntimeError("proxy-mock did not become ready in time")


class TestArguments:
    def test_defaults(self):
        args = build_parser().parse_args([])

        assert args.host == "0.0.0.0"
        assert args.port == 5000
        assert args.workers == 1
        assert args.mocks is None

    def test_several_workers_are_refused(self, capsys):
        # Mocks and traffic live in the memory of one process, so a second worker would answer
        # from an empty storage. Better a clear error than a service that lies every other call.
        with pytest.raises(SystemExit) as exc:
            main(["--workers", "2"])

        assert exc.value.code == 2
        assert "--workers must be 1" in capsys.readouterr().err

    def test_version_is_printed(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])

        assert exc.value.code == 0
        assert capsys.readouterr().out.startswith("proxy-mock ")


class TestSnapshotFile:
    def test_missing_file_exits_with_an_error(self, tmp_path, capsys):
        assert main(["--mocks", str(tmp_path / "nope.json")]) == 2
        assert "cannot read" in capsys.readouterr().err

    def test_broken_json_exits_with_an_error(self, tmp_path, capsys):
        broken = tmp_path / "mocks.json"
        broken.write_text("{oops", encoding="utf-8")

        assert main(["--mocks", str(broken)]) == 2
        assert "not valid JSON" in capsys.readouterr().err

    def test_invalid_snapshot_is_reported_before_the_server_starts(self, tmp_path):
        invalid = tmp_path / "mocks.json"
        invalid.write_text(json.dumps({"format": 99, "mocks": []}), encoding="utf-8")

        with pytest.raises(SnapshotFileError, match="not a valid snapshot"):
            read_snapshot(invalid)


class TestServeWithPreloadedMocks:
    def test_mocks_from_the_file_answer_after_startup(self, tmp_path):
        snapshot = {
            "format": 1,
            "protocol": "http",
            "mocks": [{"path": "/preloaded", "mock_data": {"body": {"loaded": True}, "status_code": 200}}],
        }
        snapshot_file = tmp_path / "mocks.json"
        snapshot_file.write_text(json.dumps(snapshot), encoding="utf-8")

        port = _free_port()
        url = f"http://127.0.0.1:{port}"
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "proxy_mock",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
                "--mocks",
                str(snapshot_file),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        try:
            _wait_until_ready(url, process)

            assert requests.get(f"{url}/preloaded", timeout=5).json() == {"loaded": True}
            assert requests.get(f"{url}/storage", timeout=5).json()["data"]["/preloaded"]
        finally:
            process.terminate()
            process.wait(timeout=10)
