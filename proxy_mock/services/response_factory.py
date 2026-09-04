from fastapi import Response
from fastapi.responses import JSONResponse


def make_response(mock_data: dict) -> Response | JSONResponse:
    if mock_data["body"] is None:
        return Response(mock_data["body"], mock_data["status_code"], mock_data["headers"])

    if isinstance(mock_data["body"], bytes):
        return Response(
            mock_data["body"],
            mock_data["status_code"],
            mock_data["headers"],
            media_type="application/protobuf",
        )

    if isinstance(mock_data["body"], str):
        return Response(
            mock_data["body"],
            mock_data["status_code"],
            mock_data["headers"],
            media_type="text/html; charset=utf-8",
        )

    return JSONResponse(mock_data["body"], mock_data["status_code"], mock_data["headers"])
