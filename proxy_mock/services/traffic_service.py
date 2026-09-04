from fastapi import FastAPI, Request

from proxy_mock.core.serializers import convert_bytes_to_str, formatted_data
from proxy_mock.core.time import now_msk_iso
from proxy_mock.domain.models import InputRequestSchema


async def get_request_data(request: Request) -> dict:
    request_body = formatted_data(await request.body())
    request_headers = {header: value for header, value in request.headers.items()}

    return InputRequestSchema(
        request_method=request.method,
        request_body=request_body,
        request_headers=request_headers,
        request_path=request.url.path,
        request_query=dict(request.query_params),
    ).model_dump()


async def new_traffic_data(app: FastAPI, request: Request, extra_info: dict | None = None) -> None:
    request_data = await get_request_data(request)
    request_data["extra_info"] = convert_bytes_to_str(extra_info or {})
    request_data["requested_at"] = now_msk_iso()

    await app.state.traffic_store.add(request_data)
