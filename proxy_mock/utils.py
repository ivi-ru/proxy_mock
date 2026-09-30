import asyncio
import json
import os
import time
from functools import wraps

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from proxy_mock.core.logging import app_logger
from proxy_mock.core.serializers import convert_bytes_to_str, formatted_data
from proxy_mock.services.cache_service import build_cache_key, cache_response
from proxy_mock.services.proxy_service import (
    ProxyRequestError,
    filter_proxy_response_headers,
    is_proxy_host_allowed,
    is_proxy_loop,
    proxy_request_to_host,
)
from proxy_mock.services.recordings import RecordingStore, recorded_response, response_headers
from proxy_mock.services.response_factory import make_response
from proxy_mock.services.rule_engine import apply_rules
from proxy_mock.services.sequences import ResponseSequence, SequenceExhausted
from proxy_mock.services.traffic_service import new_traffic_data

LOG_MODE = os.getenv("PROXY_MOCK_LOG_REQUESTS", "full").lower()


def log_request(func):
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        request_data = None
        if LOG_MODE == "full":
            request_data = await request.body()

        started = time.time()
        response = await func(request, *args, **kwargs)

        if LOG_MODE == "off":
            return response

        duration = round((time.time() - started) * 1000, 2)

        if LOG_MODE == "minimal":
            data = {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency": f"{duration}ms",
            }
        else:
            data = {
                "method": request.method,
                "path": request.url.path,
                "query": dict(request.query_params),
                "body": formatted_data(request_data) if request_data is not None else None,
                "headers": {h: v for h, v in request.headers.items()},
                "status": response.status_code,
                "latency": f"{duration}ms",
            }

        app_logger.info(f"Handled request {json.dumps(data, ensure_ascii=False)}")
        return response

    return wrapper


def apply_mocks_factory(
    app: FastAPI,
    mock_data: dict,
    sequences: dict[int | None, ResponseSequence] | None = None,
    recordings: RecordingStore | None = None,
):
    sequences = sequences or {}

    async def apply_mocks(request: Request):
        logger = app.logger
        http_client = app.state.http_client

        # Guard against proxying to self: this request has already passed through us.
        if is_proxy_loop(request):
            logger.warning(f"Proxy loop detected for {request.url.path}")
            return JSONResponse({"error": "Proxy loop detected"}, status_code=508)

        logger.info("Found a prepared response")
        await new_traffic_data(app, request, mock_data.get("extra_info"))

        # Method check (FastAPI route methods used to do this)
        allowed_methods = [str(m).upper() for m in (mock_data.get("methods") or [])]
        if allowed_methods and request.method.upper() not in allowed_methods:
            return JSONResponse({"error": f"Method {request.method} not allowed"}, status_code=405)

        recording_key = recording_request = recording_revision = None
        if recordings is not None:
            recording_key, recording_request, recording_revision = await recordings.identify(request)
            if mock_data["recording"]["mode"] == "replay":
                entry = await recordings.read(recording_key)
                if entry is None:
                    return JSONResponse(
                        {"error": {"code": "recording_not_found", "message": "No recording matches this request"}}, 404
                    )
                return recorded_response(entry["response"])

        # cache
        cache_time = mock_data.get("cache_time")
        cache_key = None
        if cache_time:
            cache_key = await build_cache_key(request, mock_data)
            cached_response = await app.state.cache.get(cache_key)
            if cached_response:
                logger.info("Returning a cached response")
                return Response(**cached_response)

        # proxy
        if proxy_host := mock_data.get("proxy_host"):
            if not is_proxy_host_allowed(proxy_host):
                logger.warning(f"Proxying to {proxy_host} is forbidden by the allowlist policy")
                return JSONResponse({"error": f"Proxy host {proxy_host} is not allowed"}, status_code=403)

            logger.info(f"Proxying request {request.url.path} to {proxy_host}")
            try:
                proxy_response = await proxy_request_to_host(request, proxy_host, http_client)
            except ProxyRequestError as err:
                # An unreachable host is no reason to cache the response or to return 500.
                logger.error(err.detail)
                return JSONResponse({"error": err.detail}, status_code=err.code)

            if recordings is not None:
                outcome = await recordings.save(recording_key, recording_request, proxy_response, recording_revision)
                response = Response(proxy_response.content, proxy_response.status_code)
                if request.method == "HEAD":
                    response.raw_headers = []
                response.raw_headers.extend(
                    (name.encode("latin-1"), value.encode("latin-1"))
                    for name, value in response_headers(
                        proxy_response.headers, preserve_length=request.method == "HEAD"
                    )
                )
                response.headers["X-Proxy-Mock-Recording"] = outcome
                return response

            response = Response(
                proxy_response.content,
                proxy_response.status_code,
                filter_proxy_response_headers(proxy_response.headers),
            )

            if cache_time and cache_key:
                await cache_response(app, cache_key, response, cache_time)

            return response

        timeout = mock_data.get("timeout") or 0
        try:
            if rules := mock_data.get("rules"):
                rule_response = await apply_rules(app, request, rules, sequences=sequences, delay=timeout)
                if rule_response is not None:
                    if cache_time and cache_key:
                        await cache_response(app, cache_key, rule_response, cache_time)
                    return rule_response
            response_data = await sequences[None].take() if None in sequences else mock_data["mock_data"]
        except SequenceExhausted as err:
            return JSONResponse({"error": {"code": "sequence_exhausted", "message": str(err)}}, 409)

        if timeout:
            logger.info(f"Request {request.url.path} has a configured delay: {timeout}s")
            await asyncio.sleep(timeout)

        # default mock response
        logger.debug(
            f"Returning the response for mock '{request.url.path}': "
            f"{json.dumps(convert_bytes_to_str(response_data), ensure_ascii=False)}"
        )
        response = make_response(response_data)

        if cache_time and cache_key:
            await cache_response(app, cache_key, response, cache_time)

        return response

    return apply_mocks
