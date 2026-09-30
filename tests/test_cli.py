"""The console entry point: argument handling and the snapshot preloaded at startup."""

import json
import socket
import subprocess
import sys
import time

import httpx2
import pytest

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
            if httpx2.get(f"{url}/__admin", timeout=1).status_code == 200:
                return
        except httpx2.RequestError:
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
    @pytest.mark.parametrize("format", [1, 2])
    def test_mocks_from_the_file_answer_after_startup(self, tmp_path, format):
        snapshot = {
            "format": format,
            "protocol": "http",
            "mocks": [{"path": "/preloaded", "mock_data": {"body": {"loaded": True}, "status_code": 200}}],
        }
        if format == 2:
            from tests.test_snapshot_v2 import recording_entry

            snapshot["mocks"].extend(
                [
                    {"path": "/ordered", "sequence": {"responses": [{"body_b64": "/wA="}, {"body": "second"}]}},
                    {"path": "/recorded", "recording": {"mode": "replay"}, "recordings": [recording_entry()]},
                ]
            )
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

            assert httpx2.get(f"{url}/preloaded", timeout=5).json() == {"loaded": True}
            assert httpx2.get(f"{url}/__admin/mocks", timeout=5).json()["data"]["/preloaded"]
            if format == 2:
                assert httpx2.get(f"{url}/ordered", timeout=5).content == b"\xff\x00"
                assert httpx2.get(f"{url}/ordered", timeout=5).text == "second"
                assert httpx2.get(f"{url}/recorded", timeout=5).content == b"\x00\xffsaved"
                exported = httpx2.get(f"{url}/__admin/snapshot", timeout=5).json()
                assert exported["format"] == 2
                assert len(exported["mocks"][-1]["recordings"]) == 1
        finally:
            process.terminate()
            process.wait(timeout=10)


@pytest.mark.parametrize(
    "mock",
    [
        {"path": "/bad", "sequence": {"responses": []}},
        {"path": "/bad", "recording": {"mode": "replay"}, "recordings": [{"id": "bad"}]},
    ],
)
def test_cli_rejects_invalid_format_two_before_startup(tmp_path, capsys, mock):
    snapshot_file = tmp_path / "bad.json"
    snapshot_file.write_text(json.dumps({"format": 2, "mocks": [mock]}), encoding="utf-8")
    assert main(["--mocks", str(snapshot_file)]) == 2
    assert "not a valid snapshot" in capsys.readouterr().err
