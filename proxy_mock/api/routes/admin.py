"""Resource-oriented administrative API, isolated from user-defined HTTP routes."""

import json
import platform
from copy import deepcopy
from http import HTTPMethod
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from proxy_mock.api.errors import api_error
from proxy_mock.api.openapi import body_documentation, inline_schema, mock_documentation, snapshot_documentation
from proxy_mock.api.schemas import (
    DataResponse,
    ErrorResponse,
    MockResource,
    MockResponse,
    SequenceStatePatch,
    SuccessResponse,
)
from proxy_mock.client.migration import normalize_mock_path
from proxy_mock.core.serializers import convert_bytes_to_str
from proxy_mock.domain.constants import ParseError
from proxy_mock.domain.models import TrafficSettingsSchema
from proxy_mock.services.mock_service import (
    cleanup_storage,
    count_mocks,
    delete_mock_data,
    mock_initialization,
    remove_runtime_routes,
    return_mock_data,
    return_storage,
    validate_mock_path,
)
from proxy_mock.services.request_parser import parse_configure
from proxy_mock.services.snapshot import SnapshotError, export_snapshot, import_snapshot

router = APIRouter(responses={code: {"model": ErrorResponse} for code in (400, 404, 405, 409, 415, 422)})
PATH_QUERY = Query(None, description="Mock identity. Omit only to read or delete the entire collection.")


def selected_path(path: str | None, required: bool = False) -> str | None:
    if path is None and not required:
        return None
    try:
        return normalize_mock_path(path)
    except (TypeError, ValueError) as err:
        raise api_error(422, "invalid_path", "Provide a non-empty mock path") from err


def check_query(request: Request, allowed: set[str]) -> None:
    keys = list(request.query_params)
    if set(keys) - allowed or any(len(request.query_params.getlist(key)) != 1 for key in keys):
        raise api_error(422, "invalid_query", "Unknown or repeated query parameter")


async def payload(request: Request) -> dict:
    try:
        value = await parse_configure(request)
    except ParseError as err:
        raise api_error(err.code, "invalid_body", str(err.detail)) from err
    if not isinstance(value, dict):
        raise api_error(422, "invalid_body", "The request body must be an object")
    return value


def validate_mock(request: Request, data: dict) -> dict:
    unknown = set(data) - MockResource.model_fields.keys()
    if unknown:
        raise api_error(422, "invalid_mock", "Unknown mock fields", sorted(unknown))
    try:
        value = MockResource.model_validate(data).model_dump()
        value["path"] = validate_mock_path(request.app.state.mock_app, data["path"])
        return value
    except ValidationError as err:
        raise api_error(422, "invalid_mock", "Invalid mock configuration", json.loads(err.json())) from err
    except (ValueError, TypeError, AssertionError) as err:
        raise api_error(422, "invalid_path", str(err)) from err


async def mock_payload(request: Request, path: str | None) -> tuple[str, dict]:
    check_query(request, {"path"})
    identity = selected_path(path, required=True)
    data = await payload(request)
    if "path" in data and selected_path(data["path"], required=True) != identity:
        raise api_error(422, "path_mismatch", "Body path must match the resource URI")
    data["path"] = identity
    return identity, data


@router.get("")
@router.get("/", include_in_schema=False)
async def service_info(request: Request):
    check_query(request, set())
    state = request.app.state
    return {
        "success": True,
        "version": state.version,
        "python_version": platform.python_version(),
        "mocks_count": await count_mocks(),
        "traffic_count": await state.traffic_store.count(),
        "traffic_max_items": state.traffic_store.max_items,
    }


@router.get("/mocks", response_model=DataResponse)
async def get_mocks(request: Request, path: str | None = PATH_QUERY):
    check_query(request, {"path"})
    identity = selected_path(path)
    async with request.app.state.admin_lock:
        data = await return_storage() if identity is None else await return_mock_data(identity)
    if data is None:
        raise api_error(404, "mock_not_found", f"No mock found for {identity}")
    return JSONResponse({"success": True, "data": convert_bytes_to_str(data)})


