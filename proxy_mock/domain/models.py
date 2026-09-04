import time
from http import HTTPMethod

from pydantic import BaseModel, Field, field_serializer, field_validator
from yarl import URL


class MockDataSchema(BaseModel):
    body: dict | str | bytes | list | None = Field(None)
    status_code: int = Field(200)
    headers: dict | None = Field(None)

    @field_serializer("headers")
    def serialize_headers(self, headers: dict) -> dict:
        return {str(key): str(value) for key, value in headers.items()} if headers else {}


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
        if value and not URL(value).is_absolute():
            raise ValueError("Parameter 'proxy_host' must be an absolute URL")
        return value


class MockRulesSchema(BaseModel):
    input_data: RulesInputDataSchema | dict = Field(RulesInputDataSchema().model_dump())
    output_data: MockDataSchema | dict = Field(MockDataSchema().model_dump())
    extra_info: dict | None = Field(None)
    priority: int = Field(0)
    timestamp: float = Field(default_factory=lambda: time.time())


class MockPathSchema(BaseModel):
    methods: list[HTTPMethod] | None = Field(None)
    mock_data: MockDataSchema | dict = Field(MockDataSchema().model_dump())
    extra_info: dict | None = Field(None)
    proxy_host: str | None = Field(None)
    timeout: float | None = Field(None)
    rules: list[MockRulesSchema] | None = Field(None)
    cache_time: int | None = Field(None)


class ConfigureMockRequestSchema(MockPathSchema):
    path: str = Field(...)

    @field_validator("proxy_host")
    def check_proxy_host(cls, value):
        if value and not URL(value).is_absolute():
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
