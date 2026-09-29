"""Request schemas for endpoints that accept both JSON and binary msgpack."""

from copy import deepcopy

from pydantic import BaseModel

from proxy_mock.api.schemas import MockResource


def inline_schema(model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def expand(value):
        if isinstance(value, list):
            return [expand(item) for item in value]
        if isinstance(value, dict):
            if "$ref" in value:
                return expand(deepcopy(definitions[value["$ref"].split("/")[-1]]))
            return {key: expand(item) for key, item in value.items()}
        return value

    return expand(schema)


def body_documentation(schema: dict, description: str) -> dict:
    return {
        "requestBody": {
            "required": True,
            "description": description,
            "content": {
                "application/json": {"schema": schema},
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"},
                    "description": "The same object encoded as msgpack; bodies may contain raw bytes.",
                },
            },
        }
    }


def mock_documentation() -> dict:
    schema = inline_schema(MockResource)
    schema.pop("required", None)  # Identity is required in the URI, optional (and checked) in the body.
    return body_documentation(
        schema,
        "PUT replaces the mock; PATCH changes supplied fields only. PATCH merges mock_data fields, "
        "replaces arrays/headers/bodies, and clears nullable fields with null. This is not JSON Merge Patch.",
    )


def snapshot_documentation() -> dict:
    schema = {
        "type": "object",
        "required": ["format", "mocks"],
        "properties": {
            "format": {"const": 1},
            "protocol": {"const": "http", "default": "http"},
            "generated_by": {"type": "string"},
            "mocks": {"type": "array", "items": {"type": "object", "required": ["path"]}},
        },
    }
    return body_documentation(
        schema,
        "Format 1 snapshot: binary bodies use body_b64. PUT replaces all mocks. PATCH merges by "
        "normalized path, replacing supplied mocks and preserving omitted mocks. Not JSON Merge Patch.",
    )
