import asyncio
import os
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from proxy_mock.api.errors import http_error, validation_error
from proxy_mock.api.routes.admin import router as admin_router
from proxy_mock.client.migration import validate_admin_prefix
from proxy_mock.core.logging import app_logger
from proxy_mock.core.settings import get_version_from_pyproject, record_unknown_traffic_default
from proxy_mock.repositories.mock_storage import MockStorage
from proxy_mock.repositories.traffic_store import TrafficStore
from proxy_mock.services.snapshot import import_snapshot
from proxy_mock.services.traffic_service import new_traffic_data
from proxy_mock.utils import log_request


def _proxy_timeout() -> float:
    raw = os.getenv("PROXY_MOCK_PROXY_TIMEOUT", "").strip()
    try:
        value = float(raw)
        return value if value > 0 else 30.0
    except ValueError:
        return 30.0


async def _preload_snapshot(app: FastAPI) -> None:
    """Load the snapshot passed to the CLI.

    It runs here rather than before uvicorn starts, because the storage lock belongs to the
    loop that first uses it — the serving loop.
    """
    snapshot = getattr(app.state, "preload_snapshot", None)
    if not snapshot:
        return

    result = await import_snapshot(app, snapshot, mode="replace")
    app.logger.info(f"Preloaded {result['imported']} mocks from a snapshot")


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    app.state.http_client = httpx2.AsyncClient(timeout=httpx2.Timeout(_proxy_timeout()))
    try:
        await _preload_snapshot(app)
        yield
    finally:
        await app.state.http_client.aclose()


class ProxyMockApp(FastAPI):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("lifespan", app_lifespan)
        super().__init__(*args, **kwargs)

        self.state.mock_storage = MockStorage()
        self.state.traffic_store = TrafficStore()
        self.state.admin_lock = asyncio.Lock()
        self.state.sequences = {}
        self.state.recordings = {}
        # Settings belong to the instance and may change without a restart.
        self.state.record_unknown_traffic = record_unknown_traffic_default()
        # Filled in by the CLI when it is given --mocks; applied during startup.
        self.state.preload_snapshot = None
        self.logger = app_logger


class AdminDispatch:
    """Reserve the entire namespace before FastAPI considers any user mock route.

    This also protects unknown administrative paths and unsupported methods from wildcard
    mocks. No assumptions about FastAPI's representation of included routers are needed.
    """

    def __init__(self, app: ASGIApp, admin: ASGIApp, prefix: str):
        self.app, self.admin, self.prefix = app, admin, prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        root = scope.get("root_path", "")
        if root and (path == root or path.startswith(root + "/")):
            path = path[len(root) :]
        target = self.app
        if scope["type"] == "http" and (path == self.prefix or path.startswith(self.prefix + "/")):
            target = self.admin
            head = scope["method"] == "HEAD"
            if head:
                scope = {**scope, "method": "GET"}

            async def admin_send(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"cache-control", b"no-store"))
                    if path in {
                        self.prefix + suffix for suffix in ("/mocks", "/settings", "/snapshot", "/sequence-state")
                    }:
                        headers.append((b"accept-patch", b"application/json, application/octet-stream"))
                    message = {**message, "headers": headers}
                elif head and message["type"] == "http.response.body":
                    message = {**message, "body": b""}
                await send(message)

            await target(scope, receive, admin_send)
        else:
            await target(scope, receive, send)


def create_app() -> ProxyMockApp:
    app = ProxyMockApp(title="Proxy Mock", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.version = get_version_from_pyproject(app.logger)
    app.state.admin_prefix = validate_admin_prefix(os.getenv("PROXY_MOCK_ADMIN_PREFIX"))
    app.state.mock_app = app
    prefix = app.state.admin_prefix
    admin = FastAPI(
        title="Proxy Mock administrative API",
        version=app.state.version,
        docs_url=prefix + "/docs",
        redoc_url=prefix + "/redoc",
        openapi_url=prefix + "/openapi.json",
        swagger_ui_oauth2_redirect_url=prefix + "/docs/oauth2-redirect",
    )
    admin.state = app.state
    admin.logger = app.logger
    admin.include_router(admin_router, prefix=prefix)
    admin.add_exception_handler(HTTPException, http_error)
    admin.add_exception_handler(RequestValidationError, validation_error)
    app.state.admin_app = admin
    app.openapi = admin.openapi

    @app.middleware("http")
    @log_request
    async def request_middleware(request: Request, call_next):
        return await call_next(request)

    app.add_middleware(AdminDispatch, admin=admin, prefix=prefix)

    @app.exception_handler(404)
    async def custom_404_handler(request: Request, exc):
        app.logger.warning(f"No mock found for {request.url.path}")
        if app.state.record_unknown_traffic:
            try:
                await new_traffic_data(app, request, {"status_code": 404})
            except Exception as err:  # recording traffic must not break the 404 response
                app.logger.error(f"Failed to record traffic for the 404: {err}")
        return JSONResponse({"error": f"No mock found for {request.url.path}"}, 404)

    app.logger.info(f"Administrative API: {prefix}")

    return app