@router.put(
    "/mocks",
    response_model=MockResponse,
    responses={201: {"model": MockResponse, "description": "Mock created; Location identifies its URI"}},
    openapi_extra=mock_documentation(),
)
async def put_mock(request: Request, path: str = Query(..., min_length=1)):
    identity, data = await mock_payload(request, path)
    value = validate_mock(request, data)
    async with request.app.state.admin_lock:
        existed = await return_mock_data(identity) is not None
        result = await mock_initialization(request.app.state.mock_app, value)
    location = request.scope.get("root_path", "") + request.app.state.admin_prefix + "/mocks?"
    location += urlencode({"path": identity})
    return JSONResponse(result, 200 if existed else 201, headers={"Location": location})


@router.patch("/mocks", response_model=MockResponse, openapi_extra=mock_documentation())
async def patch_mock(request: Request, path: str = Query(..., min_length=1)):
    identity, changes = await mock_payload(request, path)
    async with request.app.state.admin_lock:
        saved = await return_mock_data(identity)
        if saved is None:
            raise api_error(404, "mock_not_found", f"No mock found for {identity}")
        # Bodies, headers and arrays are values, not recursive merge documents.
        # [] replaces rules and null clears a nullable field, including the response body.
        merged = deepcopy(saved)
        if isinstance(changes.get("mock_data"), dict):
            merged["mock_data"].update(changes["mock_data"])
        merged.update({key: value for key, value in changes.items() if key != "mock_data"})
        if "mock_data" in changes and not isinstance(changes["mock_data"], dict):
            raise api_error(422, "invalid_mock", "mock_data must be an object")
        value = validate_mock(request, merged)
        preserve = set()
        if "sequence" not in changes:
            preserve.add(None)
        if "rules" not in changes:
            preserve.update(range(len(value.get("rules") or [])))
        old_recording, new_recording = saved.get("recording"), value.get("recording")
        preserve_recordings = bool(
            old_recording
            and new_recording
            and old_recording["match_headers"] == new_recording["match_headers"]
            and saved.get("proxy_host") == value.get("proxy_host")
        )
        result = await mock_initialization(
            request.app.state.mock_app,
            value,
            preserve_sequences=preserve,
            preserve_recordings=preserve_recordings,
        )
    return JSONResponse(result)


@router.delete("/mocks", response_model=DataResponse)
async def delete_mocks(request: Request, path: str | None = PATH_QUERY):
    check_query(request, {"path"})
    identity = selected_path(path)
    app = request.app.state.mock_app
    async with request.app.state.admin_lock:
        if identity is None:
            await cleanup_storage(app)
        else:
            if not await delete_mock_data(identity):
                raise api_error(404, "mock_not_found", f"No mock found for {identity}")
            remove_runtime_routes(app, identity)
        data = await return_storage()
    return JSONResponse({"success": True, "data": convert_bytes_to_str(data)})


@router.get("/traffic", response_model=DataResponse)
async def get_traffic(
    request: Request,
    path: str | None = None,
    method: HTTPMethod | None = None,
    limit: int | None = Query(None, gt=0),
):
    check_query(request, {"path", "method", "limit"})
    data = await request.app.state.traffic_store.list(path=path, method=method, limit=limit)
    return JSONResponse({"success": True, "count": len(data), "data": data})


@router.delete("/traffic", response_model=DataResponse)
async def delete_traffic(request: Request):
    check_query(request, set())
    await request.app.state.traffic_store.clear()
    return {"success": True, "data": []}


def settings(request: Request) -> dict:
    return {
        "record_unknown_traffic": request.app.state.record_unknown_traffic,
        "max_items": request.app.state.traffic_store.max_items,
    }


@router.get("/settings", response_model=DataResponse)
async def get_settings(request: Request):
    check_query(request, set())
    return {"success": True, "data": settings(request)}


