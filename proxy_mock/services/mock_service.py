import copy

from fastapi import FastAPI

from proxy_mock.core.deprecation import warn_deprecated_field
from proxy_mock.core.serializers import convert_bytes_to_str
from proxy_mock.repositories.mock_storage import mock_storage
from proxy_mock.utils import apply_mocks_factory


def normalize_path(path: str) -> str:
    path = (path or "").split("?")[0].strip()
    if not path.startswith("/"):
        path = "/" + path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path


def _route_candidates(path: str) -> set[str]:
    normalized = normalize_path(path)
    candidates = {normalized}
    if normalized != "/":
        candidates.add(normalized + "/")
    return candidates


def remove_runtime_routes(app: FastAPI, path: str) -> None:
    """Remove the dynamically added routes of a mock (the path and its trailing-slash variant)."""
    candidates = _route_candidates(path)
    for route in list(app.routes):
        if getattr(route, "path", None) in candidates:
            app.routes.remove(route)


async def return_mock_data(path: str) -> dict | None:
    return await mock_storage.get_mock_data(path)


async def create_mock_data(**kwargs) -> dict:
    kwargs["path"] = normalize_path(kwargs["path"])
    return await mock_storage.set_mock_data(**kwargs)


async def cleanup_storage(app: FastAPI) -> bool:
    """Full cleanup: drop the runtime routes of every mock, then clear the storage.

    Without removing the routes the path would keep answering with the mock, because the
    handler holds its data in a closure.
    """
    storage = await mock_storage.get_storage()
    for mock_path in list(storage.keys()):
        remove_runtime_routes(app, mock_path)
    return await mock_storage.clean_storage()


async def delete_mock_data(path: str) -> bool:
    return await mock_storage.delete_mock_data(path)


async def patch_mock_data(old: dict, new: dict) -> dict:
    old_rules = old.get("rules") or []
    new_rules = new.get("rules") or []
    merged_rules = [item for item in new_rules if item not in old_rules] + old_rules

    old.update(new)
    old["rules"] = merged_rules
    old["path"] = normalize_path(old["path"])

    saved = await mock_storage.set_mock_data(**old)
    old.update(saved)
    return old


async def count_mocks() -> int:
    return await mock_storage.count()


async def return_storage() -> dict:
    storage = copy.deepcopy(await mock_storage.get_storage())
    for mock in storage.values():
        if isinstance(mock["mock_data"]["body"], bytes):
            mock["mock_data"]["body"] = str(mock["mock_data"]["body"])
    return storage


async def mock_initialization(app: FastAPI, mock_data: dict):
    if mock_data.get("cache_time"):
        warn_deprecated_field("cache_time", "response caching is removed in 3.0")

    await create_mock_data(**mock_data)

    normalized_path = normalize_path(mock_data["path"])
    remove_runtime_routes(app, normalized_path)

    handler = apply_mocks_factory(app, mock_data)
    app.add_api_route(normalized_path, handler, methods=mock_data["methods"])

    if normalized_path != "/":
        app.add_api_route(normalized_path + "/", handler, methods=mock_data["methods"])

    return {
        "success": True,
        "path": normalized_path,
        "data": convert_bytes_to_str(mock_data),
    }
