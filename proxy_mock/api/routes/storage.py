from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from proxy_mock.core.serializers import convert_bytes_to_str
from proxy_mock.services.mock_service import (
    cleanup_storage,
    delete_mock_data,
    remove_runtime_routes,
    return_mock_data,
    return_storage,
)

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


@router.post("/storage/clean")
async def clean_storage(request: Request):
    """Deprecated alias for deleting mocks. The RESTful variant is `DELETE /storage`."""
    path = request.query_params.get("path")

    if path:
        remove_runtime_routes(request.app, path)
        result = await delete_mock_data(path)
    else:
        result = await cleanup_storage(request.app)

    return JSONResponse({"success": result, "data": convert_bytes_to_str(await return_storage())}, 200)
