"""Administrative API helpers shared without importing server dependencies."""

import re

MIGRATION_URL = "https://github.com/ivi-ru/proxy_mock/blob/main/MIGRATING.md"
DEFAULT_ADMIN_PREFIX = "/__admin"


def validate_admin_prefix(prefix: str | None) -> str:
    if prefix is None:
        return DEFAULT_ADMIN_PREFIX
    if not re.fullmatch(r"/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", prefix):
        raise ValueError("admin_prefix must be an absolute path without trailing slash, query, or URL escapes")
    return prefix


def normalize_mock_path(path: str) -> str:
    """Use the same mock identity in payloads and resource query parameters."""
    if not isinstance(path, str):
        raise ValueError("path must be a non-empty string")
    path = path.split("?")[0].strip()
    if not path:
        raise ValueError("path must not be empty")
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") or "/"


def service_endpoint(endpoint: str, prefix: str | None) -> str:
    return validate_admin_prefix(prefix) + endpoint
