# 🛡️ Proxy Mock

**Proxy Mock** is a tool that combines a proxy server and a mock server.
It suits automated tests, integration scenarios and local debugging of service-to-service calls.

---

## 📋 Features

- **Request proxying** to an upstream host (`proxy_host`)
- **Endpoint mocking** with flexible response configuration
- **Rules** for returning different responses on the same path
- **Response delay** (`timeout`) and **caching** (`cache_time`)
- **Traffic capture** of incoming requests for later inspection
- **Bounded in-memory traffic storage** (the last 1000 records by default)

---

## ⚠️ Security

The tool is meant for a **trusted, isolated test environment** and is not designed to be exposed publicly. Before deploying it, keep in mind:

- **No authentication.** The service endpoints (`/configure_mock`, `/storage*`, `/traffic*`, `/cache/clean`) are open to anyone with network access. Anybody can create, read and delete mocks and traffic.
- **SSRF via `proxy_host`.** By default a request can be proxied to **any** host, including your internal network and the cloud metadata address (`169.254.169.254`). The host list can be restricted with `PROXY_MOCK_ALLOWED_PROXY_HOSTS` (disabled by default, meaning any host is allowed).
- **Traffic holds sensitive data.** `/traffic` stores the full headers and bodies of incoming requests (including `Authorization` and `Cookie`), and they can be read without authorisation. Requests that matched no mock (the `404` responses) are recorded as well.
- **Loop protection.** Proxying "to self" is detected through the `x-proxy-mock-chain` marker header and is aborted with `508 Loop Detected`.

**Recommendation:** run it inside a closed network perimeter only, never expose it to the internet, and narrow proxying with the allowlist where possible.

---

## ⬆️ Migrating from 1.0.1

The previously published 1.0.1 ran on Flask. The current 2.10.1 runs on FastAPI, and four
changes break compatibility. What to fix in a project upgrading from 1.0.1:

| In 1.0.1 | In 2.10.1 |
|---|---|
| `GET /status` | `GET /proxy_mock` — no alias, the old path returns `404` |
| `get_status()` | `get_proxy_mock()` — no alias |
| `POST /configure_mock/binary` | `POST /configure_mock` with `Content-Type: application/octet-stream` |
| `configure_binary_mock()` | `configure_mock()` — it serialises the body to msgpack itself |

Error messages are now in English: a missing mock returns `{"error": "No mock found for /<path>"}`
instead of the previous Russian text. Code that matches on the message text needs updating.

Everything else stays compatible: `POST /configure_mock`, `GET /storage`, `POST /storage/clean`,
`GET /traffic`, `POST /traffic/clean` and the methods `configure_mock()`, `get_traffic()`,
`get_storage()`, `clean_storage()`, `clean_traffic()` work as before. `get_traffic()` gained
optional filters (`path`, `method`, `limit`), and calling it without arguments is unchanged.

Environment requirements changed too: Python >= 3.11 instead of 3.9, and uvicorn instead of
gunicorn. The full history is in [CHANGELOG.md](CHANGELOG.md).

---

## 🚀 Getting started

There are three ways to run proxy-mock:

- **As a pip package** (simplest for automated tests, no Docker) — see "Running without Docker" below.
- **In Docker** — see "Running in Docker" below.
- **From source** (for working on proxy-mock itself) — see below.

### 📦 Prerequisites (for running from source)

Make sure the following are installed:

- **Python** >= 3.11 (development happens on 3.14)
- **uv** >= 0.9

### ⚙️ Install and run from source

1. **Install dependencies**

    Create a virtual environment and install everything, including the dev group:
    ```bash
    uv sync
    ```

2. **Activate the virtual environment**

    Activate the generated `.venv` (or prefix commands with `uv run`):
    ```bash
    source .venv/bin/activate
    ```

3. **Run the service**

    Use the Makefile:
    ```bash
    make run
    ```

### 🐳 Running in Docker

1. **Build the image and start the service**

    ```bash
    make docker_run
    ```

2. **Reach the service**

    Once it is up, the service listens on:
    ```
    http://localhost:5000
    ```

### 🐍 Running without Docker (as a pip package)

Docker is not required for automated tests: proxy-mock is published as an ordinary Python package containing both the server and the clients.

