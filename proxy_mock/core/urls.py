"""URL parsing shared by mock validation and proxy target checks."""

from urllib.parse import urlsplit

import httpx2


def proxy_hostname(value: str) -> str | None:
    parsed = urlsplit(value)
    # Accessing the port validates malformed or out-of-range values, as yarl did.
    parsed.port
    host = parsed.hostname
    if not host:
        return None
    # Reuse the upstream transport's IDNA handling; the stdlib codec uses older IDNA 2003 rules.
    try:
        return httpx2.URL(host=host).host.lower()
    except httpx2.InvalidURL as error:
        raise ValueError(str(error)) from error
