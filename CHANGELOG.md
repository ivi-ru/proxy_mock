Migrating from 1.0.1
====================

The previously published 1.0.1 (Flask) and the current 2.x line (FastAPI) are not compatible.
Five changes require edits in projects upgrading from 1.0.1:

* **`GET /status` was renamed to `GET /proxy_mock`.** There is no alias: `/status` is now
  handled by the any-catcher (`404`, or a user mock if one is configured)
* **The client method `get_status()` was renamed to `get_proxy_mock()`.** There is no alias
* **The dedicated `POST /configure_mock/binary` endpoint is gone.** A binary body is sent to
  the regular `POST /configure_mock` with `Content-Type: application/octet-stream` (msgpack)
* **The client method `configure_binary_mock()` was removed** — use `configure_mock()`, which
  serialises the body to msgpack itself
* **Error messages are now in English.** A missing mock returns
  `{"error": "No mock found for /<path>"}` instead of the previous Russian text; code that
  matches on message text needs updating

Still compatible: `POST /configure_mock`, `GET /storage`, `POST /storage/clean`,
`GET /traffic`, `POST /traffic/clean` and the client methods `configure_mock()`,
`get_traffic()`, `get_storage()`, `clean_storage()`, `clean_traffic()`. `get_traffic()` gained
optional filters (`path`, `method`, `limit`); calling it without arguments is unchanged.

Environment requirements changed as well: Python >= 3.11 instead of 3.9, and uvicorn instead
of gunicorn. From 2.11.0 the service is started with the `proxy-mock` command.

Version 2.11.0
==============

* **Console entry point.** `proxy-mock --host … --port … --mocks …` starts the service without Docker and without a uvicorn command line; the same entry point works as `python -m proxy_mock`, and `uvx proxy-mock` runs it without installing anything. `--workers` greater than 1 is refused with an explanation: mocks and traffic live in the memory of a single process, so a second worker would answer from an empty storage
* **pytest fixtures ship with the package.** The `pytest11` entry point registers `proxy_mock` (a client, with mocks and traffic reset after every test) and `proxy_mock_url` (a session-scoped instance on a free port). `PROXY_MOCK_URL` points them at an instance that is already running instead of starting one. The fixture boilerplate previously copied out of the README is no longer needed
* **JSON snapshots of the storage.** `GET /storage/snapshot` exports every mock as one document, `POST /storage/snapshot?mode=merge|replace` loads it back, and `proxy-mock --mocks file.json` preloads it at startup. The clients gained `export_mocks()` and `import_mocks()`. The document carries `"format": 1` and a `protocol` field so that later versions stay readable; binary bodies travel base64-encoded in `body_b64`. An invalid snapshot is rejected before anything is written, so the storage is never left half-loaded
* Importing `proxy_mock.client` no longer pulls in FastAPI and uvicorn: `create_app` is resolved lazily (PEP 562). A project that only talks to a running instance stops paying the import cost of the server

* **Fixed:** the declared lower bound `fastapi>=0.136` was not safe. On 0.136.x a user mock shadows the service endpoints — configuring a mock for `/proxy_mock` made the service endpoint return the mock — because the routing behaviour the isolation relies on arrived in 0.137.0. The bound is now `fastapi>=0.137.0`
* **Fixed:** the declared lower bound `yarl>=1.8.0` was not installable on any supported Python: 1.8.0 has no wheels for 3.11+ and its generated C sources no longer compile. The bound is now `yarl>=1.9.4`

* `DELETE /traffic` and `PATCH /traffic/settings` were added as the RESTful forms of clearing traffic and updating settings, so that the endpoints deprecated here have a replacement to move to today
* **Deprecated, removed in 3.0:** `POST /storage/clean`, `POST /traffic/clean`, `POST /traffic/settings`, `POST /cache/clean` and the `cache_time` field. They keep working unchanged, but send a `Deprecation: true` header with a `Link` to the replacement and log a warning once per process
* The clients now call the RESTful endpoints (`clean_storage()`, `clean_traffic()`, `set_traffic_settings()`); the responses are unchanged. `clean_storage(path=…)` and `clean_cache()` emit a `DeprecationWarning` — use `delete_mock(path)` instead of the former

