import hashlib
import json

from fastapi import FastAPI, Request, Response


async def get_request_body_hash(request: Request) -> str:
    body = await request.body()
    if not body:
        return "empty"

    try:
        json_body = await request.json()
        normalized_json = json.dumps(json_body, sort_keys=True, separators=(",", ":"))
        return hashlib.md5(normalized_json.encode()).hexdigest()[:8]
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
        return hashlib.md5(body).hexdigest()[:8]


async def build_cache_key(request: Request, mock_data: dict) -> str:
    base_key = f"mock:{mock_data['path']}:method:{request.method}"

    if request.query_params:
        sorted_params = sorted(request.query_params.items())
        param_str = ":".join(f"{k}={v}" for k, v in sorted_params)
        base_key = f"{base_key}:query:{param_str}"

    body_hash = await get_request_body_hash(request)
    if body_hash:
        base_key = f"{base_key}:body:{body_hash}"

    return base_key


async def cache_response(app: FastAPI, key: str, response: Response, ttl: int):
    cache = app.state.cache
    try:
        cache_data = {
            "content": response.body,
            "status_code": response.status_code,
            "headers": {k: v for k, v in response.headers.items()},
        }
        await cache.set(key, cache_data, ttl=ttl)
        app.logger.info(f"Response cached under key {key} for {ttl} seconds")
    except Exception as e:
        app.logger.error(f"Caching error: {e}")
