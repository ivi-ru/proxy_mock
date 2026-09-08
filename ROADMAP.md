# 🗺️ Roadmap

This document records where proxy-mock is going and — just as importantly — where it is not
going. It is a statement of direction, not a schedule: items ship when they are ready, and the
order below is the order of intent. Everything already released is in
[CHANGELOG.md](CHANGELOG.md).

---

## 🎯 Scope

proxy-mock is a small HTTP mock and proxy server for automated tests: configure a response for a
path, point the service under test at proxy-mock, and inspect the traffic it captured. It ships
as a service (Docker, or a single command) and as a Python package with sync and async clients.

**Non-goals.** These are deliberate, and a feature request that falls under them will be declined
with a link to this section. That is not a judgement about the feature — it is what keeps the
tool small enough to stay maintained.

- No service virtualisation platform: no scenario engines, no stateful workflow modelling
- No web UI or admin dashboard
- No stub generation from OpenAPI or other schemas
- No response templating language
- No persistent storage or database: an instance holds its mocks and traffic in memory and loses
  them on restart, and that is the intended lifetime
- No metrics backends (Prometheus and friends): counters are returned as JSON by the service
  endpoint
- Not a load-testing tool: `scripts/benchmark.py` exists to catch regressions, not to test
  other people's services

---

## 🧭 Principles

### Dependency budget

A new runtime dependency is acceptable only when implementing the same thing ourselves would
take more than roughly 100 lines, or when it is protocol code (HTTP, serialisation) that nobody
should hand-roll. Everything below that threshold gets written here instead.

The reason is the second audience: projects that install proxy-mock into their own test
environment inherit every dependency and every version constraint we take on.

Current footprint, measured on Python 3.12 for 2.12.0: `pip install proxy_mock` resolves to **22
distributions** — the package plus 21 dependencies, down from 26 distributions in 2.11.0.
The install split and synchronous client migration in 3.0 will reduce this further.

### Public API contract

**Stable** — changes only in a major release, with a migration note:

- the HTTP API documented in [README.md](README.md)
- `proxy_mock.client` — `ProxyMock` and `AsyncProxyMock`
- `proxy_mock.app:create_app`
- the console script (from 2.11)

**Internal** — may change in any release, without notice:

- `proxy_mock.services.*`, `proxy_mock.repositories.*`, `proxy_mock.core.*`, `proxy_mock.utils`
- `proxy_mock.any_catcher` (currently documented as the uvicorn entry point; replaced by the
  console script in 2.11 and by `proxy_mock.app:create_app` in 3.0)
- the module layout in general

### Breaking changes

Breaking changes are batched into a single major release rather than dripped across minors.
Anything scheduled for removal keeps working for at least one minor release first, with a
deprecation warning and a CHANGELOG entry. Every major ships a "Migrating from …" section, as
2.10.1 did for 1.0.1.

---

## 2.11 — quality of life (released)

Additive: nothing here changes existing behaviour.

- **Console entry point.** `proxy-mock --host … --port … --mocks …` and `python -m proxy_mock`,
  so running the service needs neither Docker nor a uvicorn incantation. With uv installed,
  `uvx proxy-mock` runs it without installing anything at all.
  `--workers` greater than 1 is rejected with an explanation: the mock and traffic stores live
  in process memory, so a second worker answers from an empty store.
- **pytest plugin.** `proxy_mock` and `proxy_mock_url` fixtures shipped through a `pytest11`
  entry point, replacing the fixture boilerplate currently copied out of the README.
- **Lazy package import.** Importing `proxy_mock.client` must not pull in FastAPI and uvicorn
  (PEP 562 `__getattr__` in `proxy_mock/__init__.py`).
- **JSON snapshots.** `GET /storage/snapshot` exports every configured mock; `POST
  /storage/snapshot?mode=replace|merge` loads a snapshot back; `proxy-mock --mocks file.json`
  preloads one at startup. Clients get `export_mocks()` and `import_mocks()`.
  The snapshot format is a public contract from day one: a `"format": 1` envelope, binary bodies
  carried as `body_b64`, and a `protocol` field reserved so that non-HTTP mocks would not force
  a format 2. The endpoints move under the service prefix in 3.0.
- **Container image on GHCR**, published by the release workflow, so that using proxy-mock in
  someone else's CI does not require building the image first.
- **CI.** A job that resolves the declared lower bounds instead of only the locked versions; a
  smoke test that installs the built wheel into a clean virtualenv and runs the pytest fixture
  against it; a check that the container image actually starts and answers.
- **Repository hygiene.** `dependabot.yml` committed to the repository, GitHub Actions pinned by
  commit SHA, `SECURITY.md`.
- **RESTful forms first, deprecation second.** `DELETE /traffic` and `PATCH /traffic/settings`
  were added so that every deprecated endpoint has a replacement available today; only then were
  `POST /storage/clean`, `POST /traffic/clean`, `POST /traffic/settings`, `POST /cache/clean` and
  `cache_time` marked as deprecated. Deprecating something with nowhere to move is just noise.
