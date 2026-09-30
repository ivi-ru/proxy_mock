# Migrating from 2.x to 3.0

**3.0 is in development, not released.** This checkout implements its administrative REST API,
response sequences and record/replay; package version metadata remains `2.13.0` until the final
release-preparation step. Published 2.13 keeps the old routes, status codes, response bodies and client transports. Do not infer
the checkout's HTTP compatibility from its temporary package version.

Both clients now use `httpx2` as described below. The client/server installation split
remains a later step; this checkout still installs the server by default.

## Administrative REST API in this checkout

The server and both Python clients now default to `/__admin`. Set `PROXY_MOCK_ADMIN_PREFIX` on
the server and pass the same `admin_prefix` to clients to change it. The pytest fixtures read
the environment setting for both local and externally configured servers. An unset value uses
`/__admin`; an empty value is invalid. Prefixes use absolute paths of letters, digits,
underscores, hyphens and optional path segments, without a trailing slash.

The whole administrative namespace is reserved, including unknown children. User mocks cannot
shadow it. Legacy service paths are removed and become ordinary mock paths: `/storage`,
`/traffic`, `/configure_mock`, `/docs`, `/redoc` and `/openapi.json` no longer provide service
operations. A prefix provides routing isolation, not authentication.

| Operation in 2.x | Resource and method in this checkout |
|-----------------|-------------------------------------|
| `GET /proxy_mock` | `GET /__admin` |
| `POST /configure_mock` | `PUT /__admin/mocks?path=<encoded-path>` |
| `PATCH /configure_mock` | `PATCH /__admin/mocks?path=<encoded-path>` |
| `GET /storage` | `GET /__admin/mocks` |
| `GET /storage?path=...` | `GET /__admin/mocks?path=<encoded-path>` |
| `DELETE /storage`, `POST /storage/clean` without a path | `DELETE /__admin/mocks` |
| Delete a specific mock | `DELETE /__admin/mocks?path=<encoded-path>` |
| `GET /traffic` | `GET /__admin/traffic` |
| `DELETE /traffic`, `POST /traffic/clean` | `DELETE /__admin/traffic` |
| `GET /traffic/settings` | `GET /__admin/settings` |
| `PATCH /traffic/settings`, `POST /traffic/settings` | `PATCH /__admin/settings` |
| `GET /storage/snapshot` | `GET /__admin/snapshot` |
| `POST /storage/snapshot?mode=replace` | `PUT /__admin/snapshot` |
| `POST /storage/snapshot?mode=merge` | `PATCH /__admin/snapshot` |
| `POST /cache/clean` | Removed; no administrative cache resource |
| `GET /docs`, `/redoc`, `/openapi.json` | `GET /__admin/docs`, `/__admin/redoc`, `/__admin/openapi.json` |

There are no action-style `POST` aliases. A query is part of the resource URI, so
`/__admin/mocks?path=%2Finventory` identifies the configuration for `/inventory` without
mixing its potentially nested or encoded request path into the administrative path hierarchy.
Use a client's query encoder rather than concatenating arbitrary paths into a URL.

### Mock creation, replacement and partial updates

The mock path moves to the required query parameter on `PUT` and `PATCH`. A body `path` is
optional and, when supplied, must match. `GET` and `DELETE` without a query address the whole
collection; `?path=` is invalid and never means all mocks.

Before, in released 2.x:

```sh
curl -X POST http://localhost:5000/configure_mock \
  -H 'Content-Type: application/json' \
  -d '{"path":"/inventory","mock_data":{"body":{"available":3}}}'
```

After, in this checkout:

```sh
curl -X PUT 'http://localhost:5000/__admin/mocks?path=%2Finventory' \
  -H 'Content-Type: application/json' \
  -d '{"mock_data":{"body":{"available":3}}}'
```

`PUT` creates the mock with `201` or replaces it with `200`. Repeating it produces the same
configuration, and omitted properties return to defaults. `PATCH` returns `200` only for an
existing mock and preserves omitted properties. It merges supplied `mock_data` properties,
while replacing a supplied response body or array as a whole. It is not JSON Merge Patch.
Explicit `null` clears nullable fields; non-nullable fields reject null. For example:

