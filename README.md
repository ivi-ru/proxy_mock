# 🛡️ Proxy Mock

[![PyPI](https://img.shields.io/pypi/v/proxy_mock)](https://pypi.org/project/proxy_mock/)
[![Python](https://img.shields.io/pypi/pyversions/proxy_mock)](https://pypi.org/project/proxy_mock/)
[![CI](https://github.com/ivi-ru/proxy_mock/actions/workflows/ci.yml/badge.svg)](https://github.com/ivi-ru/proxy_mock/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Proxy Mock** is a tool that combines a proxy server and a mock server.
It suits automated tests, integration scenarios and local debugging of service-to-service calls.

[Migration to 3.0](MIGRATING.md) · [Roadmap](ROADMAP.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Security policy](SECURITY.md)

> **3.0 development, not a release:** this checkout implements the new administrative REST API.
> Its package version remains `2.13.0` until release preparation is complete. The HTTP reference
> below describes this checkout; published 2.13 retains the legacy API and opt-in aliases.
> Pin `proxy_mock>=2.13,<3` for the published compatible release. See
> [Migrating from 2.x to 3.0](MIGRATING.md) for the HTTP changes and work still planned.

## Quick start

With Python 3.11 or newer, install the published 2.x package and test dependencies in a virtual
environment. The Python example also works with this development checkout:

```bash
python -m pip install 'proxy_mock>=2.13,<3' pytest requests
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
The [Docker Compose example](examples/compose/README.md) shows an application in a separate
container calling a mocked inventory service and verifies the captured request.
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
- **Response caching** (`cache_time`) — deprecated; still present during development, with removal planned for 3.0

---

## ⚠️ Security

The tool is meant for a **trusted, isolated test environment** and is not designed to be exposed publicly. Before deploying it, keep in mind:

- **No authentication.** The administrative endpoints under `/__admin` (or the configured prefix) are open to anyone with network access. Anybody can create, read and delete mocks and traffic.
- **SSRF via `proxy_host`.** By default a request can be proxied to **any** host, including your internal network and the cloud metadata address (`169.254.169.254`). The host list can be restricted with `PROXY_MOCK_ALLOWED_PROXY_HOSTS` (disabled by default, meaning any host is allowed).
- **Traffic holds sensitive data.** `/__admin/traffic` stores the full headers and bodies of incoming requests (including `Authorization` and `Cookie`), and they can be read without authorisation. Requests that matched no mock (the `404` responses) are recorded as well.
- **Loop protection.** Proxying "to self" is detected through the `x-proxy-mock-chain` marker header and is aborted with `508 Loop Detected`.

**Recommendation:** run it inside a closed network perimeter only, never expose it to the internet, and narrow proxying with the allowlist where possible.

---

## ⬆️ Historical migration from 1.0.1 to 2.x

This section describes the released 2.x API. For this checkout, also apply
[the 3.0 HTTP migration](MIGRATING.md#administrative-rest-api-in-this-checkout).

The previously published 1.0.1 ran on Flask. The 2.x line runs on FastAPI, and four
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

The [Docker Compose example](examples/compose/README.md) includes a complete local build and
an application calling its mock from another container.

Every release is published to GHCR. The package currently requires registry access because
public visibility is disabled by the organization. If you have access, no local build is needed:

```bash
docker run --rm -p 5000:5000 ghcr.io/ivi-ru/proxy_mock:latest
```

To start from a prepared snapshot, mount it and pass `--mocks`:

```bash
docker run --rm -p 5000:5000 -v "$PWD/mocks.json:/mocks.json" \
    ghcr.io/ivi-ru/proxy_mock:latest \
    python -m proxy_mock --host=0.0.0.0 --port=5000 --mocks /mocks.json
```

To build from a public checkout without GHCR access:

```bash
docker build -t proxy-mock .
docker run --rm -p 127.0.0.1:5000:5000 proxy-mock
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

The whole storage can be exported as one JSON document, kept next to the tests, and loaded back.
The HTTP example below targets this development checkout:

```bash
curl http://localhost:5000/__admin/snapshot > mocks.json  # export from this checkout
proxy-mock --port 5000 --mocks mocks.json                 # start with them preloaded
```

The same from Python:

```python
snapshot = proxy_mock.export_mocks()
proxy_mock.import_mocks(snapshot)  # merge into what is already configured
proxy_mock.import_mocks(snapshot, mode="replace")  # or replace the storage
```

For HTTP import, use `PUT /__admin/snapshot` to replace storage or `PATCH /__admin/snapshot`
to merge mocks by their path. Merge replaces each included mock in full and leaves other paths
untouched; it is not JSON Merge Patch. Both accept the exported document. Invalid snapshots
are rejected before storage changes.

The document still uses format 1 in this development step:

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
| `PROXY_MOCK_ADMIN_PREFIX` | absolute path, default `/__admin` | Administrative namespace, including docs and OpenAPI. Legacy routes are removed in this checkout. The prefix cannot be empty. See [migration guide](MIGRATING.md) |
| `PROXY_MOCK_LOG_REQUESTS` | `full` (default), `minimal`, `off` | Logging level for incoming requests |
| `PROXY_MOCK_TRAFFIC_MAX` | integer > 0 (default `1000`) | Maximum number of records in the in-memory traffic store. Changeable at runtime via `PATCH /__admin/settings` |
| `PROXY_MOCK_PROXY_TIMEOUT` | float, seconds (default `30`) | Timeout for outgoing proxied requests |
| `PROXY_MOCK_ALLOWED_PROXY_HOSTS` | comma-separated host list (default: empty) | Allowlist of proxy targets. Empty means any host is allowed |
| `PROXY_MOCK_RECORD_UNKNOWN_TRAFFIC` | `true` (default), `false` (`1/0`, `yes/no`, `on/off`) | Whether to record requests that matched no mock (the `404` response). Toggleable at runtime via `PATCH /__admin/settings` |
| `PROXY_MOCK_URL` | URL (default: empty) | Read by the pytest fixtures: when set, they use that instance instead of starting one |

---

# 📡 API

Full request and response schemas are available in the auto-generated documentation while the service is running:

- **Swagger UI** — `http://localhost:5000/__admin/docs`
- **ReDoc** — `http://localhost:5000/__admin/redoc`
- **OpenAPI JSON** — `http://localhost:5000/__admin/openapi.json`

A short reference and the key examples follow.

## Administrative REST resources

These routes describe the unreleased checkout. Replace `/__admin` with
`PROXY_MOCK_ADMIN_PREFIX` when configured. The entire namespace is reserved: user mocks cannot
shadow administrative routes, documentation, or unknown paths inside it. Former service paths
such as `/storage`, `/configure_mock` and `/docs` can now be used by ordinary mocks.

| Method | Resource URI | Purpose | Success status |
|--------|--------------|---------|----------------|
| `GET` | `/__admin` | Server availability and instance summary | `200` |
| `GET` | `/__admin/mocks` | List all mocks | `200` |
| `DELETE` | `/__admin/mocks` | Delete all mocks | `200` |
| `GET` | `/__admin/mocks?path=%2Finventory` | Read one mock | `200` |
| `PUT` | `/__admin/mocks?path=%2Finventory` | Create or fully replace one mock | `201` when created; `200` when replaced |
| `PATCH` | `/__admin/mocks?path=%2Finventory` | Partially update an existing mock | `200` |
| `DELETE` | `/__admin/mocks?path=%2Finventory` | Delete one mock | `200` |
| `GET` | `/__admin/traffic` | Read traffic; optional `path`, `method`, `limit` filters | `200` |
| `DELETE` | `/__admin/traffic` | Clear all traffic; no query parameters | `200` |
| `GET` | `/__admin/settings` | Read traffic recording settings | `200` |
| `PATCH` | `/__admin/settings` | Partially update `record_unknown_traffic` and/or `max_items` | `200` |
| `GET` | `/__admin/snapshot` | Export the format 1 snapshot document | `200` |
| `PUT` | `/__admin/snapshot` | Replace all mocks from a snapshot | `200` |
| `PATCH` | `/__admin/snapshot` | Merge a snapshot by mock path | `200` |
| `DELETE` | `/__admin/cache` | Clear the deprecated response cache, pending its removal | `200` |

The query is part of a resource URI: `/__admin/mocks?path=%2Finventory` identifies the mock whose
request path is `/inventory`. URL-encode the path rather than inserting it into administrative
path segments. `PUT` is idempotent and replaces the whole configuration; omitted properties
return to defaults. `PATCH` preserves omitted properties. Neither operation uses `POST`.
An absent query selects the collection for `GET` and `DELETE`; an empty `path` is invalid.
`PUT` and `PATCH` require `path` in the query. A body `path`, if present, must match it.

Success responses retain the `success` envelope and operation-specific data, except snapshot
export, which returns the snapshot document itself. Administrative errors share one shape:

```json
{"success": false, "error": {"code": "mock_not_found", "message": "No mock found for /inventory"}}
```

The message is descriptive; error responses may also include `error.details`. Missing mocks
return `404` for item `GET`, `PATCH` and `DELETE`. Invalid fields, empty paths and invalid
traffic filters return `422`; malformed request bodies return `400`; unsupported body media
types return `415`. An unsupported administrative method returns `405`. Legacy service routes
and action-style `POST` aliases are no longer administrative operations.

## Mock representation and partial updates

Use `application/json` or `application/octet-stream` (msgpack) for mock `PUT` and `PATCH`.
`PUT` supplies the complete representation. `PATCH` merges supplied `mock_data` properties
with the current response; response bodies themselves are replaced, not recursively patched.
Explicit `null` clears nullable fields such as `proxy_host` and `mock_data.body`. Arrays are
replaced in full: `{"rules": []}` removes all rules. Null is invalid for non-nullable fields.

| Field | Type | Description |
|-------|------|-------------|
| `path` (optional) | `string` | Must match the required `path` query parameter |
| `methods` | `list[string]` | HTTP methods (all by default) |
| `mock_data.body` | `string \| dict \| list \| bytes \| null` | Response body |
| `mock_data.status_code` | `int` | Response code (default `200`) |
| `mock_data.headers` | `dict` | Response headers |
| `extra_info` | `dict` | Arbitrary metadata (ends up in traffic) |
| `proxy_host` | `string` (**absolute URL**) | Proxy the request to this host |
| `timeout` | `float` | Delay before responding, seconds |
| `cache_time` | `int` | Deprecated response cache lifetime, seconds; removal remains planned |
| `rules` | `list[dict]` | Rules producing different responses on one path |

For example, create a mock and then change only its status code:

```sh
curl -X PUT 'http://localhost:5000/__admin/mocks?path=%2Finventory' \
  -H 'Content-Type: application/json' \
  -d '{"mock_data":{"body":{"available":3},"status_code":200}}'
curl -X PATCH 'http://localhost:5000/__admin/mocks?path=%2Finventory' \
  -H 'Content-Type: application/json' \
  -d '{"mock_data":{"status_code":503}}'
```

The second request keeps the existing body and headers. See
[the migration guide](MIGRATING.md#administrative-rest-api-in-this-checkout) for additional
before/after examples.

Each entry in `rules`:

- **`input_data`** — the match condition: `methods`, `body`, `headers`, `query`, `proxy_host` (absolute URL), `timeout`.
- **`output_data`** — the response: `body`, `status_code`, `headers`.
- **`extra_info`** — rule metadata (appears in traffic as `rule_extra_info`).
- **`priority`** — `int`, higher values are checked earlier (default `0`).

Rules are sorted by descending `priority`, then by insertion order; the first match wins.

#### Full representation example

Send this representation to `PUT /__admin/mocks?path=%2Ftest%2Fendpoint`.

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

If no mock is configured for the path, the response is `404` with the body `{"error": "No mock found for /<path>"}`. By default such a request is recorded in traffic too (with `extra_info.status_code = 404`). Recording unknown traffic can be turned off with `PROXY_MOCK_RECORD_UNKNOWN_TRAFFIC=false` or at runtime via `PATCH /__admin/settings`.

---

## 📄 License

[MIT](LICENSE)
