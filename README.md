# 🛡️ Proxy Mock

[![PyPI](https://img.shields.io/pypi/v/proxy_mock)](https://pypi.org/project/proxy_mock/)
[![Python](https://img.shields.io/pypi/pyversions/proxy_mock)](https://pypi.org/project/proxy_mock/)
[![CI](https://github.com/ivi-ru/proxy_mock/actions/workflows/ci.yml/badge.svg)](https://github.com/ivi-ru/proxy_mock/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Proxy Mock** is a tool that combines a proxy server and a mock server.
It suits automated tests, integration scenarios and local debugging of service-to-service calls.

[Migration to 3.0](MIGRATING.md) · [Roadmap](ROADMAP.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Security policy](SECURITY.md)

> **3.0 development, not a release:** this checkout implements the administrative REST API,
> response sequences, record/replay, unified Python clients using `httpx2`, and the `server` extra.
> Its package version is `3.0.0`; publication is still a separate maintainer action. The HTTP
> reference below describes this checkout; published 2.13 retains the legacy API and opt-in aliases.
> Pin `proxy_mock>=2.13,<3` for the published compatible release. See
> [Migrating from 2.x to 3.0](MIGRATING.md) for the HTTP changes and work still planned.

## Quick start

With Python 3.11 or newer, install this development checkout and pytest in a virtual
environment from the repository root:

```bash
python -m pip install '.[server]' pytest
```

Save this complete test as `test_http_dependency.py`:

```python
import httpx2


def test_http_dependency(proxy_mock, proxy_mock_url):
    proxy_mock.configure_mock(path="/inventory/sku-42", methods=["GET"], body={"available": 3})

    response = httpx2.get(f"{proxy_mock_url}/inventory/sku-42", timeout=5)

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

The [runnable examples](examples/README.md) include REST mock updates, sequence restart,
offline replay from a snapshot, and an async client alongside this quick start.
The [Docker Compose example](examples/compose/README.md) shows an application in a separate
container calling a mocked inventory service and verifies the captured request.
To use the tool outside pytest, start the standalone server with `proxy-mock --port 5000`.

---

## 📋 Features

- **Request proxying** to an upstream host (`proxy_host`)
- **Endpoint mocking** with flexible response configuration
- **Rules** for returning different responses on the same path
- **Record/replay** with inspectable upstream replies and exact request matching (unreleased 3.0)
- **Response sequences** for ordered replies on a mock or a matching rule (unreleased 3.0)
- **Response delay** (`timeout`)
- **Traffic capture** of incoming requests for later inspection
- **Bounded in-memory traffic storage** (the last 1000 records by default)
- **JSON snapshots** of the whole storage: export, load back, or preload at startup
- **One command to start** (`proxy-mock`) and **pytest fixtures** that ship with the package

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

The 3.0 server requires the `server` extra. When installing this checkout use
`pip install '.[server]'`; package-index commands below apply when 3.0 is released.
Published 2.x includes the server by default. The shortest path after release is one command,
with nothing installed permanently:

```bash
uvx --from 'proxy_mock[server]' proxy-mock --port 5000
pipx run --spec 'proxy_mock[server]' proxy-mock --port 5000
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
    uv sync --extra server
    ```

2. **Activate the virtual environment**

    Activate the generated `.venv` (or prefix commands with `uv run --extra server`):
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

Published releases have images on GHCR. Access may require registry credentials.
The `latest` image follows published releases and does not contain this unreleased 3.0 API.
For a released server, no local build is needed:

```bash
docker run --rm -p 5000:5000 ghcr.io/ivi-ru/proxy_mock:latest
```

To build this checkout without GHCR access:

```bash
docker build -t proxy-mock:local .
docker run --rm -p 127.0.0.1:5000:5000 proxy-mock:local
```

To preload a snapshot, replace the run command above with:

```bash
docker run --rm -p 127.0.0.1:5000:5000 -v "$PWD/mocks.json:/mocks.json" \
    proxy-mock:local \
    python -m proxy_mock --host=0.0.0.0 --port=5000 --mocks /mocks.json
```

A snapshot must match the server: published 2.x reads format 1; this checkout reads formats
1 and 2. A format 2 snapshot needs the locally built image while 3.0 remains unreleased.

Once it is up, the service listens on `http://localhost:5000`.

### 🐍 Running without Docker (as a pip package)

Docker is not required for automated tests. The 3.0 base install contains both clients and a
pytest plugin for external instances; the `server` extra supplies local server dependencies.
The wheel includes the server code in both cases.

```bash
pip install 'proxy_mock[server]'
proxy-mock --port 5000
```

`proxy-mock --help` lists the options; the ones that matter are `--host`, `--port`, `--log-level`
and `--mocks`. The same entry point is available as `python -m proxy_mock`.

Only a single worker is supported — mocks and captured traffic live in the memory of one
process, so a second worker would answer from an empty storage. `--workers 2` is refused with
that explanation rather than starting a service that lies every other call.

When embedding the server, each call to `proxy_mock.app:create_app()` creates an independent
application with empty mock and traffic storage. Its routes, recordings and sequence cursors
belong to that application; clearing or importing mocks in another application does not affect it.

#### Fixtures for pytest

The package registers a pytest plugin, so the fixtures are available as soon as it is installed
— no `conftest.py` boilerplate. Starting a local instance requires the `server` extra. A base
install is sufficient when `PROXY_MOCK_URL` points at an existing instance. The
[quick start](#quick-start) configures a response, makes an HTTP request, and verifies traffic.

| Fixture | Scope | What it gives |
|---------|-------|---------------|
| `proxy_mock_url` | session | Base URL of a running instance. Starts a server on a free port and shuts it down at the end of the session |
| `proxy_mock` | function | A `ProxyMock` client bound to that URL. Mocks and traffic are reset after every test |

To run the tests against an instance that is already up (in docker compose, for example), set
`PROXY_MOCK_URL` — the fixture then uses it and starts nothing. Use a dedicated test
instance because fixture teardown deletes all its mocks and traffic. For a custom administrative
prefix, set `PROXY_MOCK_ADMIN_PREFIX` in the test environment to match the server:

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

Export uses format 2. Import and `--mocks` accept formats 1 and 2. The format 2 document
includes sequence definitions and completed recordings alongside ordinary mock configuration:

```json
{
  "format": 2,
  "protocol": "http",
  "mocks": [{"path": "/external/api", "mock_data": {"body": {"answer": 42}, "status_code": 200}}]
}
```

The exported `generated_by` field reports the server version and is optional on import.
Binary bodies cannot be written as JSON, so they travel base64-encoded in `body_b64` instead of
`body`, and are restored as bytes on import.

Format 2 keeps `sequence` definitions on mocks and rules. A mock with `recording` configuration
also exports its `recordings` array, in oldest-write order. Each array entry has the same
`id`, `request` and `response` representation returned by `GET /__admin/recordings`. An omitted
array imports as empty. Export does not consume or reset sequences; import restarts cursors at
zero. Sequence runtime positions, traffic and requests in flight are excluded.
Mock configuration, including record/replay mode, is preserved. Global traffic settings are
excluded; import never contacts an upstream.

Before mutation, import validates every mock, binary body and recording. Entry ids must match
the exact recorded request; duplicate paths/ids, unknown format 2 fields, invalid headers or
bodies, and recording collections exceeding their configured count/byte budgets return `422`.
Imported data is never silently evicted to fit limits. Binary config sections use either
`body` or `body_b64`, never both. Recorded bodies always use canonical base64 strings, and
recorded header pairs preserve duplicates and Latin-1 octets. `HEAD` recordings may retain a
single numeric representation length; HEAD, 204 and 304 replies have empty bodies.

Snapshot merge replaces each supplied mock's configuration and recordings in full; omitted
mocks retain their runtime state. Replace removes omitted mocks and their runtime state.
Replaced mocks detach pending recordings so late responses cannot modify imported data.
The CLI validates the file before starting and restores the same data at startup.

Format 1 remains readable for static/proxy mocks and rules. Sequences and recordings require
format 2, and a format 1 document containing them is rejected. Published 2.x cannot read
format 2: do not relabel an exported format 2 document as format 1.

### Python client transport

In this 3.0 checkout, both `ProxyMock` and `AsyncProxyMock` return `httpx2.Response` from
`execute_request()`. Check `.is_success` or explicit status codes; responses are always
truthy. Use `content=` for raw bodies, `data=` for form mappings, and `follow_redirects=`
for redirect handling. Wrapper-created clients do not follow redirects by default and use
10-second timeouts for each network operation; `timeout=None` disables them.

Pass `http_client=httpx2.Client(...)` or `httpx2.AsyncClient(...)` for custom headers,
cookies, TLS, proxies or transports. The wrapper closes native clients it creates and leaves
injected clients open. `.http_client` exposes the native client. For exception handling,
per-request options and executable migration examples, see the
[transport contract](MIGRATING.md#python-client-transport-in-this-checkout).
Published 2.x keeps the previous synchronous response type and redirect behavior.

**Requirements and limitations:**

- Python **>= 3.11** in the test environment; on older interpreters pip will not find an installable version.
- The base install depends on `httpx2` and `msgpack`. Only `proxy_mock[server]` adds
  `fastapi>=0.137`, `pydantic>=2.6` and `uvicorn>=0.27`; their bounds are unchanged.
  If they conflict with your application, run the server in a separate environment and use
  the base install with `PROXY_MOCK_URL` in the test environment.
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
| `GET` | `/__admin/snapshot` | Export the format 2 snapshot document | `200` |
| `PUT` | `/__admin/snapshot` | Replace all mocks from a snapshot | `200` |
| `PATCH` | `/__admin/snapshot` | Merge a snapshot by mock path | `200` |
| `GET` | `/__admin/recordings?path=%2Finventory` | Inspect recorded replies; optional `id` selects one entry | `200` |
| `DELETE` | `/__admin/recordings?path=%2Finventory` | Delete that collection or one entry selected by `id` | `200` |
| `GET` | `/__admin/sequence-state?path=%2Finventory` | Inspect a sequence cursor; optional zero-based `rule` index | `200` |
| `PATCH` | `/__admin/sequence-state?path=%2Finventory` | Restart that sequence with `{"position": 0}` | `200` |

The query is part of a resource URI: `/__admin/mocks?path=%2Finventory` identifies the mock whose
request path is `/inventory`. URL-encode the path rather than inserting it into administrative
path segments. `PUT` is idempotent and replaces the whole configuration; omitted properties
return to defaults. Its `Location` header identifies the mock resource URI. `PATCH` preserves omitted properties. Neither operation uses `POST`.
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
types return `415`. An unsupported administrative method on a known resource returns `405`. Legacy service routes
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
| `sequence` | `object \| null` | Ordered response definition; see below |
| `recording` | `object \| null` | Explicit record/replay configuration; see below |
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

Rules are sorted by descending `priority`; equal priorities retain submitted list order unless
explicit `timestamp` values change it. The first match wins.

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

## Response sequences

Available in this unreleased checkout. The
[runnable sequence example](examples/test_v3_workflows.py) covers exhaustion, restart and
snapshot restoration. Set `sequence` on a mock or on an individual rule:

```python
proxy_mock.configure_mock(
    path="/inventory",
    sequence={
        "responses": [
            {"status_code": 503, "body": {"retry": True}},
            {"status_code": 200, "body": {"available": 3}},
        ],
        "on_exhaustion": "repeat_last",
    },
)
assert proxy_mock.execute_request("GET", "/inventory").status_code == 503
assert proxy_mock.execute_request("GET", "/inventory").status_code == 200
assert proxy_mock.execute_request("GET", "/inventory").status_code == 200
assert proxy_mock.get_sequence_state("/inventory")["data"]["position"] == 2
proxy_mock.reset_sequence("/inventory")
assert proxy_mock.execute_request("GET", "/inventory").status_code == 503
```

Both clients support `sequence=...`, `get_sequence_state(path, rule_index=None)` and
`reset_sequence(path, rule_index=None)`. A sequence requires at least one response. Each response
has its own `body`, `status_code` and `headers`, with the same types/defaults as a static mock.
Binary bodies are supported by the clients through msgpack.

`on_exhaustion` defaults to `repeat_last`: after consuming the list, all further calls repeat
its final response. With `error`, further matching requests return `409` and
`{"error": {"code": "sequence_exhausted", "message": "Response sequence exhausted"}}`.
An exhausted matching rule does not fall through to another rule or the default response.

Rules are still selected by their existing conditions and priority. Set the same `sequence`
object directly on a rule to give that rule its own cursor. If no rule matches, a mock-level
sequence supplies the default response. Otherwise the static `mock_data` is used. The optional
`rule` query parameter is the rule's zero-based index in the configured list, before sorting by
priority. Each rule cursor is independent of the default cursor and of the other rules.

State is a separate REST resource:

```sh
curl 'http://localhost:5000/__admin/sequence-state?path=%2Finventory'
curl -X PATCH 'http://localhost:5000/__admin/sequence-state?path=%2Finventory' \
  -H 'Content-Type: application/json' -d '{"position":0}'
```

State contains `position` (number of reserved entries, capped at the list length), `length`,
`exhausted` and `on_exhaustion`. `GET`, administrative `HEAD`, and mock inspection do not consume
responses. `PATCH` accepts only an integer `position: 0`; it resets the selected cursor. A mock
without a sequence, an absent mock or an absent rule sequence returns `404`.

Positions are reserved atomically before configured delays. Concurrent calls cannot reserve
the same entry before exhaustion, but response completion order may differ. The cursor is
shared across all methods, query strings and path-parameter values matching that mock or rule.
Requests rejected by the mock's method filter, and rules that do not match, do not advance it.
Every matching method, including a user mock's `HEAD`, consumes an entry. Cancellation after
reservation also consumes it.

Full mock replacement (`PUT`) starts every cursor from zero. A mock `PATCH` preserves cursors
unless it explicitly supplies `sequence` or `rules`: replacing `sequence` restarts the default
cursor; replacing `rules` restarts rule cursors. `sequence: null` disables that sequence, and
`rules: []` removes rule sequences. Deleting/clearing mocks removes their cursor state. A reset
or replacement affects future reservations; requests already assigned a response retain it.

Sequences cannot be combined with mock-level `proxy_host`, because proxying would bypass the
ordered replies. A rule cannot combine its own sequence with its own
`input_data.proxy_host`. These combinations return `422` before any configuration is changed.

**Snapshots:** format 2 preserves sequence definitions, including binary responses. Import
restarts all imported mock and rule cursors at zero; export leaves current positions unchanged.
Format 1 imports with sequences return `422`. See [snapshot semantics](#snapshots-of-the-storage).

## Record/replay

Available in this unreleased checkout. The
[runnable offline replay example](examples/test_v3_workflows.py) starts a disposable upstream,
saves binary replies and cookies, then replays a snapshot after the upstream has stopped.
Configure a mock with an upstream and explicit recording:

```python
proxy_mock.configure_mock(
    "/inventory",
    proxy_host="http://localhost:8000",
    recording={"mode": "record", "match_headers": ["Accept"]},
)
# Each request reaches the upstream; its completed HTTP response is saved in memory.
original = proxy_mock.execute_request("GET", "/inventory?sku=42", headers={"Accept": "application/json"})
assert original.headers["X-Proxy-Mock-Recording"] == "stored"
entries = proxy_mock.get_recordings("/inventory")["data"]

# PATCH preserves completed recordings when the upstream and matching headers are unchanged.
proxy_mock.patch_mock("/inventory", recording={"mode": "replay", "match_headers": ["Accept"]})
replayed = proxy_mock.execute_request("GET", "/inventory?sku=42", headers={"Accept": "application/json"})
assert replayed.content == original.content
assert replayed.status_code == original.status_code
proxy_mock.delete_recordings("/inventory", entries[0]["id"])
```

Both clients accept `recording=...` and expose `get_recordings(path, recording_id=None)` and
`delete_recordings(path, recording_id=None)`. The administrative resource is
`/__admin/recordings?path=<encoded-mock-path>`: `GET` reads the collection and `DELETE` clears it.
An optional `id` selects a single entry. Missing configurations or entries return `404`;
invalid, empty, repeated or unknown selectors return `422`. The `path` selector is required,
so an invalid selector cannot clear every mock's recordings. Custom administrative prefixes
apply to this resource too.

`recording` is an object with these fields:

| Field | Default | Meaning |
|---|---|---|
| `mode` | Required | `record` proxies each request and stores the completed reply; `replay` serves saved replies without contacting the upstream |
| `match_headers` | `[]` | Additional request header names to include in the matching key; names are case-insensitive, values remain exact |
| `max_items` | `100` | Positive integer limiting retained entries per mock |
| `max_bytes` | `10485760` | Positive integer limiting the sum of JSON-encoded entry sizes, including base64 bodies and metadata |

Matching always uses the method, raw percent-encoded path, raw query string and exact body
bytes. Query order, repeated keys, encoding and body whitespace matter. Selected header values
retain their order; a missing header differs from an empty one. All other headers are ignored.
The key is exposed as a stable SHA-256 `id`. Every entry contains `request` (method, path, query,
selected headers and `body_b64`) and `response` (status code, ordered header pairs and `body_b64`).
Bodies are base64 strings to preserve binary data in JSON. These entries contain test data,
including any selected credentials and upstream cookies, and are readable through the same
unauthenticated administrative API as traffic.

HTTP replies, including redirects, `4xx` and `5xx`, are recorded. Redirects are not followed.
Transport failures return the existing `502`/`504` errors without replacing a saved reply;
allowlist and proxy-loop rejections are not recorded. Replay never falls back to proxying,
rules or `mock_data`. A missing key returns `404` with
`{"error": {"code": "recording_not_found", "message": "No recording matches this request"}}`.
Saved replies can be replayed repeatedly without consumption. `HEAD` has its own key and keeps
the upstream representation length when supplied for an uncompressed response. A missing length
stays absent on replay. Compressed HEAD lengths are omitted because the decoded representation
length cannot be recovered without its body. Bodies are captured after transport decompression;
content encoding, ordinary content length and hop-by-hop headers are removed. Response length
is regenerated, and repeated headers such as `Set-Cookie` are preserved.

For a repeated key, the last completed recording replaces the earlier entry. Reads do not
change eviction order. Limits evict the oldest writes first. A single entry larger than the
byte budget is skipped while the upstream response is still returned and any earlier entry
for that key remains available. Record-mode replies report `X-Proxy-Mock-Recording: stored`,
`too_large` or `superseded`; this diagnostic header is not part of the saved reply. The byte
budget bounds retained serialized data, not total process memory or bodies buffered in flight.

Full mock `PUT` starts with an empty collection. `PATCH` preserves completed entries while
`proxy_host` and normalized `match_headers` remain unchanged, including when switching modes
or resizing limits; lowering limits immediately evicts excess entries. The `recording` object
is replaced as a whole, so repeat any non-default settings in a PATCH. Changing the upstream
or matching headers starts fresh. `recording: null`, mock deletion and clearing mocks discard
the collection. Every mock update detaches pending recordings: their responses still reach
the caller but cannot write into the new generation. A successful recording deletion also
invalidates all pending writes for that mock, preventing a late response from undoing deletion.

Record mode requires a mock-level `proxy_host`. Replay accepts it for later switching back to
record mode, but does not use it. Record/replay rejects combinations with rules or response sequences with `422`. Configured mock methods still apply; rejected
methods and administrative requests never produce recordings. Static response and delay
settings do not affect record/replay replies.

**Snapshots:** format 2 includes the recording configuration and completed entries, preserving
matching keys, binary bodies, repeated header pairs and eviction order. Entries exceeding the
configured limits or failing integrity checks are rejected before mutation. Format 1 imports
containing recording data return `422`. See [snapshot semantics](#snapshots-of-the-storage).

## Removed response caching

Response caching is removed in this 3.0 checkout. `cache_time` is no longer a mock field,
`clean_cache()` is absent from both clients, and `/__admin/cache` returns an administrative
`404`. Passing `cache_time` to either client's configure/patch helper raises `TypeError` before
sending a request; direct HTTP configuration returns `422`, including for null or zero values.
Remove the argument from static mocks: their reply remains available until reconfiguration or
deletion, and configured delays apply to every request. Ordinary mock/rule proxying always
fetches the upstream. For saved upstream replies, use explicit [record/replay](#recordreplay).

Snapshot imports accept legacy `cache_time: null` or `cache_time: 0` and discard those disabled
settings. Any enabled or invalid cache setting returns `422` before mutation. Remove the field
from the file, or migrate the test to record/replay; importing a snapshot never records an
upstream response automatically. New storage representations and snapshot exports omit
`cache_time`. Published 2.x continues to provide its existing caching API.

## Catching requests on `/<path>`

For any path that has a mock configured, the server processes the request in this order:

1. Records the request in traffic.
2. Checks the method, otherwise `405 Method Not Allowed`.
3. If record/replay is configured, either serves a matching saved reply or proxies and records the response as described above.
4. When `proxy_host` is set, proxies to the upstream host and returns its response (proxying "to self" is aborted with `508`). If the host is unreachable or does not resolve — `502`; if it did not answer within `PROXY_MOCK_PROXY_TIMEOUT` — `504`. Every proxied request reaches the upstream.
5. Otherwise selects the first matching rule, or the default response. If it has a sequence, reserves its next entry before waiting.
6. Applies `timeout` (and any matching rule delay), then serves the selected rule response, default sequence entry, or static `mock_data`. Exhausted `error` sequences return `409` immediately.

If no mock is configured for the path, the response is `404` with the body `{"error": "No mock found for /<path>"}`. By default such a request is recorded in traffic too (with `extra_info.status_code = 404`). Recording unknown traffic can be turned off with `PROXY_MOCK_RECORD_UNKNOWN_TRAFFIC=false` or at runtime via `PATCH /__admin/settings`.

---

## 📄 License

[MIT](LICENSE)
