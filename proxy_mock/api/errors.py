"""One error representation for every administrative resource."""

from math import isfinite

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def safe_error_data(value):
    """Keep diagnostics JSON-safe even when msgpack input contains arbitrary bytes."""
    if isinstance(value, dict):
        return {safe_error_data(str(key)): safe_error_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [safe_error_data(item) for item in value]
    if isinstance(value, str):
        return value.encode("utf-8", errors="backslashreplace").decode("utf-8")
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    # bytes must retain their octets; validation context may also contain exceptions.
    return safe_error_data(str(value))


def api_error(status: int, code: str, message: str, details=None) -> HTTPException:
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return HTTPException(status, detail=error)


async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if not isinstance(detail, dict) or "code" not in detail:
        detail = {"code": f"http_{exc.status_code}", "message": str(detail)}
    headers = dict(exc.headers or {})
    if exc.status_code == 405:
        path = request.scope["path"].removeprefix(request.scope.get("root_path", ""))
        methods = request.app.openapi()["paths"].get(path, {})
        if methods:
            allowed = {method.upper() for method in methods}
            if "GET" in allowed:
                allowed.add("HEAD")
            headers["Allow"] = ", ".join(sorted(allowed))
    return JSONResponse({"success": False, "error": safe_error_data(detail)}, exc.status_code, headers=headers)


async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return await http_error(request, api_error(422, "validation_error", "Invalid request", exc.errors()))
