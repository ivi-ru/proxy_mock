"""Optional server dependency checks without importing the server itself."""

from importlib.util import find_spec


class ServerDependenciesMissing(RuntimeError):
    """A local server was requested without its optional dependencies."""


def require_server_dependencies() -> None:
    missing = [name for name in ("fastapi", "pydantic", "uvicorn") if find_spec(name) is None]
    if missing:
        raise ServerDependenciesMissing(
            f"Missing server dependencies: {', '.join(missing)}. Install them with: pip install 'proxy_mock[server]'"
        )
