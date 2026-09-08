# Runnable examples

[`test_http_dependency.py`](test_http_dependency.py) contains two complete integration tests:

- Configure an inventory response, make a real HTTP request, and check the response and recorded traffic.
- Export mock configuration to JSON, clear the original mocks, restore the snapshot, and request the restored endpoint.

## Run against an installed package

Requires Python 3.11 or newer. Save `test_http_dependency.py` in your working directory, then run
these commands in a virtual environment:

```bash
python -m pip install 'proxy_mock>=2.11,<3' pytest requests
python -m pytest -q test_http_dependency.py
```

Expected result: **2 passed**. No separate server, Docker, credentials, or external service is needed.
The installed pytest plugin starts a server on a free loopback port and resets mocks and traffic
after each test. The snapshot file is created in pytest's temporary directory.

In an application's own test, configure its HTTP dependency URL to use `proxy_mock_url` before
calling the application. These examples call that URL directly so they can run on their own.

## Run from this repository

```bash
uv sync --locked
uv run pytest -q examples/test_http_dependency.py
```

CI also copies the examples outside the repository and runs them against the built wheel. This
checks that the public package and its registered fixtures are sufficient to run the examples.

## Run an application and its mock in separate containers

The [Docker Compose example](compose/README.md) starts a tiny storefront and a separate
proxy-mock container, configures inventory data, and verifies both the storefront response and its
captured request. It includes start, check, and cleanup commands and explains container DNS
names versus host URLs.