* A container image is published to GHCR on every release: `docker run --rm -p 5000:5000 ghcr.io/ivi-ru/proxy_mock:latest`. The image now carries a default command, so it starts without build arguments
* CI additions: a job that resolves and tests the declared *lowest* dependency versions, and a smoke test that installs the built wheel into a clean environment and runs the shipped fixtures and console script against it. GitHub Actions are pinned by commit SHA and the Dependabot configuration lives in the repository
* **Free-threaded interpreters are no longer supported.** Running on a free-threaded build (3.14t) measured slower than on the regular one, because the service's work is CPU-bound. The documentation section, the `scripts/check_gil.py` helper and the intent to test that build have been dropped; the regular 3.11-3.14 builds are unaffected
* Project documentation: `ROADMAP.md` (scope, non-goals, the dependency budget and what 2.12 and 3.0 change), `CONTRIBUTING.md`, `SECURITY.md` and `AGENTS.md`

Version 2.10.1
==============

* First public release of the 2.x line. The changes since 1.0.1 are listed below, and the upgrade path is in "Migrating from 1.0.1"
* Functionality is unchanged relative to 2.10.0: code, API and clients were not modified
* Documentation, code comments and API error messages are now in English
* Added a license file (MIT) and a GitHub Actions build

Version 2.10.0
==============

* **Breaking change.** The service endpoint `GET /status` was renamed to `GET /proxy_mock`. The old path is not even kept as an alias: `/status` is now handled by the any-catcher (`404` or a user mock)
* **Breaking change.** In the `ProxyMock` and `AsyncProxyMock` clients the `get_status()` method was renamed to `get_proxy_mock()` with no alias, so consumer projects need fixing on upgrade

* Fixed a `500` with a traceback when `proxy_host` was unreachable: the httpx2 transport error (DNS failure, refused connection, broken protocol) bubbled up to uvicorn. It now returns `502` with the reason, and `504` when the upstream host times out. Fixed in both proxy paths, for mocks and for rules. Failed responses are not cached and the request still lands in traffic
* `GET /proxy_mock` returns an instance summary: the Python version (`python_version`), the number of configured mocks (`mocks_count`), the number of traffic records (`traffic_count`) and the current store limit (`traffic_max_items`)
* The traffic store limit is adjustable at runtime through the `max_items` field of `POST /traffic/settings`. Lowering the limit trims the oldest records and keeps the freshest. The endpoint body is a partial update: any subset of fields is accepted, an empty body gives `422`

* Recording of unknown traffic (requests that matched no mock) became switchable. The `PROXY_MOCK_RECORD_UNKNOWN_TRAFFIC` environment variable (default `true`, preserving 2.9.0 behaviour) accepts `1/0`, `true/false`, `yes/no`, `on/off`; an unrecognised value falls back to the default
* New service endpoints `GET /traffic/settings` and `POST /traffic/settings` configure traffic capture at runtime, without restarting the service. The clients gained `get_traffic_settings()` and `set_traffic_settings()`
* The `404` response itself and its logging do not change when recording is off: the flag only controls whether the request lands in traffic

* The project moved from Poetry to uv: `uv.lock` instead of `poetry.lock`, dev dependencies in `[dependency-groups]` (PEP 735)
* The build backend changed from `poetry-core` to `hatchling`; the sdist contents are listed explicitly so tests and repository service files are not shipped
* The Dockerfile and the build moved to uv: `uv sync --locked` instead of `poetry sync`, `uv build` / `uv publish` instead of `poetry build` / `poetry publish`. The multi-stage layout did not change
* The Makefile gained an `install` target (`uv sync`); `.venv/` and `dist/` were added to `.gitignore`

