import json
from copy import deepcopy

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from proxy_mock.domain.constants import ParseError
from proxy_mock.domain.models import ConfigureMockRequestSchema
from proxy_mock.services.mock_service import mock_initialization, patch_mock_data, return_mock_data
from proxy_mock.services.request_parser import parse_configure

router = APIRouter()


@router.post("/configure_mock")
async def configure_mock(request: Request):
    try:
        parsed_data = await parse_configure(request)
    except ParseError as err:
        return JSONResponse({"success": False, "error": err.detail}, err.code)

    try:
        validate_data = ConfigureMockRequestSchema.model_validate(parsed_data).model_dump()
    except ValidationError as err:
        return JSONResponse({"success": False, "error": json.loads(err.json())}, 422)

    response = await mock_initialization(request.app, validate_data)
    return JSONResponse(response, 201)


@router.patch("/configure_mock")
async def patch_mock_configuration(request: Request):
    try:
        parsed_data = await parse_configure(request)
    except ParseError as err:
        return JSONResponse({"success": False, "error": err.detail}, err.code)

    try:
        validate_data = ConfigureMockRequestSchema.model_validate(parsed_data).model_dump(exclude_unset=True)
    except ValidationError as err:
        return JSONResponse({"success": False, "error": json.loads(err.json())}, 422)

    saved_data = await return_mock_data(validate_data["path"])
    if not saved_data:
        return JSONResponse({"success": False, "error": f"There is no mock for {validate_data['path']}"}, 400)

    mock_data = deepcopy(await patch_mock_data(saved_data, validate_data))
    response = await mock_initialization(request.app, mock_data)
    return JSONResponse(response, 200)