```sh
curl -X PATCH 'http://localhost:5000/__admin/mocks?path=%2Finventory' \
  -H 'Content-Type: application/json' \
  -d '{"proxy_host":null,"mock_data":{"body":null,"status_code":204},"rules":[]}'
```

This clears the proxy target and response body, changes the status and removes every rule,
while retaining response headers and other omitted fields. JSON and msgpack mock bodies remain
supported. Missing item reads, patches and deletes return `404`; a repeated deletion therefore
returns `404` after its first successful `200`, while remaining idempotent in its effect.

### Responses and validation

Successful responses retain their operation-specific `success`/data envelopes; snapshot
export still returns the snapshot document directly. Administrative errors now use:

```json
{"success": false, "error": {"code": "mock_not_found", "message": "No mock found for /inventory"}}
```

`error.details` is optional. Update callers that expected a string or list in `error`, a
successful empty result for a missing mock, or `201` for replacement. Invalid representations,
empty paths, body/query path mismatches and invalid traffic filters return `422`. Malformed
JSON/msgpack returns `400`; unsupported mock body content types return `415`. Unsupported
administrative methods return `405`. These errors do not change user-defined mock responses.

### Traffic, settings and snapshots

Traffic reads accept `path`, `method` and `limit`. Deletion clears all traffic and accepts no
query parameters; supplying a filter returns `422` without deleting records. Settings remain a partial update
of `record_unknown_traffic` and/or positive `max_items` through `PATCH /__admin/settings`.

Snapshots export format 2; imports and CLI preload accept formats 1 and 2, including binary
`body_b64`. Format 2 adds sequence definitions and completed recordings. Use `PUT` to replace
storage or `PATCH` to merge complete mocks keyed by path. Snapshot PATCH is a custom merge:
it replaces every included mock in full, keeps other paths, and is not RFC 7396 JSON Merge
Patch. Both methods accept the exported snapshot document. Invalid imports leave storage
unchanged. The old `POST` and `mode` query switch are removed.

```sh
curl http://localhost:5000/__admin/snapshot > mocks.json
curl -X PUT http://localhost:5000/__admin/snapshot \
  -H 'Content-Type: application/json' --data-binary @mocks.json
```

### Python clients

Use the clients from the same checkout as the server. The public convenience methods select
the new resource methods; `configure_mock()` uses PUT and `patch_mock()` uses PATCH.
`import_mocks(..., mode="replace")` uses PUT and `mode="merge"` uses PATCH. Generic
`execute_request()` calls still use the exact route you provide, so migrate any handwritten
administrative requests. Published 2.13 clients use a different HTTP contract even when their
opt-in prefix is `/__admin`.

Both clients return `httpx2.Response`; migrate request arguments and response handling
as described below. Response caching is removed. Installation extras remain separate work.

## Record/replay in this checkout

Record/replay is explicit: configure `recording: {"mode": "record"}` with a mock-level
`proxy_host`, then switch with `PATCH` to `recording: {"mode": "replay"}`. This preserves
completed replies while upstream and `match_headers` remain unchanged. Repeat non-default
recording settings when switching; the object is replaced in full. Both clients accept
`recording=...`, `get_recordings()` and `delete_recordings()`.