```bash
pip install proxy_mock
uvicorn proxy_mock.any_catcher:app --host 0.0.0.0 --port 5000 --workers 1
```

You can also start it straight from your tests with a session-scoped pytest fixture (free port, automatic shutdown):

```python
import socket
import threading
import time

import pytest
import uvicorn

from proxy_mock.app import create_app
from proxy_mock.client import ProxyMock


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def proxy_mock_url():
    port = _free_port()
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("proxy-mock failed to start in time")
        time.sleep(0.05)

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def proxy_mock(proxy_mock_url):
    return ProxyMock(proxy_mock_url)
```

Using it in a test:

```python
def test_external_service(proxy_mock):
    proxy_mock.configure_mock(path="/external/api", body={"answer": 42})
    # ... point the application under test at proxy_mock_url and assert on its behaviour
    traffic = proxy_mock.get_traffic(path="/external/api")
    assert traffic["count"] == 1
```

**Requirements and limitations:**

- Python **>= 3.11** in the test environment; on older interpreters pip will not find an installable version.
- The package pulls server dependencies (`fastapi>=0.136`, `pydantic>=2.6`, `uvicorn`, `httpx2`). If your test project pins older versions, the resolver may conflict. In that case install proxy-mock into a separate environment (`uv tool install` / `pipx`) and run it as a subprocess.
- Under parallel runs (pytest-xdist) start one instance per worker: the mock and traffic stores are global to an instance.

### Free-threaded Python (optional)

The service also runs on a free-threaded build of the interpreter (3.14t). The official
`python` images on Docker Hub do not publish free-threaded variants, so the interpreter has to
be installed separately, for example with uv:

```bash
uv python install 3.14t
uv sync --python 3.14t
```

Uvicorn should be started with a single worker (`--workers 1`). To confirm the GIL is really
disabled:

```bash
python scripts/check_gil.py
```

### Environment variables

| Variable | Values | Description |
|----------|--------|-------------|
| `PROXY_MOCK_LOG_REQUESTS` | `full` (default), `minimal`, `off` | Logging level for incoming requests |
| `PROXY_MOCK_TRAFFIC_MAX` | integer > 0 (default `1000`) | Maximum number of records in the in-memory traffic store. Changeable at runtime via `POST /traffic/settings` |
| `PROXY_MOCK_PROXY_TIMEOUT` | float, seconds (default `30`) | Timeout for outgoing proxied requests |
| `PROXY_MOCK_ALLOWED_PROXY_HOSTS` | comma-separated host list (default: empty) | Allowlist of proxy targets. Empty means any host is allowed |
| `PROXY_MOCK_RECORD_UNKNOWN_TRAFFIC` | `true` (default), `false` (`1/0`, `yes/no`, `on/off`) | Whether to record requests that matched no mock (the `404` response). Toggleable at runtime via `POST /traffic/settings` |

---

# 📡 API

Full request and response schemas are available in the auto-generated documentation while the service is running:

- **Swagger UI** — `http://localhost:5000/docs`
- **ReDoc** — `http://localhost:5000/redoc`
- **OpenAPI JSON** — `http://localhost:5000/openapi.json`

A short reference and the key examples follow.

## Service endpoints

| Method | URL | Purpose | Success response |
|--------|-----|---------|------------------|
| `GET` | `/proxy_mock` | Server availability and an instance summary | `200` — `{"success": true, "version": "...", "python_version": "...", "mocks_count": N, "traffic_count": N, "traffic_max_items": N}` |
| `POST` | `/configure_mock` | Create a mock | `201` — `{"success": true, "path": "...", "data": {...}}` |
| `PATCH` | `/configure_mock` | Amend an existing mock (it must already exist) | `200` — same shape as POST |
| `GET` | `/storage` | List mocks. Query: `path` filters by path | `200` — `{"success": true, "data": {...}}` |
| `DELETE` | `/storage` | Delete mocks. Query: `path` for one mock; without `path` all of them | `200` — `{"success": true, "data": {...}}`; `404` if the given mock does not exist |
| `POST` | `/storage/clean` | Deprecated alias of `DELETE /storage` (same effect) | `200` — `{"success": true, "data": {...}}` |
| `GET` | `/traffic` | Show captured traffic. Query: `path`, `method`, `limit` | `200` — `{"success": true, "count": N, "data": [...]}` |
| `POST` | `/traffic/clean` | Clear the traffic store | `200` — `{"success": true, "data": []}` |
| `GET` | `/traffic/settings` | Current traffic recording settings | `200` — `{"success": true, "data": {"record_unknown_traffic": true, "max_items": 1000}}` |
| `POST` | `/traffic/settings` | Change traffic settings. Body: `{"record_unknown_traffic": bool}` and/or `{"max_items": int > 0}`; the update is partial | `200` — same shape as GET; `400` on malformed JSON, `422` on an invalid or empty body |
| `POST` | `/cache/clean` | Invalidate the entire cache | `200` — `{"success": true}` |
| `*` | `/<any path>` | Catch-all: returns a mock, proxies, or `404` | depends on the configuration (see below) |

