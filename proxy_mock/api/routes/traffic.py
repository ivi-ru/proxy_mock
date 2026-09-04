import json

from aiocache import Cache
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from proxy_mock.domain.models import TrafficSettingsSchema

router = APIRouter()


def _traffic_settings(request: Request) -> dict:
    return {
        "record_unknown_traffic": request.app.state.record_unknown_traffic,
        "max_items": request.app.state.traffic_store.max_items,
    }


@router.get("/traffic")
async def get_traffic(request: Request):
    path = request.query_params.get("path")
    method = request.query_params.get("method")
    limit_raw = request.query_params.get("limit")
    limit = int(limit_raw) if limit_raw and limit_raw.isdigit() else None

    data = await request.app.state.traffic_store.list(path=path, method=method, limit=limit)
    return JSONResponse({"success": True, "count": len(data), "data": data}, 200)


@router.post("/traffic/clean")
async def clean_traffic(request: Request):
    await request.app.state.traffic_store.clear()
    return JSONResponse({"success": True, "data": []}, 200)


@router.get("/traffic/settings")
async def get_traffic_settings(request: Request):
    return JSONResponse({"success": True, "data": _traffic_settings(request)}, 200)


@router.post("/traffic/settings")
async def set_traffic_settings(request: Request):
    """Traffic recording settings, changeable without restarting the service.

    The update is partial: only the supplied fields are applied.
    """
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse({"success": False, "error": "The request body must be valid JSON"}, 400)

    try:
        settings = TrafficSettingsSchema.model_validate(payload)
    except ValidationError as err:
        return JSONResponse({"success": False, "error": json.loads(err.json())}, 422)

    changes = settings.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return JSONResponse(
            {"success": False, "error": "Provide at least one field: record_unknown_traffic, max_items"}, 422
        )

    if "record_unknown_traffic" in changes:
        request.app.state.record_unknown_traffic = changes["record_unknown_traffic"]

    if "max_items" in changes:
        await request.app.state.traffic_store.set_max_items(changes["max_items"])

    request.app.logger.info(f"Traffic settings updated: {changes}")

    return JSONResponse({"success": True, "data": _traffic_settings(request)}, 200)


@router.post("/cache/clean")
async def clean_cache(request: Request):
    await request.app.state.cache.close()
    request.app.state.cache = Cache(Cache.MEMORY, namespace="mocks")
    return JSONResponse({"success": True}, 200)
