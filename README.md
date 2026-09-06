# 🛡️ Proxy Mock

[![PyPI](https://img.shields.io/pypi/v/proxy_mock)](https://pypi.org/project/proxy_mock/)
[![Python](https://img.shields.io/pypi/pyversions/proxy_mock)](https://pypi.org/project/proxy_mock/)
[![CI](https://github.com/ivi-ru/proxy_mock/actions/workflows/ci.yml/badge.svg)](https://github.com/ivi-ru/proxy_mock/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Proxy Mock** is a tool that combines a proxy server and a mock server.
It suits automated tests, integration scenarios and local debugging of service-to-service calls.

[Roadmap](ROADMAP.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Security policy](SECURITY.md)

## Quick start

With Python 3.11 or newer, install the package and test dependencies in a virtual environment:

```bash
python -m pip install 'proxy_mock>=2.11,<3' pytest requests
```

Save this complete test as `test_http_dependency.py`:

```python
import requests


def test_http_dependency(proxy_mock, proxy_mock_url):
    proxy_mock.configure_mock(path="/inventory/sku-42", methods=["GET"], body={"available": 3})

    response = requests.get(f"{proxy_mock_url}/inventory/sku-42", timeout=5)

    assert response.status_code == 200
    assert response.json() == {"available": 3}
    traffic = proxy_mock.get_traffic(path="/inventory/sku-42", method="GET")
    assert traffic["count"] == 1
    assert traffic["data"][0]["request_path"] == "/inventory/sku-42"
```

Run it:

```bash
python -m pytest -q test_http_dependency.py
```

Expected result: **1 passed**. The fixtures start a server on a free loopback port, reset its
state after the test, and shut it down at the end of the session. No separate server is needed.

The [runnable examples](examples/README.md) include this test and a JSON snapshot round trip.
To use the tool outside pytest, start the standalone server with `proxy-mock --port 5000`.

---

## 📋 Features

- **Request proxying** to an upstream host (`proxy_host`)
- **Endpoint mocking** with flexible response configuration
- **Rules** for returning different responses on the same path
- **Response delay** (`timeout`)
- **Traffic capture** of incoming requests for later inspection
- **Bounded in-memory traffic storage** (the last 1000 records by default)
- **JSON snapshots** of the whole storage: export, load back, or preload at startup
- **One command to start** (`proxy-mock`) and **pytest fixtures** that ship with the package
- **Response caching** (`cache_time`) — deprecated, removed in 3.0

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

The previously published 1.0.1 ran on Flask. The current 2.x line runs on FastAPI, and four
changes break compatibility. What to fix in a project upgrading from 1.0.1:

| In 1.0.1 | In 2.x |
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

The shortest path is one command, with nothing installed permanently:

```bash
uvx proxy-mock --port 5000          # with uv
pipx run proxy-mock --port 5000     # with pipx
```

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

Every release is published to GHCR, so nothing has to be built:

```bash
docker run --rm -p 5000:5000 ghcr.io/ivi-ru/proxy_mock:latest
```

To start from a prepared snapshot, mount it and pass `--mocks`:

```bash
docker run --rm -p 5000:5000 -v "$PWD/mocks.json:/mocks.json" \
    ghcr.io/ivi-ru/proxy_mock:latest \
    python -m proxy_mock --host=0.0.0.0 --port=5000 --mocks /mocks.json
```

To build the image from the working tree instead:

```bash
make docker_run
```

Once it is up, the service listens on `http://localhost:5000`.

### 🐍 Running without Docker (as a pip package)

Docker is not required for automated tests: proxy-mock is published as an ordinary Python package containing the server, both clients and a pytest plugin.

```bash
pip install proxy_mock
proxy-mock --port 5000
```

`proxy-mock --help` lists the options; the ones that matter are `--host`, `--port`, `--log-level`
and `--mocks`. The same entry point is available as `python -m proxy_mock`.

Only a single worker is supported — mocks and captured traffic live in the memory of one
process, so a second worker would answer from an empty storage. `--workers 2` is refused with
that explanation rather than starting a service that lies every other call.

#### Fixtures for pytest

The package registers a pytest plugin, so the fixtures are available as soon as it is installed
— no `conftest.py` boilerplate. The [quick start](#quick-start) is a complete test that configures
a response, makes an HTTP request, and verifies the captured traffic.

| Fixture | Scope | What it gives |
|---------|-------|---------------|
| `proxy_mock_url` | session | Base URL of a running instance. Starts a server on a free port and shuts it down at the end of the session |
| `proxy_mock` | function | A `ProxyMock` client bound to that URL. Mocks and traffic are reset after every test |

To run the tests against an instance that is already up (in docker compose, for example), set
`PROXY_MOCK_URL` — the fixture then uses it and starts nothing:

```bash
PROXY_MOCK_URL=http://localhost:5000 pytest
```

To keep mocks across several tests, build a client of your own from `proxy_mock_url` instead of
using the `proxy_mock` fixture, which resets state between tests.

#### Snapshots of the storage

The whole storage can be exported as one JSON document, kept next to the tests, and loaded back:

```bash
curl http://localhost:5000/storage/snapshot > mocks.json   # export
proxy-mock --port 5000 --mocks mocks.json                  # start with them preloaded
```

The same from Python:

```python
snapshot = proxy_mock.export_mocks()
proxy_mock.import_mocks(snapshot)  # merge into what is already configured
proxy_mock.import_mocks(snapshot, mode="replace")  # or replace the storage
```

The document carries its own format version, so snapshots stay readable across releases:

```json
{
  "format": 1,
  "protocol": "http",
  "generated_by": "proxy_mock 2.11.0",
  "mocks": [{"path": "/external/api", "mock_data": {"body": {"answer": 42}, "status_code": 200}}]
}
```

Binary bodies cannot be written as JSON, so they travel base64-encoded in `body_b64` instead of
`body`, and are restored as bytes on import.

**Requirements and limitations:**

- Python **>= 3.11** in the test environment; on older interpreters pip will not find an installable version.
- The package pulls server dependencies (`fastapi>=0.137`, `pydantic>=2.6`, `uvicorn`, `httpx2`). If your test project pins older versions, the resolver may conflict. In that case install proxy-mock into a separate environment (`uv tool install` / `pipx`) and run it as a subprocess.
- Under parallel runs (pytest-xdist) every worker starts its own instance: the mock and traffic stores belong to a process.

### Environment variables

| Variable | Values | Description |
|----------|--------|-------------|
| `PROXY_MOCK_LOG_REQUESTS` | `full` (default), `minimal`, `off` | Logging level for incoming requests |
| `PROXY_MOCK_TRAFFIC_MAX` | integer > 0 (default `1000`) | Maximum number of records in the in-memory traffic store. Changeable at runtime via `PATCH /traffic/settings` |
| `PROXY_MOCK_PROXY_TIMEOUT` | float, seconds (default `30`) | Timeout for outgoing proxied requests |
| `PROXY_MOCK_ALLOWED_PROXY_HOSTS` | comma-separated host list (default: empty) | Allowlist of proxy targets. Empty means any host is allowed |
| `PROXY_MOCK_RECORD_UNKNOWN_TRAFFIC` | `true` (default), `false` (`1/0`, `yes/no`, `on/off`) | Whether to record requests that matched no mock (the `404` response). Toggleable at runtime via `PATCH /traffic/settings` |
| `PROXY_MOCK_URL` | URL (default: empty) | Read by the pytest fixtures: when set, they use that instance instead of starting one |

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
| `GET` | `/storage/snapshot` | Export every mock as a snapshot document | `200` — the snapshot itself (see "Snapshots of the storage") |
| `POST` | `/storage/snapshot` | Load a snapshot. Query: `mode=merge` (default) or `mode=replace` | `200` — `{"success": true, "data": {"imported": N, "mode": "...", "paths": [...]}}`; `400` on malformed JSON or an unknown mode, `422` on an invalid snapshot |
| `GET` | `/traffic` | Show captured traffic. Query: `path`, `method`, `limit` | `200` — `{"success": true, "count": N, "data": [...]}` |
| `DELETE` | `/traffic` | Clear the traffic store | `200` — `{"success": true, "data": []}` |
| `GET` | `/traffic/settings` | Current traffic recording settings | `200` — `{"success": true, "data": {"record_unknown_traffic": true, "max_items": 1000}}` |
| `PATCH` | `/traffic/settings` | Change traffic settings. Body: `{"record_unknown_traffic": bool}` and/or `{"max_items": int > 0}`; the update is partial | `200` — same shape as GET; `400` on malformed JSON, `422` on an invalid or empty body |

**Deprecated, removed in 3.0.** They still work and answer exactly as before, but send a
`Deprecation: true` response header and a `Link` to the replacement:

| Method | URL | Replacement |
|--------|-----|-------------|
| `POST` | `/storage/clean` | `DELETE /storage` |
| `POST` | `/traffic/clean` | `DELETE /traffic` |
| `POST` | `/traffic/settings` | `PATCH /traffic/settings` |
| `POST` | `/cache/clean` | none — response caching goes away with it |
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
| `cache_time` | `int` | Response cache lifetime, seconds. **Deprecated**, removed in 3.0 |
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

If no mock is configured for the path, the response is `404` with the body `{"error": "No mock found for /<path>"}`. By default such a request is recorded in traffic too (with `extra_info.status_code = 404`). Recording unknown traffic can be turned off with `PROXY_MOCK_RECORD_UNKNOWN_TRAFFIC=false` or at runtime via `PATCH /traffic/settings`.

---

## 📄 License

[MIT](LICENSE)
