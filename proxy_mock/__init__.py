"""proxy-mock: an HTTP mock and proxy server for automated tests.

``create_app`` is resolved lazily (PEP 562) so that importing the clients does not pull in
FastAPI and uvicorn: a project that only talks to a running instance should not pay for the
server it does not start.
"""

from importlib import metadata
from typing import TYPE_CHECKING

__all__ = ["create_app"]

try:
    __version__ = metadata.version(__package__)
except metadata.PackageNotFoundError:
    __version__ = ""

if TYPE_CHECKING:
    from proxy_mock.app import create_app


def __getattr__(name: str):
    if name == "create_app":
        from proxy_mock.app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted([*__all__, "__version__"])
