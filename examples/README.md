# Runnable examples

These examples target proxy-mock 3.0. 2.x servers and clients have a different administrative
HTTP API. No external API or credentials are needed.

## Run from this repository

Requires Python 3.11 or newer. From the repository root:

```bash
uv sync --locked --extra server
uv run --extra server pytest -q examples
```

Expected result: **7 passed**. The installed pytest plugin starts a server on a free loopback
port and resets mocks and traffic after each test. Temporary upstreams and application
processes shut down at the end of their tests; snapshot files use pytest's temporary directory.

| File | Tests | What it demonstrates |
|------|-------|----------------------|
| [test_http_dependency.py](test_http_dependency.py) | 2 | Inventory response and captured traffic; JSON snapshot round trip |
| [test_v3_workflows.py](test_v3_workflows.py) | 4 | REST create/patch/delete; sequence exhaustion/restart and binary snapshot; offline record/replay with cookies; async client |
| [test_storefront.py](test_storefront.py) | 1 | The Compose application and check scripts communicating over real loopback HTTP |

The record/replay example shuts down its upstream before restoring and replaying a snapshot.
A missing request key returns 404; deleting an entry prevents subsequent replay. No request
is sent to the stopped upstream. The sequence example shows that imported cursors restart
at zero rather than resuming the exported position.

In an application's own test, configure its HTTP dependency URL to use `proxy_mock_url`
before calling the application. The inventory examples call that URL directly so they can
run on their own.

## Run against an installed package

Install into a virtual environment, then copy the `examples` directory to another directory
before running pytest there:

```bash
python -m pip install 'proxy_mock[server]' pytest
```

CI builds the wheel and copies these examples outside the repository. This verifies that the
installed package and registered fixtures work without importing the source tree.

## Use a running instance or a custom prefix

A base install is sufficient for tests that only talk to a running server. Set
`PROXY_MOCK_URL` and, if needed, the same `PROXY_MOCK_ADMIN_PREFIX` as the server:

```bash
PROXY_MOCK_URL=http://127.0.0.1:5000 \
PROXY_MOCK_ADMIN_PREFIX=/test/admin \
  python -m pytest -q examples
```

Use a dedicated test instance: fixture teardown and the storefront check clear all its mocks
and traffic. The recording example starts its upstream at 127.0.0.1 on the test machine, so
proxy-mock must run on that same host and allow that upstream. For a server in another container
or machine, run only examples that do not start a host-local upstream, or provide a recording
upstream reachable from the server.

To check the default local fixture with a custom prefix:

```bash
PROXY_MOCK_ADMIN_PREFIX=/test/admin uv run --extra server pytest -q examples
```

## 2.x compatibility

Only [test_http_dependency.py](test_http_dependency.py) also works with 2.x. Copy that file
into a test directory and install `proxy_mock>=2.13,<3` plus pytest to stay on 2.x. The
sequence and recording examples require 3.0.

## Run an application and its mock in separate containers

The [Docker Compose example](compose/README.md) starts a tiny storefront and proxy-mock in
separate containers. Its start/check/cleanup commands verify container DNS and networking.
The loopback test above exercises the same scripts but does not validate Docker networking.
