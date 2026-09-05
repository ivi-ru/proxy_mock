"""Command-line entry point: ``proxy-mock``, also reachable as ``python -m proxy_mock``.

Starting the service should not require Docker, a uvicorn incantation or knowledge of the
module layout — those are internals, and this is the supported way in.
"""

import argparse
import json
import sys
from pathlib import Path

from proxy_mock.core.settings import get_version_from_pyproject
from proxy_mock.services.snapshot import SnapshotError, parse_snapshot

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5000
DEFAULT_LOG_LEVEL = "info"
LOG_LEVELS = ("critical", "error", "warning", "info", "debug", "trace")


class SnapshotFileError(Exception):
    """The file given to --mocks cannot be used."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proxy-mock",
        description="Start a proxy-mock server: an HTTP mock and proxy server for automated tests.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"interface to bind (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port to bind (default: {DEFAULT_PORT})")
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        choices=LOG_LEVELS,
        help=f"uvicorn log level (default: {DEFAULT_LOG_LEVEL})",
    )
    parser.add_argument(
        "--mocks",
        type=Path,
        metavar="FILE",
        help="snapshot file (as produced by GET /storage/snapshot) to load at startup",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="accepted for compatibility with uvicorn flags; only 1 is supported",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"proxy-mock {get_version_from_pyproject()}",
    )
    return parser


def read_snapshot(path: Path) -> dict:
    """Read and validate a snapshot file before the server binds its port."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as err:
        raise SnapshotFileError(f"cannot read {path}: {err}") from err

    try:
        snapshot = json.loads(raw)
    except json.JSONDecodeError as err:
        raise SnapshotFileError(f"{path} is not valid JSON: {err}") from err

    try:
        parse_snapshot(snapshot)
    except SnapshotError as err:
        raise SnapshotFileError(f"{path} is not a valid snapshot: {err.detail}") from err

    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.workers != 1:
        parser.error(
            "--workers must be 1: mocks and captured traffic live in the memory of a single "
            "process, so additional workers would answer from an empty storage"
        )

    snapshot = None
    if args.mocks:
        try:
            snapshot = read_snapshot(args.mocks)
        except SnapshotFileError as err:
            print(f"proxy-mock: {err}", file=sys.stderr)
            return 2

    import uvicorn

    from proxy_mock.app import create_app

    app = create_app()
    app.state.preload_snapshot = snapshot

    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
    return 0
