"""Migration helpers shared by the clients without importing server dependencies."""

import re

MIGRATION_URL = "https://github.com/ivi-ru/proxy_mock/blob/main/MIGRATING.md"


def validate_admin_prefix(prefix: str | None) -> str | None:
    if prefix is None:
        return None
    if not re.fullmatch(r"/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", prefix):
        raise ValueError("admin_prefix must be an absolute path without trailing slash, query, or URL escapes")
    # An alias must not replace a legacy service route or the built-in API documentation.
    if prefix.split("/")[1] in {
        "proxy_mock",
        "configure_mock",
        "storage",
        "traffic",
        "cache",
        "docs",
        "redoc",
        "openapi.json",
    }:
        raise ValueError("admin_prefix overlaps an existing service path")
    return prefix


ADMIN_SUFFIXES = {
    "/proxy_mock": "",
    "/configure_mock": "/mocks",
    "/storage": "/mocks",
    "/traffic": "/traffic",
    "/traffic/settings": "/settings",
    "/storage/snapshot": "/snapshot",
}


def service_endpoint(endpoint: str, prefix: str | None) -> str:
    # Removed operations keep their legacy path and semantics throughout 2.x.
    if prefix is not None and endpoint in ADMIN_SUFFIXES:
        return prefix + ADMIN_SUFFIXES[endpoint]
    return endpoint
