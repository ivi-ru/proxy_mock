import base64
import binascii
import re
import time
from http import HTTPMethod
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from proxy_mock.core.urls import proxy_hostname


class MockDataSchema(BaseModel):
    body: dict | str | bytes | list | None = Field(None)
    status_code: int = Field(200)
    headers: dict | None = Field(None)

    @field_serializer("headers")
    def serialize_headers(self, headers: dict) -> dict:
        return {str(key): str(value) for key, value in headers.items()} if headers else {}


class SequenceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    responses: list[MockDataSchema] = Field(min_length=1)
    on_exhaustion: Literal["repeat_last", "error"] = "repeat_last"


class RecordingSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["record", "replay"]
    match_headers: list[str] = Field(default_factory=list)
    max_items: int = Field(100, strict=True, gt=0)
    max_bytes: int = Field(10 * 1024 * 1024, strict=True, gt=0)

    @field_validator("match_headers")
    @classmethod
    def validate_headers(cls, values):
        if any(not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", value) for value in values):
            raise ValueError("match_headers must contain HTTP header names")
        return sorted({value.lower() for value in values})


class RecordedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    method: str
    path: str
    query: str
    body_b64: str
    headers: dict[str, list[str]]

    @field_validator("method")
    @classmethod
    def validate_method(cls, value):
        if value not in {method.value for method in HTTPMethod}:
            raise ValueError("Unknown request method")
        return value

    @field_validator("path", "query")
    @classmethod
    def validate_target(cls, value, info):
        if any(ord(char) < 33 or ord(char) > 126 for char in value) or "#" in value:
            raise ValueError("Recorded target must use raw ASCII URL encoding")
        if info.field_name == "path" and (not value.startswith("/") or "?" in value):
            raise ValueError("Recorded path must be absolute and contain no query")
        return value

    @field_validator("body_b64")
    @classmethod
    def validate_body(cls, value):
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as err:
            raise ValueError("Recorded body must be valid base64") from err
        if base64.b64encode(decoded).decode("ascii") != value:
            raise ValueError("Recorded body must use canonical base64")
        return value


class RecordedReply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status_code: int = Field(ge=200, le=599)
    headers: list[list[str]]
    body_b64: str

    @field_validator("body_b64")
    @classmethod
    def validate_body(cls, value):
        return RecordedRequest.validate_body(value)

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, values):
        for pair in values:
            if len(pair) != 2 or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", pair[0]):
                raise ValueError("Recorded headers must be name/value pairs")
            if any(ord(char) > 255 or ord(char) == 127 or (ord(char) < 32 and char != "\t") for char in pair[1]):
                raise ValueError("Recorded header values must use valid Latin-1 octets")
        return values


class RecordingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^[0-9a-f]{64}$")
    request: RecordedRequest
    response: RecordedReply


class RulesInputDataSchema(BaseModel):
    methods: list[HTTPMethod] | None = Field(None)
    body: dict | bytes | None = Field(None)
    headers: dict | None = Field(None)
    query: dict | None = Field(None)
    proxy_host: str | None = Field(None)
    timeout: float | None = Field(None)

    @field_serializer("headers")
    def serialize_headers(self, headers: dict) -> dict:
        return {str(key).lower(): str(value) for key, value in headers.items()} if headers else {}

    @field_serializer("query")
    def serialize_query(self, query: dict) -> dict:
        return {str(key): str(value) for key, value in query.items()} if query else {}

    @field_validator("proxy_host")
    def check_proxy_host(cls, value):
        if value and not proxy_hostname(value):
            raise ValueError("Parameter 'proxy_host' must be an absolute URL")
        return value


class MockRulesSchema(BaseModel):
    input_data: RulesInputDataSchema | dict = Field(RulesInputDataSchema().model_dump())
    output_data: MockDataSchema | dict = Field(MockDataSchema().model_dump())
    extra_info: dict | None = Field(None)
    priority: int = Field(0)
    timestamp: float = Field(default_factory=lambda: time.time())
    sequence: SequenceSchema | None = None


class MockPathSchema(BaseModel):
    methods: list[HTTPMethod] | None = Field(None)
    mock_data: MockDataSchema | dict = Field(MockDataSchema().model_dump())
    extra_info: dict | None = Field(None)
    proxy_host: str | None = Field(None)
    timeout: float | None = Field(None)
    rules: list[MockRulesSchema] | None = Field(None)
    sequence: SequenceSchema | None = None
    recording: RecordingSchema | None = None


class ConfigureMockRequestSchema(MockPathSchema):
    path: str = Field(...)

    @field_validator("proxy_host")
    def check_proxy_host(cls, value):
        if value and not proxy_hostname(value):
            raise ValueError("Parameter 'proxy_host' must be an absolute URL")
        return value

    @field_serializer("path")
    def serialize_path(self, path: str):
        path = path.split("?")[0]
        path = path.replace(" ", "")
        return f"/{path}" if path and path[0] != "/" else path

    @field_serializer("methods")
    def serialize_methods(self, methods: list[str]):
        if not methods:
            return [m.value for m in HTTPMethod]
        return methods


class TrafficSettingsSchema(BaseModel):
    """Partial update: only the explicitly supplied fields are applied."""

    record_unknown_traffic: bool | None = Field(None)
    max_items: int | None = Field(None, gt=0)


class InputRequestSchema(BaseModel):
    request_method: str = Field(...)
    request_body: dict | list | str | None = Field(None)
    request_headers: dict | None = Field(None)
    request_path: str | None = Field(None)
    request_query: dict | None = Field(None)
    extra_info: dict | None = Field(None)
