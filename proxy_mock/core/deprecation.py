"""Deprecation notices for the 3.0 migration (RFC 9745)."""

from fastapi import Request, Response
from fastapi.routing import APIRoute

from proxy_mock.client.migration import ADMIN_SUFFIXES, MIGRATION_URL
from proxy_mock.core.logging import app_logger

REMOVED_IN = "3.0"
# Announcement date: 2026-09-17 UTC. No removal date is promised by a Sunset header.
DEPRECATION_DATE = "@1789603200"
_warned: set[str] = set()


def mark_deprecated(response: Response, endpoint: str, replacement: str | None = None) -> Response:
    response.headers["Deprecation"] = DEPRECATION_DATE
    links = [f'<{MIGRATION_URL}>; rel="deprecation"']
    if replacement:
        links.append(f'<{replacement}>; rel="successor-version"')
    existing = response.headers.get("Link")
    response.headers["Link"] = ", ".join(([existing] if existing else []) + links)
    if endpoint not in _warned:
        _warned.add(endpoint)
        successor = f"; replacement resource: {replacement}" if replacement else ""
        app_logger.warning(f"{endpoint} is deprecated and will be removed in {REMOVED_IN}{successor}; {MIGRATION_URL}")
    return response


class LegacyAdminRoute(APIRoute):
    """Mark only a matched legacy service operation, never a user mock at the same path."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def deprecated_handler(request: Request) -> Response:
            response = await handler(request)
            prefix = request.app.state.admin_prefix
            legacy_path = {"/storage/clean": "/storage", "/traffic/clean": "/traffic"}.get(self.path, self.path)
            suffix = ADMIN_SUFFIXES.get(legacy_path)
            replacement = prefix + suffix if prefix is not None and suffix is not None else None
            return mark_deprecated(response, f"{request.method} {self.path}", replacement)

        return deprecated_handler


def warn_deprecated_field(field: str, detail: str) -> None:
    """Warn once per process about a deprecated field in the configuration payload."""
    if field in _warned:
        return
    _warned.add(field)
    app_logger.warning(f"Field '{field}' is deprecated and will be removed in {REMOVED_IN}: {detail}; {MIGRATION_URL}")