@router.patch(
    "/settings",
    response_model=DataResponse,
    openapi_extra=body_documentation(inline_schema(TrafficSettingsSchema), "Partial traffic settings update."),
)
async def patch_settings(request: Request):
    check_query(request, set())
    data = await payload(request)
    if not data or set(data) - TrafficSettingsSchema.model_fields.keys() or any(v is None for v in data.values()):
        raise api_error(422, "invalid_settings", "Provide record_unknown_traffic and/or a positive max_items")
    try:
        changes = TrafficSettingsSchema.model_validate(data).model_dump(exclude_unset=True)
    except ValidationError as err:
        raise api_error(422, "invalid_settings", "Invalid traffic settings", json.loads(err.json())) from err
    async with request.app.state.admin_lock:
        if "max_items" in changes:
            await request.app.state.traffic_store.set_max_items(changes["max_items"])
        if "record_unknown_traffic" in changes:
            request.app.state.record_unknown_traffic = changes["record_unknown_traffic"]
        return {"success": True, "data": settings(request)}


@router.get("/snapshot")
async def get_snapshot(request: Request):
    check_query(request, set())
    try:
        async with request.app.state.admin_lock:
            return JSONResponse(await export_snapshot(request.app.state.version))
    except SnapshotError as err:
        raise api_error(err.code, "unsupported_snapshot", str(err.detail)) from err


async def sequence_state(request: Request, path: str, rule: int | None, *, reset: bool = False) -> dict:
    check_query(request, {"path", "rule"})
    identity = selected_path(path, required=True)
    async with request.app.state.admin_lock:
        sequence = request.app.state.sequences.get(identity, {}).get(rule)
        if sequence is None:
            raise api_error(404, "sequence_not_found", "No response sequence found for this mock or rule")
        return {"success": True, "data": await sequence.state(reset=reset)}


@router.get("/sequence-state", response_model=DataResponse)
async def get_sequence_state(
    request: Request, path: str = Query(..., min_length=1), rule: int | None = Query(None, ge=0)
):
    return await sequence_state(request, path, rule)


@router.patch(
    "/sequence-state",
    response_model=DataResponse,
    openapi_extra=body_documentation(inline_schema(SequenceStatePatch), "Set position to zero to restart a sequence."),
)
async def patch_sequence_state(
    request: Request, path: str = Query(..., min_length=1), rule: int | None = Query(None, ge=0)
):
    data = await payload(request)
    try:
        SequenceStatePatch.model_validate(data)
    except ValidationError as err:
        raise api_error(422, "invalid_sequence_state", "Position must be zero", json.loads(err.json())) from err
    return await sequence_state(request, path, rule, reset=True)


@router.put("/snapshot", response_model=DataResponse, openapi_extra=snapshot_documentation())
@router.patch("/snapshot", response_model=DataResponse, openapi_extra=snapshot_documentation())
async def update_snapshot(request: Request):
    check_query(request, set())
    data = await payload(request)
    mode = "replace" if request.method == "PUT" else "merge"
    try:
        async with request.app.state.admin_lock:
            result = await import_snapshot(request.app.state.mock_app, data, mode)
    except SnapshotError as err:
        raise api_error(err.code, "invalid_snapshot", "Invalid mock snapshot", err.detail) from err
    return {"success": True, "data": result}


@router.delete("/cache", response_model=SuccessResponse)
async def delete_cache(request: Request):
    """Temporary resource until the separately planned cache removal."""
    check_query(request, set())
    await request.app.state.cache.clear()
    return {"success": True}


@router.get("/recordings", response_model=DataResponse)
@router.delete("/recordings", response_model=DataResponse)
async def recordings(
    request: Request, path: str = Query(..., min_length=1), id: str | None = Query(None, pattern=r"^[0-9a-f]{64}$")
):
    """Read or delete a mock's recording collection, or one entry selected by its id."""
    check_query(request, {"path", "id"})
    identity = selected_path(path, required=True)
    async with request.app.state.admin_lock:
        store = request.app.state.recordings.get(identity)
        if store is None:
            raise api_error(404, "recordings_not_found", "No record/replay configuration found for this mock")
        if request.method == "DELETE":
            if not await store.delete(id):
                raise api_error(404, "recording_not_found", "No recording found for this id")
            return {"success": True, "data": []}
        data = await store.read(id)
        if data is None:
            raise api_error(404, "recording_not_found", "No recording found for this id")
        return {"success": True, "data": data}
