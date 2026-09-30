"""Request schemas for endpoints that accept both JSON and binary msgpack."""

from copy import deepcopy

from pydantic import BaseModel

from proxy_mock.api.schemas import MockResource
from proxy_mock.domain.models import RecordingEntry


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


def snapshot_schema(format: int) -> dict:
    mock = inline_schema(MockResource)

    def add_binary_bodies(schema):
        if isinstance(schema, dict):
            for value in list(schema.values()):
                add_binary_bodies(value)
            properties = schema.get("properties", {})
            if "body" in properties:
                properties["body_b64"] = {"type": "string", "format": "byte"}
                schema["not"] = {"required": ["body", "body_b64"]}
        elif isinstance(schema, list):
            for value in schema:
                add_binary_bodies(value)

    add_binary_bodies(mock)
    if format == 2:
        mock["properties"]["recordings"] = {
            "type": "array",
            "items": inline_schema(RecordingEntry),
            "description": "Completed entries in oldest-write order; requires recording configuration.",
        }
    else:
        # Format 1 may carry null placeholders but cannot represent either new feature.
        mock["properties"]["recording"] = {"type": "null"}

        def legacy_sequences(schema):
            if isinstance(schema, dict):
                properties = schema.get("properties", {})
                if "sequence" in properties:
                    properties["sequence"] = {"type": "null"}
                for value in schema.values():
                    legacy_sequences(value)
            elif isinstance(schema, list):
                for value in schema:
                    legacy_sequences(value)

        legacy_sequences(mock)
    return {
        "type": "object",
        "additionalProperties": format == 1,
        "required": ["format", "mocks"],
        "properties": {
            "format": {"type": "integer", "const": format},
            "protocol": {"const": "http", "default": "http"},
            "generated_by": {"type": "string"},
            "mocks": {"type": "array", "items": mock},
        },
    }


def snapshot_documentation() -> dict:
    return body_documentation(
        {"oneOf": [snapshot_schema(1), snapshot_schema(2)]},
        "Formats 1 and 2 are accepted; export uses format 2. Binary bodies use body_b64. "
        "Format 2 includes sequence definitions and recordings; cursors restart at zero. "
        "PUT replaces all mocks. PATCH merges by "
        "normalized path, replacing supplied mocks and preserving omitted mocks. Not JSON Merge Patch. "
        "All validation, including recording integrity and limits, finishes before storage changes.",
    )
