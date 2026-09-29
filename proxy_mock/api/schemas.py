from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from proxy_mock.domain.models import (
    ConfigureMockRequestSchema,
    MockDataSchema,
    MockRulesSchema,
    RulesInputDataSchema,
)


class SuccessResponse(BaseModel):
    success: bool = True


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail


class DataResponse(SuccessResponse):
    data: dict | list


class MockResponse(DataResponse):
    path: str


class ResponseData(MockDataSchema):
    model_config = ConfigDict(extra="forbid")


class RuleInput(RulesInputDataSchema):
    model_config = ConfigDict(extra="forbid")
    body: dict | bytes | str | list | None = None


class RuleResource(MockRulesSchema):
    model_config = ConfigDict(extra="forbid")
    input_data: RuleInput = Field(default_factory=RuleInput)
    output_data: ResponseData = Field(default_factory=ResponseData)
    # Equal priorities retain submitted list order unless the caller supplies timestamps.
    # A repeated PUT must not generate a different representation.
    timestamp: float = 0


class MockResource(ConfigureMockRequestSchema):
    model_config = ConfigDict(extra="forbid")
    mock_data: ResponseData = Field(default_factory=ResponseData)
    rules: list[RuleResource] | None = None
