import json

import msgpack
from fastapi import Request

from proxy_mock.domain.constants import ConfigureContentTypes, ParseError


async def parse_configure(request: Request) -> dict:
    input_data = await request.body()
    if not input_data:
        raise ParseError("No request data", 400)

    content_type = request.headers.get("content-type")

    match content_type:
        case ConfigureContentTypes.JSON:
            try:
                return json.loads(input_data)
            except json.JSONDecodeError as err:
                raise ParseError(f"Parse error: {err}", 400)
        case ConfigureContentTypes.BINARY:
            try:
                return msgpack.unpackb(input_data)
            # On malformed data msgpack raises FormatError (UnpackException), ExtraData and
            # ValueError, so catch everything: otherwise the client gets a 500 instead of a clear 400.
            except (msgpack.UnpackException, ValueError) as err:
                raise ParseError(f"Parse error: {err}", 400)
        case _:
            raise ParseError(f"Unsupported content type: {content_type}", 415)
