# Migrating from 2.x to 3.0

Version 2.13 is the compatibility preparation release. **3.0 is planned, not released.**
All existing 2.x routes, response bodies, status codes and client transports still work in
2.13. Record & replay, response sequences and the client/server installation split belong to
3.0; they are not available in 2.13.

## Stay on 2.x until you are ready

Pin `proxy_mock>=2.13,<3` in a test project that needs the existing contract. Upgrade the server
first, then the clients. A 2.13 client without `admin_prefix` still uses the legacy paths and
can talk to an older 2.x server. Keep `requests` behaviour until you have checked your callers.
Already installed old versions do not acquire warnings remotely: read release notes and update
to 2.13 to see these notices. There is no network update check or telemetry.

## Try the new administrative paths in 2.13

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

| Legacy operation | 2.13 opt-in alias / planned 3.0 path |
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
| `POST /cache/clean` | No replacement; removed with caching in 3.0 |

In 2.13 aliases keep the existing JSON/msgpack bodies, query parameters and status codes.
`?path=...`, traffic filters and snapshot `?mode=merge|replace` work unchanged. The full RESTful
review for 3.0 may refine contracts; check the final 3.0 migration notes before upgrading.
Old paths remain available even when aliases are enabled. A 3.0 server will default to
`/__admin` and remove the legacy paths.

`clean_storage(path=...)` still calls its legacy endpoint, even with `admin_prefix`, because
it returns `200` with `success: false` for a missing mock. Switch to `delete_mock(path)`, which
returns `404` when the mock is missing. `clean_cache()` also stays on its legacy path in 2.13.

## Understand the warnings

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

## Synchronous client transport in 3.0

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

Exact 3.0 transport defaults and exception mappings are not implemented by 2.13. They must be
specified in this guide when 3.0 ships, with executable before/after examples.

## Installation and startup in 3.0

The planned base install, `proxy_mock`, contains only clients; use `proxy_mock[server]` when
running the server, CLI or the pytest fixture that starts a local server. **Do not use this
extra as a migration step in 2.13: that release still installs the server by default.**
Switch existing uvicorn entry points from `proxy_mock.any_catcher:app` to the supported factory
`uvicorn proxy_mock.app:create_app --factory`, or use the `proxy-mock` console command already
available in 2.x. Only one worker is supported because storage is in process memory.

## Response caching and new 3.0 features

`cache_time`, `clean_cache()` and `POST /cache/clean` will be removed. Remove caching from static
mocks now; their configured response already remains available until the mock is changed or
removed. For cached upstream responses, stay on 2.x until record & replay is available, then
explicitly record a response as a mock and replay it. There is no record & replay API in 2.13.

Record & replay and ordered response sequences are required for 3.0. Their concrete API,
sequence exhaustion/reset behaviour and examples will be documented with implementation.
gRPC and an authentication token are outside the 3.0 scope.