**`/configure_mock` errors:**

- `400` — empty body or malformed JSON/msgpack: `{"success": false, "error": "..."}`
- `415` — unsupported `Content-Type` (`application/json` or `application/octet-stream` is required)
- `422` — the body failed validation (for example the required `path` is missing): `{"success": false, "error": [...]}`

## `/configure_mock` body

Content type: `application/json` or `application/octet-stream` (msgpack). The PATCH body is identical to POST.

| Field | Type | Description |
|-------|------|-------------|
| `path` (required) | `string` | Path the mock applies to |
| `methods` | `list[string]` | HTTP methods (all by default) |
| `mock_data.body` | `string \| dict \| list \| bytes \| null` | Response body |
| `mock_data.status_code` | `int` | Response code (default `200`) |
| `mock_data.headers` | `dict` | Response headers |
| `extra_info` | `dict` | Arbitrary metadata (ends up in traffic) |
| `proxy_host` | `string` (**absolute URL**) | Proxy the request to this host |
| `timeout` | `float` | Delay before responding, seconds |
| `cache_time` | `int` | Response cache lifetime, seconds |
| `rules` | `list[dict]` | Rules producing different responses on one path |

Each entry in `rules`:

- **`input_data`** — the match condition: `methods`, `body`, `headers`, `query`, `proxy_host` (absolute URL), `timeout`.
- **`output_data`** — the response: `body`, `status_code`, `headers`.
- **`extra_info`** — rule metadata (appears in traffic as `rule_extra_info`).
- **`priority`** — `int`, higher values are checked earlier (default `0`).

Rules are sorted by descending `priority`, then by insertion order; the first match wins.

#### Example

```json
{
    "path": "/test/endpoint",
    "mock_data": {
        "body": {"message": "Hello, World!"},
        "status_code": 200,
        "headers": {"Content-Type": "application/json"}
    },
    "extra_info": {"service": "example_service"},
    "timeout": 1.5,
    "cache_time": 600,
    "rules": [
        {
            "input_data": {
                "methods": ["POST", "PUT"],
                "body": {"message": "any data"},
                "headers": {"X-App-Version": "870"},
                "query": {"user": "1"}
            },
            "output_data": {
                "body": {"message": "other data"},
                "status_code": 201,
                "headers": {"X-Request-ID": "123456"}
            },
            "extra_info": {"rule_request_id": "Request-id"},
            "priority": 10
        }
    ]
}
```

## Catching requests on `/<path>`

For any path that has a mock configured, the server processes the request in this order:

1. Records the request in traffic.
2. Checks the method, otherwise `405 Method Not Allowed`.
3. Returns a cached response when `cache_time` is set and there is a cache hit.
4. When `proxy_host` is set, proxies to the upstream host and returns its response (proxying "to self" is aborted with `508`). If the host is unreachable or does not resolve — `502`; if it did not answer within `PROXY_MOCK_PROXY_TIMEOUT` — `504`. Failed responses are not cached.
5. Otherwise applies `timeout`, then `rules`, then the default `mock_data`.

If no mock is configured for the path, the response is `404` with the body `{"error": "No mock found for /<path>"}`. By default such a request is recorded in traffic too (with `extra_info.status_code = 404`). Recording unknown traffic can be turned off with `PROXY_MOCK_RECORD_UNKNOWN_TRAFFIC=false` or at runtime via `POST /traffic/settings`.

---

## 📄 License

[MIT](LICENSE)