Version 2.9.0
=============

* Requests that matched no mock (the 404 response) are recorded in traffic, with `status_code: 404` written to `extra_info`
* `requested_at_ts` was dropped from traffic; only `requested_at` remains (Europe/Moscow, ISO-8601)
* Protection against proxying "to self": the `x-proxy-mock-chain` marker header, with the loop aborted by a `508` response
* An allowlist of proxy targets via `PROXY_MOCK_ALLOWED_PROXY_HOSTS` (disabled by default, so any host is allowed)
* The traffic store limit was set to 1000 and made configurable through `PROXY_MOCK_TRAFFIC_MAX`
* An explicit timeout for outgoing proxied requests, configurable through `PROXY_MOCK_PROXY_TIMEOUT` (30s by default)
* A new `DELETE /storage` endpoint for deleting mocks: without `path` all of them, with `path` a single one (`404` if it does not exist). `POST /storage/clean` remains as a deprecated alias
* Moved from `httpx` to `httpx2` (the httpx successor maintained under Pydantic) for the server HTTP clients, the async client and the benchmark

* The Dockerfile became multi-stage: a slim server image without compilers, git and poetry, plus a separate `ci-image` target for CI tasks
* Service version detection works when proxy_mock is installed as a library: first proxy_mock's own pyproject.toml, then the package metadata (previously `create_app()` failed without a pyproject.toml in the working directory)
* README: a section on running without Docker (pip package plus a pytest fixture)
* Lower dependency bounds were relaxed for compatibility when installed as a library: Python `>=3.11`, pydantic `>=2.6`, uvicorn `>=0.27`, requests `>=2.31`, aiocache `>=0.12.2`. FastAPI stays at `>=0.136`, because below that the service endpoint protection breaks
* A regression test for service route protection (`tests/test_service_routes.py`)

* Fixed a bug in full mock cleanup: runtime routes are now removed as well (previously a path kept answering with its mock after cleanup)
* Fixed handling of malformed msgpack during configuration: it returns `400` instead of `500`
* Removed unreachable code in binary data serialisation

* Added a "Security" section to the README (no authentication, SSRF via `proxy_host`, sensitive data in traffic)
* The API section of the README was simplified and brought up to date, with a link to the auto-generated OpenAPI docs (`/docs`, `/redoc`)
* Increased test coverage, including the `AsyncProxyMock` async client

Version 2.8.0
=============

* Migration to Python 3.14.6 with support for the free-threaded build (3.14.6t)
* Updated FastAPI (>=0.136), uvicorn (>=0.44) and the remaining dependencies
* TOML reading replaced with the stdlib `tomllib` (writing goes through `tomlkit` in the CI scripts)

* The project structure was refactored:
  * `app/` — application factory and lifespan
  * `api/routes/` — HTTP routes
  * `domain/` — schemas and domain constants
  * `services/` — business logic (mock/proxy/rules/cache/parser/traffic)
  * `repositories/` — in-memory stores
  * `core/` — logging, settings, serialisation, time
* `any_catcher.py` became a thin entrypoint
* Reduced coupling and bloat in `utils.py`

* Async upstream proxying via `httpx` instead of the blocking `requests` in the server
* Traffic now stores the request time:
  * `requested_at` (Europe/Moscow, ISO-8601)
  * `requested_at_ts` (unix timestamp)
* The traffic store is bounded: only the last 100 requests
* Added concurrency protection (a lock) for the in-memory stores
* Improved rule logic:
  * `priority` support
  * more stable condition matching
* Added filters for `/traffic`: `path`, `method`, `limit`
* Configurable request logging through `PROXY_MOCK_LOG_REQUESTS=full|minimal|off`

* Sync client refactoring:
  * less duplication between configure and patch
  * better request/response handling
* Added a new async client `AsyncProxyMock` built on `httpx`

