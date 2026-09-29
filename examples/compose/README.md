> This checkout uses the unreleased administrative REST API. Build the image from this checkout;
> published 2.x images do not implement this contract. The Compose file builds `proxy-mock:local`
> by default.

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
Docker downloads the base images and builds proxy-mock from this checkout on the first run.

The GHCR package currently requires registry access; public visibility is disabled by the
organization. Building from the public repository above works without GHCR credentials.

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

## Use an image built from this checkout

Set `PROXY_MOCK_IMAGE` to the tag of an image built from this source tree. Published 2.x images
use the old administrative API and cannot run this checkout's check script.

CI overrides `PROXY_MOCK_IMAGE` with the image built from the current checkout and runs the same
start, check, and cleanup commands.
