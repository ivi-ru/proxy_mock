import platform

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from proxy_mock.services.mock_service import count_mocks

router = APIRouter()


@router.get("/proxy_mock")
async def get_proxy_mock(request: Request):
    app = request.app
    return JSONResponse(
        {
            "success": True,
            "version": app.state.version,
            "python_version": platform.python_version(),
            "mocks_count": await count_mocks(),
            "traffic_count": await app.state.traffic_store.count(),
            "traffic_max_items": app.state.traffic_store.max_items,
        },
        200,
    )