- **Two lower bounds turned out to be wrong**, and the new CI job found them on its first run:
  `fastapi>=0.136` allowed versions where a user mock shadows the service endpoints (the floor is
  now 0.137.0), and `yarl>=1.8.0` was not installable on any supported Python (now 1.9.4).

---

## 2.12 — dependency diet (released)

No breaking API changes: fewer things installed, with the existing clients and cache API intact.

| Removed | Replaced by | Why |
|---------|-------------|-----|
| `aiocache` | Small TTL dictionary with event-loop timers | Preserves expiration and cleanup for a cache that 3.0 deletes |
| `yarl` | `urllib.parse` | Also removes `multidict` and `propcache`, including their compiled extensions |

Measured result on Python 3.12: **26 → 22** installed distributions including proxy-mock,
three fewer packages with compiled extensions. Counts reflect clean installations on 2026-09-08
and may change as transitive dependencies evolve.

The original plan also removed `requests`, but `ProxyMock.execute_request()` publicly returns
`requests.Response`. Substituting `httpx2.Response` changes `.ok`, truth testing, exceptions and
other caller-visible behaviour. This part moves to 3.0 under the public API contract above.

---

## 3.0 — one breaking release

### Service endpoints move behind a prefix

All service endpoints move under a single prefix (`/__admin` by default, configurable through
`PROXY_MOCK_ADMIN_PREFIX`): eleven routes become five paths, all REST-shaped, and a user mock can
no longer collide with a service endpoint.

Today that isolation depends on how FastAPI nests routers added through `include_router` — see
the docstring in `tests/test_service_routes.py` — which is why `fastapi>=0.137` is pinned as a
lower bound. It also means configuring a mock for `/proxy_mock` currently returns `success: true`
and then never serves that mock. After the move the isolation is ours, and the FastAPI floor can
be lowered again.

| 2.x | 3.0 |
|-----|-----|
| `GET /proxy_mock` | `GET /__admin` |
| `POST /configure_mock`, `PATCH /configure_mock` | `POST /__admin/mocks`, `PATCH /__admin/mocks` |
| `GET /storage`, `DELETE /storage`, `POST /storage/clean` | `GET /__admin/mocks`, `DELETE /__admin/mocks` |
| `GET /traffic`, `POST /traffic/clean` | `GET /__admin/traffic`, `DELETE /__admin/traffic` |
| `GET /traffic/settings`, `POST /traffic/settings` | `GET /__admin/settings`, `PATCH /__admin/settings` |
| `GET` / `POST /storage/snapshot` | `GET` / `POST /__admin/snapshot` |
| `POST /cache/clean` | removed with the cache |

### Response caching removed

`cache_time`, `POST /cache/clean` and the cache service are deleted. Caching a mock response is
close to a no-op by construction — the mock is already static and cheap — and the one case where
it does something, a proxied response, is better served by record & replay, which is explicit
about what was recorded and lets you look at it.

### Synchronous client transport

Both clients use `httpx2`, removing `requests` and the dependencies used only by it. The
migration guide must cover the new response type, exception classes, request keyword arguments,
redirect defaults, timeouts and session customisation. Existing `requests.Response` behaviour
remains available throughout 2.x.

### Install split

The base install becomes the clients only; the server moves behind an
extra, `proxy_mock[server]`. Exact distribution counts will be measured at release time.
A project that installs proxy-mock to talk to a running
instance stops inheriting FastAPI, uvicorn and their constraints.

### Entry point

The documented entry point becomes the `proxy-mock` console script, with
`proxy_mock.app:create_app` for embedding. `proxy_mock.any_catcher:app` stops being documented.

---

## Under consideration

Not scheduled. Listed so that the intent is on record.

- **Record & replay** — proxy a request to the real upstream and store the response as a mock.
  The proxy half already exists, and this is the well-defined feature that response caching was
  reaching for.
- **Response sequences** — first call returns A, second returns B, for a single path. Fits the
  existing rule engine.
- **Optional auth token** — a single shared token on the service endpoints
  (`PROXY_MOCK_TOKEN`), so an instance can be reachable outside localhost.
- **gRPC** — deferred, and not merely unscheduled. The blockers are structural: uvicorn does not
  serve HTTP/2 at all; gRPC delivers its status in trailers, which are an ASGI extension with
  uneven server support; and `grpcio` is a large C extension that historically lags behind new
  CPython releases, which would hold back the interpreter versions this project supports. If it is ever built, the shape is fixed in advance: an optional extra on a separate
  port, opaque byte-level unary mocking (routing by `/package.Service/Method`, no protobuf
  parsing, no descriptors), and no streaming, reflection or TLS termination. Demand will be
  collected in an issue before any code is written.
