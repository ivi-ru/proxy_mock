# Mock an HTTP dependency between containers

This example runs a tiny storefront in one container and proxy-mock in
another. A third, short-lived container configures inventory data, requests a product from the
storefront, and checks the response and the inventory request captured by proxy-mock.
The sample application and check use only Python's standard library.

Requires Docker with Docker Compose v2. From the repository root:

```bash
cd examples/compose
docker build -t proxy-mock-example ../..
export PROXY_MOCK_IMAGE=proxy-mock-example
docker compose up -d --wait proxy-mock app
docker compose run --rm check
docker compose down --remove-orphans
```

Expected output from the check:

```text
PASS: storefront response and captured inventory request
```

The check exits nonzero if either assertion fails. Run the cleanup command even after a failed
check. No persistent volumes, credentials, external APIs, or host Python packages are required.
Docker downloads the base images and builds proxy-mock from the repository on the first run.
The Compose file uses `proxy-mock:local` unless `PROXY_MOCK_IMAGE` names another image.

## Addresses inside and outside Docker

| Caller | Storefront | Mock dependency |
|--------|------------|-----------------|
| Another Compose container | `http://app:8000` | `http://proxy-mock:5000` |
| Your host | `http://127.0.0.1:18000` | `http://127.0.0.1:15000` |

`localhost` inside the storefront container means the storefront itself. The application uses
`INVENTORY_URL=http://proxy-mock:5000`, where `proxy-mock` is the Compose service's DNS name.
Only loopback ports are published on the host. Set `APP_PORT` or `PROXY_MOCK_PORT` before running
Compose if the default host ports are occupied.

After the check, you can inspect the configured response and recorded requests in
`http://127.0.0.1:15000/__admin/docs` before running cleanup. The check resets this dedicated instance's
mocks and traffic each time it runs, so it is safe to repeat.

## Use another image

Set `PROXY_MOCK_IMAGE` to the tag of an image built from a 3.x source tree. Images of 2.x use
the old administrative API and cannot run the check script.

CI overrides `PROXY_MOCK_IMAGE` with the image built from the commit under test and runs the
same start, check, and cleanup commands.

## Check the scripts on the host

`uv run --extra server pytest -q examples/test_storefront.py` from the repository root starts
the same application and check scripts against a local proxy-mock fixture. No Docker daemon
is required for that test; container DNS and networking are verified by the Compose run above.

For manual host runs, `app.py` reads `INVENTORY_URL`, `APP_HOST` (default `0.0.0.0`) and
`APP_PORT` (default `8000`). `check.py` reads `MOCK_URL`, `APP_URL` and
`PROXY_MOCK_ADMIN_PREFIX` (default `/__admin`), preserving the Compose addresses by default.
The check clears all mocks and traffic on its target instance, so use a dedicated test server.
