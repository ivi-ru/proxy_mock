import os
from uuid import uuid4

import httpx2
from fastapi import Request
from yarl import URL

# Unique process id. Regenerated on every start, so markers left by previous
# instances cannot cause false positives.
INSTANCE_ID = uuid4().hex

# Chain header listing the instances a request has already passed through.
# Guards against proxying to self (and against loops spanning several instances).
PROXY_CHAIN_HEADER = "x-proxy-mock-chain"

PROXY_BAD_GATEWAY = 502
PROXY_GATEWAY_TIMEOUT = 504


class ProxyRequestError(Exception):
    """Upstream host is unreachable, does not resolve or did not answer in time.

    Without it the httpx2 exception bubbled up to uvicorn: the client got an empty `500`
    and the logs got a traceback instead of a meaningful response.
    """

    def __init__(self, proxy_host: str, error: Exception):
        self.proxy_host = proxy_host
        self.error = error
        # A timeout maps to 504, everything else (DNS, refused connection, broken protocol) to 502.
        self.code = PROXY_GATEWAY_TIMEOUT if isinstance(error, httpx2.TimeoutException) else PROXY_BAD_GATEWAY
        self.detail = f"Failed to proxy the request to {proxy_host}: {type(error).__name__}: {error}"
        super().__init__(self.detail)


def _parse_chain(raw: str) -> list[str]:
    return [item for item in raw.split(",") if item]


def is_proxy_loop(request: Request) -> bool:
    """We already proxied this request and it came back to us, so this is a loop."""
    chain = _parse_chain(request.headers.get(PROXY_CHAIN_HEADER, ""))
    return INSTANCE_ID in chain


def get_allowed_proxy_hosts() -> set[str] | None:
    """Hosts allowed as proxy targets.

    The list comes from the PROXY_MOCK_ALLOWED_PROXY_HOSTS env variable (comma-separated).
    When the variable is unset we return None: any host is allowed, which is the default
    kept for backward compatibility.
    """
    raw = os.getenv("PROXY_MOCK_ALLOWED_PROXY_HOSTS", "").strip()
    if not raw:
        return None
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def is_proxy_host_allowed(proxy_host: str) -> bool:
    allowed = get_allowed_proxy_hosts()
    if allowed is None:
        return True
    host = (URL(proxy_host).host or "").lower()
    return host in allowed


def make_proxy_request_url(request_url: str, proxy_host: str) -> str:
    req_url = URL(request_url)
    proxy_url = URL(proxy_host).with_path(req_url.path).with_query(req_url.query)
    return proxy_url.human_repr()


def filter_proxy_response_headers(headers: httpx2.Headers) -> dict:
    excluded = {"content-encoding", "content-length", "transfer-encoding"}
    return {k: v for k, v in headers.items() if k.lower() not in excluded}


def filter_proxy_request_headers(headers: httpx2.Headers) -> dict:
    excluded = {"host", "content-length", "transfer-encoding", "connection"}
    return {k: v for k, v in headers.items() if k.lower() not in excluded}


async def proxy_request_to_host(
    request_data: Request,
    proxy_host: str,
    http_client: httpx2.AsyncClient,
) -> httpx2.Response:
    request_url = make_proxy_request_url(str(request_data.url), proxy_host)

    headers = filter_proxy_request_headers(request_data.headers)
    # Append ourselves to the instance chain so an incoming loop can be detected.
    chain = _parse_chain(request_data.headers.get(PROXY_CHAIN_HEADER, "")) + [INSTANCE_ID]
    headers[PROXY_CHAIN_HEADER] = ",".join(chain)

    try:
        return await http_client.request(
            method=request_data.method,
            url=request_url,
            content=await request_data.body(),
            headers=headers,
            follow_redirects=False,
        )
    except (httpx2.RequestError, httpx2.InvalidURL) as err:
        raise ProxyRequestError(proxy_host, err) from err
