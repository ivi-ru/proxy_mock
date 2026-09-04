from importlib import metadata

from proxy_mock.app import create_app

try:
    __version__ = metadata.version(__package__)
except ModuleNotFoundError:
    __version__ = ""

__all__ = ["create_app"]
