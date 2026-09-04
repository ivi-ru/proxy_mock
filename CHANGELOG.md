Migrating from 1.0.1
====================

The previously published 1.0.1 (Flask) and the current 2.10.1 (FastAPI) are not compatible.
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
of gunicorn.

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
