import os
import tomllib
from importlib import metadata

PACKAGE_NAME = "proxy_mock"

RECORD_UNKNOWN_TRAFFIC_ENV = "PROXY_MOCK_RECORD_UNKNOWN_TRAFFIC"
DEFAULT_RECORD_UNKNOWN_TRAFFIC = True

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def record_unknown_traffic_default() -> bool:
    """Whether to record requests that matched no mock (the 404 response) in traffic.

    An unrecognised value falls back to the default, so a typo cannot silently change behaviour.
    """
    raw = os.getenv(RECORD_UNKNOWN_TRAFFIC_ENV, "").strip().lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    return DEFAULT_RECORD_UNKNOWN_TRAFFIC


def get_version_from_pyproject(logger) -> str:
    # Dev checkout or Docker image: the working directory holds proxy_mock's own pyproject.toml.
    # We check the project name so that another project's pyproject.toml is not picked up
    # when proxy_mock is installed as a library.
    try:
        with open("pyproject.toml", "rb") as file:
            pyproject_data = tomllib.load(file)
        project = pyproject_data.get("project") or {}
        if project.get("name") == PACKAGE_NAME:
            version = project["version"]
            logger.info(f"Proxy-Mock version is {version}")
            return version
    except (OSError, tomllib.TOMLDecodeError, KeyError):
        pass

    # Installed as a package: take the version from the distribution metadata
    try:
        version = metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        logger.warning("Could not determine the proxy_mock version")
        return "unknown"

    logger.info(f"Proxy-Mock version is {version}")
    return version