`GET` and `DELETE /__admin/recordings?path=...` inspect and clear a mock's recorded replies;
an optional `id` selects one entry. Modes belong to the mock resource rather than action
endpoints. Matching uses method, raw path/query and exact body bytes, optionally selected
headers. Replay does not contact the upstream and returns `404` on a missing key. Completed
HTTP errors are recorded; transport errors are not. Collections have configurable count and
byte limits, and record-mode responses report whether storage succeeded through
`X-Proxy-Mock-Recording`. See the [full contract](README.md#recordreplay), including lifecycle,
concurrent requests, binary bodies and repeated headers.

Snapshot format 2 preserves recording configuration and completed replies, including binary
bodies, repeated header pairs and eviction order. Invalid keys or collections exceeding their
configured limits return `422` before mutation. Format 1 has no recording representation and
rejects this data. Published 2.13 has no record/replay API.

## Response sequences in this checkout

Mocks and rules accept `sequence: {"responses": [...], "on_exhaustion": "repeat_last"}`.
The default repeats the final response; `on_exhaustion: "error"` returns `409` when all entries
have been consumed. Existing static mocks and rule matching keep their behavior when no
sequence is configured. See [the sequence contract](README.md#response-sequences) for examples.

Inspect cursors with `GET /__admin/sequence-state?path=...`; reset one with `PATCH` and
`{"position": 0}`. Add `rule=<zero-based-index>` to select a rule cursor. Both clients provide
`get_sequence_state()` and `reset_sequence()`. Full mock replacement starts fresh; unrelated
partial updates keep cursor positions. Requests already assigned a response keep it across
reset, reconfiguration or deletion.

Format 2 exports sequence definitions and binary responses; imported cursors start at zero.
Export does not change positions. Format 1 imports with sequences return `422` atomically.
Ordinary format 1 snapshots remain supported. Published 2.x cannot read format 2; do not
relabel its envelope as format 1. Traffic and in-flight requests are excluded.
Snapshot merge replaces supplied mocks and recordings completely while preserving omitted
mocks. Missing recording arrays mean empty collections. The CLI restores format 2 at startup.
See the [snapshot contract](README.md#snapshots-of-the-storage).

## Released 2.13 compatibility reference

The following sections describe published 2.13 only. They do not describe this checkout.

### Stay on 2.x until you are ready

Pin `proxy_mock>=2.13,<3` in a test project that needs the existing contract. Upgrade the server
first within the 2.x line, then the clients. A 2.13 client without `admin_prefix` still uses the
legacy paths and can talk to an older 2.x server. Keep `requests` behaviour until you have checked your callers.
Already installed old versions do not acquire warnings remotely: read release notes and update
to 2.13 to see these notices. There is no network update check or telemetry.

### Try the administrative aliases in 2.13

Aliases are **opt-in** so that an existing mock at `/__admin` is not unexpectedly shadowed.
Start the server with:

```sh
PROXY_MOCK_ADMIN_PREFIX=/__admin proxy-mock --host 127.0.0.1 --port 5000
```

Use the same prefix explicitly in either client:

```python
from proxy_mock.client import ProxyMock, AsyncProxyMock

with ProxyMock("http://127.0.0.1:5000", admin_prefix="/__admin") as client:
    client.configure_mock(path="/inventory", body={"available": True})
    assert client.execute_request("GET", "/inventory").json()["available"]

# In async code:
# async with AsyncProxyMock("http://127.0.0.1:5000", admin_prefix="/__admin") as client:
#     await client.get_storage()
```

The prefix must be an absolute path of letters, digits, underscores, hyphens and optional
path segments, without a trailing slash. It must not overlap an existing service path such as
`/storage`, `/traffic`, `/docs` or their children. A prefix is not authentication. Reserve its
administrative paths for the server and choose a prefix that does not collide with your mocks.
Leaving the environment variable unset disables aliases; an explicitly empty value is invalid.
Generic `execute_request()` calls always use the route you provide, without rewriting mock URLs.
The pytest fixture continues using the legacy routes in 2.13; construct a client explicitly to
exercise the aliases.

| Legacy operation | Released 2.13 opt-in alias |
| --- | --- |
| `GET /proxy_mock` | `GET /__admin` |
| `POST /configure_mock` | `POST /__admin/mocks` |
| `PATCH /configure_mock` | `PATCH /__admin/mocks` |
| `GET /storage` | `GET /__admin/mocks` |
| `DELETE /storage` | `DELETE /__admin/mocks` |
| `POST /storage/clean` | `DELETE /__admin/mocks` |
| `GET /traffic` | `GET /__admin/traffic` |
| `DELETE /traffic`, `POST /traffic/clean` | `DELETE /__admin/traffic` |
| `GET /traffic/settings` | `GET /__admin/settings` |
| `PATCH /traffic/settings`, `POST /traffic/settings` | `PATCH /__admin/settings` |
| `GET /storage/snapshot` | `GET /__admin/snapshot` |
| `POST /storage/snapshot` | `POST /__admin/snapshot` |
| `POST /cache/clean` | No alias; the legacy cache endpoint remains |

In 2.13 aliases keep the existing JSON/msgpack bodies, query parameters and status codes.
`?path=...`, traffic filters and snapshot `?mode=merge|replace` work unchanged. These aliases do not implement the new
PUT/PATCH contract above. Old paths remain available even when aliases are enabled in 2.13.

`clean_storage(path=...)` still calls its legacy endpoint, even with `admin_prefix`, because
it returns `200` with `success: false` for a missing mock. Switch to `delete_mock(path)`, which
returns `404` when the mock is missing. `clean_cache()` also stays on its legacy path in 2.13.

### Understand the 2.13 warnings

Every matched legacy service operation returns `Deprecation: @1789603200` (the announcement
date, 2026-09-17 UTC) and a `Link` with `rel="deprecation"` pointing to this guide. The date
syntax follows [RFC 9745](https://www.rfc-editor.org/rfc/rfc9745.html); it replaces the old
non-standard `Deprecation: true` value. When aliases are enabled, another link with
`rel="successor-version"` points to the replacement resource. Consult the table for the HTTP
method: a URI alone does not tell you to change `POST` to `DELETE` or `PATCH`.
The same notices accompany handled error responses. User mock responses are not marked.
Aliases themselves have no route-deprecation header. Server warnings are logged once per
operation per process, rather than for every request. No `Sunset` date is promised yet.

Python emits `DeprecationWarning` for the synchronous client's upcoming transport change,
`cache_time`, `clean_cache()` and `clean_storage(path=...)`. Python's standard warning filters
control repetition and visibility; use `python -W default::DeprecationWarning -m pytest` to
review them. Warnings do not change successful responses or retries. Projects treating warnings
as errors should review these notices before enabling that policy for a dependency upgrade.

## Python client transport in this checkout

Both `ProxyMock` and `AsyncProxyMock` now use `httpx2` and return its buffered `Response`
from `execute_request()`. `requests`, `charset-normalizer`, `urllib3` and `certifi` are no
longer installed by proxy-mock. Published 2.13 retains `requests.Session` and
`requests.Response` for the synchronous client.

### Response handling and request arguments

Replace `.ok` and response truth testing with an explicit status check. `httpx2.Response`
is always truthy, including HTTP errors; `.is_success` is true only for 200–299. If your
old `.ok` check accepted redirects, use `response.status_code < 400` instead.

Before (published 2.x sync client):

```python
with ProxyMock(url) as client:
    response = client.execute_request("POST", "/upload", data=b"raw", allow_redirects=False)
    assert response.ok
    cookies = response.raw.headers.getlist("Set-Cookie")
```

After (this checkout, sync client):

```python
with ProxyMock(url) as client:
    response = client.execute_request("POST", "/upload", content=b"raw", follow_redirects=False)
    assert response.is_success
    cookies = response.headers.get_list("Set-Cookie")
```

The async client accepts the same arguments using `await`. Request options follow the
native `httpx2` request API: `content=` sends raw bytes or text, `json=` serializes JSON,
`data=` accepts a form mapping, and `files=` uploads multipart data. Raw text or bytes in
`data=` raise `TypeError`. Replace `allow_redirects` with `follow_redirects`. `stream=` is
unsupported: wrapper calls read the complete response. Use the native client's streaming
API when needed. Use `response.headers.raw` for original header bytes; convenience header
accessors may decode UTF-8 rather than Latin-1.

JSON, forms and multipart encoding can differ from requests. Recording keys include exact
request bytes: reuse explicit `content=` when byte identity matters, or capture a new
recording after migrating the request encoding. Generic relative routes append to the
wrapper host's base path, preserving encoded paths, raw query strings and trailing slashes;
absolute request URLs override the host.

### Defaults and exceptions

Clients created by the wrapper do not follow redirects by default. Set `follow_redirects=True`
per request to follow them. The constructor timeout defaults to 10 seconds for each connect,
read, write and pool operation, not a total deadline. Pass a number, `httpx2.Timeout` or
`None` (disable timeouts); a per-request `timeout=` overrides the constructor value.
Native TLS verification and environment proxy settings remain enabled by default.

HTTP errors return a response by default. `execute_request(..., raise_for_status=True)`
raises `ProxyMockResponseError` for status codes >=400, or `AsyncProxyMockResponseError`
for async calls; the exception exposes `.response`. Redirects do not raise through this
flag. Calling the native `response.raise_for_status()` instead raises
`httpx2.HTTPStatusError` for any non-2xx status, including redirects.

All native `httpx2.RequestError` failures are wrapped in `ProxyMockRequestError` or
`AsyncProxyMockRequestError`, with the original exception in `__cause__`. This includes
connection, read/write, timeout, protocol, decoding and redirect-limit errors. Native
`httpx2.InvalidURL` and argument errors such as `TypeError` propagate unchanged. All four
wrapper exception classes are exported from `proxy_mock.client`; the async error classes
also subclass the corresponding sync error classes, so shared callers can catch the common
base classes. Their existing module import locations remain available.

### Custom native clients and ownership

Replace `.session` access and requests adapters with an `httpx2.Client` or `AsyncClient`.
Pass it as `http_client=` to preserve configured headers, cookies, authentication, TLS,
proxy, transport and event hooks. The wrapper exposes it through `.http_client` and always
uses its own host for relative routes, regardless of the native client's `base_url`.

```python
import httpx2
from proxy_mock.client import ProxyMock

with httpx2.Client(headers={"X-Test": "yes"}, trust_env=False) as http:
    with ProxyMock(url, http_client=http, timeout=5.0) as client:
        response = client.execute_request("GET", "/item")
        assert response.is_success
    # The borrowed native client is still open here.
```

For async use, nest `async with httpx2.AsyncClient(...) as http` and
`async with AsyncProxyMock(url, http_client=http) as client`. The injected client's
`follow_redirects` default is honored, while the wrapper's constructor timeout applies
unless overridden per request. A wrapper-created native client is closed by `close()` /
`aclose()` or context exit, including exceptional exit. An injected client is borrowed:
the caller closes it. Passing the wrong native client type raises `TypeError`.

## Remaining 3.0 work: installation and startup

The planned base install, `proxy_mock`, contains only clients; use `proxy_mock[server]` when
running the server, CLI or the pytest fixture that starts a local server. **Do not use this
extra as a migration step yet: published 2.13 and this checkout still install the server
by default.**
Switch existing uvicorn entry points from `proxy_mock.any_catcher:app` to the supported factory
`uvicorn proxy_mock.app:create_app --factory`, or use the `proxy-mock` console command already
available in 2.x. Only one worker is supported because storage is in process memory.

## Removed response caching in this checkout

`cache_time`, `clean_cache()` and both the legacy and administrative cache resources are
removed. Passing the field to either client's configure/patch helper raises `TypeError`
locally, and direct HTTP mock configuration returns `422` even for null or zero. Calling
`clean_cache()` raises `AttributeError`; `/__admin/cache` returns `404` and remains protected
from user-mock shadowing. Remove cleanup calls and the field from your tests.

Static mock replies stay available until reconfiguration or deletion, and delays apply to
every request. Ordinary proxying reaches the upstream on each request. Use explicit
[record/replay](README.md#recordreplay) to capture and serve upstream replies.

For migration, snapshot imports accept and discard disabled legacy cache values (`null` or
integer zero). Enabled or invalid cache values return `422` without changing configuration,
recordings or cursors. Remove the field from those files or migrate the scenario explicitly;
import never contacts an upstream to populate recordings. New exports omit the field.
Published 2.13 retains its caching API and transport behavior.

Record/replay, ordered sequences and snapshot format 2 are implemented in this checkout.
gRPC and an authentication token are outside the 3.0 scope.
