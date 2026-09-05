"""Marking of endpoints that 3.0 removes.

A deprecated endpoint keeps working unchanged; it only gains the RFC 8594 ``Deprecation``
header, a ``Link`` to its replacement and a one-off warning in the log, so that the removal in
3.0 does not come as a surprise.
"""

from fastapi import Response

from proxy_mock.core.logging import app_logger

REMOVED_IN = "3.0"

_warned: set[str] = set()


def mark_deprecated(response: Response, endpoint: str, replacement: str | None = None) -> Response:
    response.headers["Deprecation"] = "true"
    if replacement:
        response.headers["Link"] = f'<{replacement}>; rel="successor-version"'

    if endpoint not in _warned:
        _warned.add(endpoint)
        successor = f"; use {replacement} instead" if replacement else ""
        app_logger.warning(f"{endpoint} is deprecated and will be removed in {REMOVED_IN}{successor}")

    return response


def warn_deprecated_field(field: str, detail: str) -> None:
    """Warn once per process about a deprecated field in the configuration payload."""
    if field in _warned:
        return

    _warned.add(field)
    app_logger.warning(f"Field '{field}' is deprecated and will be removed in {REMOVED_IN}: {detail}")
