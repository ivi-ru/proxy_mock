import asyncio
import json

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from proxy_mock.core.serializers import convert_bytes_to_str, formatted_data
from proxy_mock.services.proxy_service import (
    ProxyRequestError,
    filter_proxy_response_headers,
    is_proxy_host_allowed,
    proxy_request_to_host,
)
from proxy_mock.services.response_factory import make_response


async def apply_rules(app: FastAPI, request: Request, rules: list) -> Response | JSONResponse | None:
    logger = app.logger
    http_client = app.state.http_client

    request_body = await request.body()
    request_headers = dict(request.headers)
    request_query = dict(request.query_params)

    rules_sorted = sorted(
        rules,
        key=lambda r: (int(r.get("priority", 0)), float(r.get("timestamp", 0))),
        reverse=True,
    )

    for rule in rules_sorted:
        rule_conditions = rule["input_data"]

        rule_body = rule_conditions.get("body", {})
        rule_headers = rule_conditions.get("headers", {})
        rule_query = rule_conditions.get("query", {})
        rule_methods = [str(m).upper() for m in (rule_conditions.get("methods", []) or [])]
        rule_timeout = rule_conditions.get("timeout", 0.0)
        rule_proxy_host = rule_conditions.get("proxy_host", "")

        if rule_methods and request.method.upper() not in rule_methods:
            continue

        if rule_body:
            if not (request_body == rule_body or formatted_data(request_body) == rule_body):
                continue

        if rule_headers and not (rule_headers.items() <= request_headers.items()):
            continue

        if rule_query:
            str_query = {str(k): str(v) for k, v in request_query.items()}
            str_rule_query = {str(k): str(v) for k, v in rule_query.items()}
            if not (str_rule_query.items() <= str_query.items()):
                continue

        await app.state.traffic_store.patch_last({"rule_extra_info": convert_bytes_to_str(rule.get("extra_info", {}))})

        if rule_proxy_host:
            if not is_proxy_host_allowed(rule_proxy_host):
                logger.warning(f"Proxying to {rule_proxy_host} is forbidden by the allowlist policy")
                return JSONResponse({"error": f"Proxy host {rule_proxy_host} is not allowed"}, status_code=403)

            try:
                proxy_response = await proxy_request_to_host(request, rule_proxy_host, http_client)
            except ProxyRequestError as err:
                logger.error(err.detail)
                return JSONResponse({"error": err.detail}, status_code=err.code)

            logger.info("Received a response from the upstream host")
            return Response(
                proxy_response.content,
                proxy_response.status_code,
                filter_proxy_response_headers(proxy_response.headers),
            )

        if rule_timeout:
            await asyncio.sleep(rule_timeout)

        logger.debug(f"Returning the rule response: {json.dumps(convert_bytes_to_str(rule['output_data']))}")
        return make_response(rule["output_data"])

    logger.debug("No rule matched")
    return None
