import copy

from fastapi import FastAPI
from starlette.routing import compile_path

from proxy_mock.client.migration import normalize_mock_path
from proxy_mock.core.serializers import convert_bytes_to_str
from proxy_mock.services.recordings import RecordingStore
from proxy_mock.services.sequences import build_sequences
from proxy_mock.utils import apply_mocks_factory


def validate_mock_path(app: FastAPI, path: str) -> str:
    """Validate before changing storage or routes, including during snapshot import."""
    normalized = normalize_mock_path(path)
    prefix = app.state.admin_prefix
    if normalized == prefix or normalized.startswith(prefix + "/"):
        raise ValueError(f"Mock path is inside the reserved administrative namespace: {prefix}")
    compile_path(normalized)
    return normalized


def _route_candidates(path: str) -> set[str]:
    normalized = normalize_mock_path(path)
    candidates = {normalized}
    if normalized != "/":
        candidates.add(normalized + "/")
    return candidates


def remove_runtime_routes(app: FastAPI, path: str) -> None:
    """Remove the dynamically added routes of a mock (the path and its trailing-slash variant)."""
    candidates = _route_candidates(path)
    app.state.sequences.pop(normalize_mock_path(path), None)
    recordings = app.state.recordings.pop(normalize_mock_path(path), None)
    if recordings is not None:
        recordings.retire()
    for route in list(app.routes):
        if getattr(route, "path", None) in candidates:
            app.routes.remove(route)


async def return_mock_data(app: FastAPI, path: str) -> dict | None:
    return await app.state.mock_storage.get_mock_data(path)


async def create_mock_data(app: FastAPI, **kwargs) -> dict:
    kwargs["path"] = normalize_mock_path(kwargs["path"])
    return await app.state.mock_storage.set_mock_data(**kwargs)


async def cleanup_storage(app: FastAPI) -> bool:
    """Full cleanup: drop the runtime routes of every mock, then clear the storage.

    Without removing the routes the path would keep answering with the mock, because the
    handler holds its data in a closure.
    """
    storage = await app.state.mock_storage.get_storage()
    for mock_path in list(storage.keys()):
        remove_runtime_routes(app, mock_path)
    return await app.state.mock_storage.clean_storage()


async def delete_mock_data(app: FastAPI, path: str) -> bool:
    return await app.state.mock_storage.delete_mock_data(path)


async def count_mocks(app: FastAPI) -> int:
    return await app.state.mock_storage.count()


async def return_storage(app: FastAPI) -> dict:
    storage = copy.deepcopy(await app.state.mock_storage.get_storage())
    for mock in storage.values():
        if isinstance(mock["mock_data"]["body"], bytes):
            mock["mock_data"]["body"] = str(mock["mock_data"]["body"])
    return storage


async def mock_initialization(
    app: FastAPI,
    mock_data: dict,
    *,
    preserve_sequences: set | None = None,
    preserve_recordings: bool = False,
    recording_entries: list[dict] | None = None,
):
    mock_data["path"] = validate_mock_path(app, mock_data["path"])
    await create_mock_data(app, **mock_data)

    normalized_path = normalize_mock_path(mock_data["path"])
    previous = app.state.sequences.get(normalized_path, {})
    old_recordings = app.state.recordings.get(normalized_path) if preserve_recordings else None
    remove_runtime_routes(app, normalized_path)

    recordings = None
    if config := mock_data.get("recording"):
        recordings = RecordingStore(config, old_recordings, entries=recording_entries)
        app.state.recordings[normalized_path] = recordings
    states = build_sequences(mock_data, previous, preserve_sequences or set())
    app.state.sequences[normalized_path] = states
    handler = apply_mocks_factory(app, mock_data, states, recordings)
    app.add_api_route(normalized_path, handler, methods=mock_data["methods"])

    if normalized_path != "/":
        app.add_api_route(normalized_path + "/", handler, methods=mock_data["methods"])

    return {
        "success": True,
        "path": normalized_path,
        "data": convert_bytes_to_str(mock_data),
    }
