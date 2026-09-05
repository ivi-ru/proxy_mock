from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from proxy_mock.core.deprecation import mark_deprecated
from proxy_mock.core.serializers import convert_bytes_to_str
from proxy_mock.services.mock_service import (
    cleanup_storage,
    delete_mock_data,
    remove_runtime_routes,
    return_mock_data,
    return_storage,
)
from proxy_mock.services.snapshot import SnapshotError, export_snapshot, import_snapshot

router = APIRouter()


@router.get("/storage")
async def get_storage(request: Request):
    path = request.query_params.get("path")
    data = await return_mock_data(path) if path else await return_storage()
    return JSONResponse({"success": True, "data": convert_bytes_to_str(data)}, 200)


@router.delete("/storage")
async def delete_storage(request: Request):
    """Delete mocks. Without `path` all of them; with `path` only that one (`404` if missing)."""
    path = request.query_params.get("path")

    if not path:
        result = await cleanup_storage(request.app)
        return JSONResponse({"success": result, "data": convert_bytes_to_str(await return_storage())}, 200)

    remove_runtime_routes(request.app, path)
    deleted = await delete_mock_data(path)
    if not deleted:
        return JSONResponse({"success": False, "error": f"No mock found for {path}"}, 404)

    return JSONResponse({"success": True, "data": convert_bytes_to_str(await return_storage())}, 200)


@router.get("/storage/snapshot")
async def get_storage_snapshot(request: Request):
    """Export every configured mock as a snapshot document.

    The response body is the snapshot itself rather than the usual `success`/`data` envelope, so
    that it can be saved to a file and fed back to `POST /storage/snapshot` or to
    `proxy-mock --mocks` unchanged.
    """
    return JSONResponse(await export_snapshot(request.app.state.version), 200)


@router.post("/storage/snapshot")
async def post_storage_snapshot(request: Request):
    """Load a snapshot into the running instance.

    `mode=merge` (the default) keeps the mocks that are already configured; `mode=replace`
    clears the storage first.
    """
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse({"success": False, "error": "The request body must be valid JSON"}, 400)

    mode = request.query_params.get("mode", "merge")

    try:
        result = await import_snapshot(request.app, payload, mode)
    except SnapshotError as err:
        return JSONResponse({"success": False, "error": err.detail}, err.code)

    request.app.logger.info(f"Loaded {result['imported']} mocks from a snapshot (mode={mode})")
    return JSONResponse({"success": True, "data": result}, 200)


@router.post("/storage/clean")
async def clean_storage(request: Request):
    """Deprecated alias for deleting mocks. The RESTful variant is `DELETE /storage`."""
    path = request.query_params.get("path")

    if path:
        remove_runtime_routes(request.app, path)
        result = await delete_mock_data(path)
    else:
        result = await cleanup_storage(request.app)

    response = JSONResponse({"success": result, "data": convert_bytes_to_str(await return_storage())}, 200)
    return mark_deprecated(response, "POST /storage/clean", "DELETE /storage")
