# Migrating from 2.x to 3.0

**3.0 is in development, not released.** This checkout implements its administrative REST API,
response sequences and record/replay; package version metadata remains `2.13.0` until the final
release-preparation step. Published 2.13 keeps the old routes, status codes, response bodies and client transports. Do not infer
the checkout's HTTP compatibility from its temporary package version.

Snapshot evolution, cache removal, transport unification and the client/server
installation split remain later steps. They are not implemented by this checkout.

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
| `POST /cache/clean` | `DELETE /__admin/cache`, pending cache removal |
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

Snapshots retain format 1 in this step, including binary `body_b64`. Use `PUT` to replace
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

The synchronous client still uses `requests`; changing transports and installation extras is
separate work. Deprecated caching also remains in this step, with cleanup at
`DELETE /__admin/cache`. Do not depend on that resource in new tests: cache removal is planned for 3.0.

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

Recordings have no format 1 representation. Export returns `409` for storage containing
record/replay; format 1 imports with `recording` return `422` atomically. Their persistence
belongs to the separate format 2 step. Published 2.13 has no record/replay API.

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

Snapshot format 2 remains a separate preparation step. For now, exporting any configured
sequence returns `409`; format 1 imports with sequences return `422` without changing storage.
Use the configuration API to create sequences during this stage. Ordinary format 1 snapshots
remain supported. Do not add sequence fields to format 1: older readers can silently drop them.

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

## Remaining 3.0 work: synchronous client transport

In 2.13, `ProxyMock` still uses `requests.Session` and returns `requests.Response` from
`execute_request()`. Async transport remains `httpx2`. In 3.0 both clients will use `httpx2`.
Before migrating, audit code that relies on:

- The concrete `requests.Response` type, `.ok`, response truth testing, or `isinstance` checks.
  Prefer explicit `status_code` checks now, with the exact success range your test requires.
- `requests` exceptions. The current sync transport wraps connection/timeouts in
  `ProxyMockRequestError`; other transport exceptions can still come from `requests`.
  The 3.0 exception contract must be documented and tested before release.
- Request keyword arguments, body encoding, redirects, timeouts, streaming, cookies and
  session customisation (including adapters and direct `.session` access). Do not assume
  requests-specific arguments or defaults transfer unchanged to `httpx2`.

Exact 3.0 transport defaults and exception mappings are not implemented in this checkout yet. They must be
specified in this guide when 3.0 ships, with executable before/after examples.

## Remaining 3.0 work: installation and startup

The planned base install, `proxy_mock`, contains only clients; use `proxy_mock[server]` when
running the server, CLI or the pytest fixture that starts a local server. **Do not use this
extra as a migration step yet: published 2.13 and this checkout still install the server
by default.**
Switch existing uvicorn entry points from `proxy_mock.any_catcher:app` to the supported factory
`uvicorn proxy_mock.app:create_app --factory`, or use the `proxy-mock` console command already
available in 2.x. Only one worker is supported because storage is in process memory.

## Remaining 3.0 work: caching and new features

`cache_time`, `clean_cache()` and the cache resource will be removed. The old action-style
`POST /cache/clean` is already gone in this checkout; temporary cleanup uses `DELETE /__admin/cache`. Remove caching from static
mocks now; their configured response already remains available until the mock is changed or
removed. For cached upstream responses, use the explicit record/replay configuration described
above in this checkout. Published 2.13 retains caching and has no record/replay API.

Record/replay and ordered response sequences are implemented in this checkout as documented
above; their snapshot support awaits format 2.
gRPC and an authentication token are outside the 3.0 scope.
