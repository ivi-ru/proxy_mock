"""Opt-in 3.0 resource paths, retaining the existing 2.x request/response contracts."""

from fastapi import APIRouter

from proxy_mock.api.routes import configure, service, storage, traffic


def create_admin_router(prefix: str) -> APIRouter:
    router = APIRouter()
    # Keep the full paths on the original router: runtime mock cleanup must never remove them.
    for suffix, method, endpoint in [
        ("", "GET", service.get_proxy_mock),
        ("/mocks", "POST", configure.configure_mock),
        ("/mocks", "PATCH", configure.patch_mock_configuration),
        ("/mocks", "GET", storage.get_storage),
        ("/mocks", "DELETE", storage.delete_storage),
        ("/traffic", "GET", traffic.get_traffic),
        ("/traffic", "DELETE", traffic.delete_traffic),
        ("/settings", "GET", traffic.get_traffic_settings),
        ("/settings", "PATCH", traffic.patch_traffic_settings),
        ("/snapshot", "GET", storage.get_storage_snapshot),
        ("/snapshot", "POST", storage.post_storage_snapshot),
    ]:
        router.add_api_route(prefix + suffix, endpoint, methods=[method], name="admin_" + endpoint.__name__)
    return router
