import os
from contextlib import asynccontextmanager

import httpx2
from aiocache import Cache
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from proxy_mock.api.routes.configure import router as configure_router
from proxy_mock.api.routes.service import router as service_router
from proxy_mock.api.routes.storage import router as storage_router
from proxy_mock.api.routes.traffic import router as traffic_router
from proxy_mock.core.logging import app_logger
from proxy_mock.core.settings import get_version_from_pyproject, record_unknown_traffic_default
from proxy_mock.repositories.traffic_store import TrafficStore
from proxy_mock.services.traffic_service import new_traffic_data
from proxy_mock.utils import log_request


def _proxy_timeout() -> float:
    raw = os.getenv("PROXY_MOCK_PROXY_TIMEOUT", "").strip()
    try:
        value = float(raw)
        return value if value > 0 else 30.0
    except ValueError:
        return 30.0


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    app.state.http_client = httpx2.AsyncClient(timeout=httpx2.Timeout(_proxy_timeout()))
    try:
        yield
    finally:
        await app.state.http_client.aclose()


class ProxyMockApp(FastAPI):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("lifespan", app_lifespan)
        super().__init__(*args, **kwargs)

        self.state.cache = Cache(Cache.MEMORY, namespace="mocks")
        self.state.traffic_store = TrafficStore()
        # Toggled at runtime via POST /traffic/settings, so it lives in state rather than in a module constant.
        self.state.record_unknown_traffic = record_unknown_traffic_default()
        self.logger = app_logger


def create_app() -> ProxyMockApp:
    app = ProxyMockApp(title="Proxy Mock")
    app.state.version = get_version_from_pyproject(app.logger)

    app.include_router(service_router)
    app.include_router(configure_router)
    app.include_router(storage_router)
    app.include_router(traffic_router)

    @app.middleware("http")
    @log_request
    async def request_middleware(request: Request, call_next):
        return await call_next(request)

    @app.exception_handler(404)
    async def custom_404_handler(request: Request, exc):
        app.logger.warning(f"No mock found for {request.url.path}")
        if app.state.record_unknown_traffic:
            try:
                await new_traffic_data(app, request, {"status_code": 404})
            except Exception as err:  # recording traffic must not break the 404 response
                app.logger.error(f"Failed to record traffic for the 404: {err}")
        return JSONResponse({"error": f"No mock found for {request.url.path}"}, 404)

    app.logger.info(f"Service routes: {sorted(collect_service_paths(app))}")

    return app


def collect_service_paths(app: FastAPI) -> set[str]:
    """Paths of the service endpoints.

    Since the FastAPI upgrade, routes added by include_router are nested in _IncludedRouter
    and have no top-level ``path`` attribute of their own, so we read them from original_router.
    """
    paths: set[str] = set()
    for route in app.routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            for inner in getattr(original_router, "routes", []):
                inner_path = getattr(inner, "path", None)
                if inner_path:
                    paths.add(inner_path)
        else:
            route_path = getattr(route, "path", None)
            if route_path:
                paths.add(route_path)
    return paths