* Moved to public APIs, without relying on private fields such as `_dict` and `_url`
* Behavioural compatibility was preserved for existing tests and mocking scenarios

Version 2.5.4
=============

* Fixed the data type of the incoming request body

Version 2.5.3
=============

* Fixed rule sorting

Version 2.5.2
=============

* Mock rules are now sorted by creation time, newest first

Version 2.5.1
=============

* Added proxying and delays inside mock rules

Version 2.5.0
=============

* Updated helper packages and raised the minimum Python version to 3.10
* Added caching of mocked responses
* Added an endpoint for cache invalidation

Version 2.4.3
=============

* Added the ability to pass extra information about a mock rule into traffic

Version 2.4.2
=============

* Added the ability to pass HTTP request methods when configuring mock rules

Version 2.4.1
=============

* Added the ability to specify the HTTP request method during configuration
* Fixed coverage measurement for asynchronous code
* `pyproject.toml` was converted to the new format used by the newer poetry
* Added pre-commit to make linting easier

Version 2.4.0
=============

* Merged the JSON and binary mock configuration endpoints into a single `/configure_mock`. By default client requests compress the payload into bytes and the server unpacks it back into a dict
* Updated unit tests
* Added msgpack, a library for working with binary data

Version 2.3.1
=============

* Fixed automatic tag creation

Version 2.3.0
=============

* Added new PATCH endpoints for updating already created mocks

Version 2.2.0
=============

* Changed how rules work: when several conditions are given in one rule, the special response is returned only if all of them match
* Added the ability to specify query parameters in rules
* The Docker application now uses Python 3.13

Version 2.1.2
=============

* Fixed a bug in how extra information was shown in traffic

Version 2.1.1
=============

* Fixed formatting of incoming request bodies
* Traffic now includes information about query parameters and the request method
* Updated the returned content type for strings and protobufs

Version 2.1.0
=============

* Added the ability to return different responses for one mock based on given conditions

Version 2.0.0
=============

* Service routes were renamed:
    /configure --> /configure_mock
    /configure/binary --> /configure_mock/binary
    /cleanup_params --> /traffic/clean
    /cleanup_storage --> /storage/clean
    /mock_params --> /traffic
* The binary body of a mock configuration request must now be an encoded dict
* Strict validation of POST requests
* The client was moved into a separate directory (`/client/client.py`)
* The server runs through uvicorn (ASGI) instead of gunicorn (WSGI)
* FastAPI was integrated in place of Flask
* Any request can now be mocked (the path is passed as a route argument)
* The internal mock storage now only serves an informational purpose, while the mocks themselves are added dynamically through FastAPI

Version 1.0.10
==============

* When a request is intercepted, its headers are recorded in mock_params

Version 1.0.9
=============

* Removed unnecessary dependencies

Version 1.0.8
=============

* Interception of requests without endpoints and recording of their data in a dedicated place
* More methods supported for request interception
* Changed the log format

Version 1.0.7
=============

* Encode binary data as latin-1 for storage inside the proxy mock

Version 1.0.6
=============

* Fixed a bug when reading the request parameter storage

Version 1.0.5
=============

* Added the ability to proxy requests to a preconfigured host
* A new key appeared in the `/configure` and `/configure/binary` endpoints: `proxy_host`
* Added unit tests for the new and the existing functionality
* Updated the service documentation

Version 1.0.4
=============

* Added a new `/configure/binary` endpoint for configuring mocks with binary content
* Added the ability to read data from the stores by a given key
* Added the ability to delete data from the stores by a given key

Version 1.0.3
=============

* Added the git module to the base Docker image
* Hid unused dependencies of the client library

Version 1.0.2
=============

* Allowed Python from version 3.9 onwards
* Lowered dependency versions for maximum compatibility with other projects
* Raised the poetry version to 1.8.2

Version 1.0.1
=============

* Added the proxy mock client
* Added tests for the proxy mock server
* CI can run tests and linters, and build and publish the library
* Added code linting
