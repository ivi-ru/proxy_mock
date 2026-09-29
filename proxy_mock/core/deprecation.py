"""Warnings for features retained until their planned 3.0 removal."""

from proxy_mock.client.migration import MIGRATION_URL
from proxy_mock.core.logging import app_logger

REMOVED_IN = "3.0"
_warned: set[str] = set()


def warn_deprecated_field(field: str, detail: str) -> None:
    """Warn once per process about a deprecated field in the configuration payload."""
    if field in _warned:
        return
    _warned.add(field)
    app_logger.warning(f"Field '{field}' is deprecated and will be removed in {REMOVED_IN}: {detail}; {MIGRATION_URL}")
