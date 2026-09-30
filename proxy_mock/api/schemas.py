from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from proxy_mock.domain.models import (
    ConfigureMockRequestSchema,
    MockDataSchema,
    MockRulesSchema,
    RulesInputDataSchema,
    SequenceSchema,
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


class SequenceResource(SequenceSchema):
    responses: list[ResponseData] = Field(min_length=1)


class SequenceStatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: int = Field(..., strict=True, ge=0, le=0, description="Set to zero to restart the sequence.")


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
    sequence: SequenceResource | None = None

    @model_validator(mode="after")
    def validate_sequence(self):
        if self.sequence is not None and self.input_data.proxy_host:
            raise ValueError("A rule cannot combine a response sequence with proxy_host")
        return self


class MockResource(ConfigureMockRequestSchema):
    model_config = ConfigDict(extra="forbid")
    mock_data: ResponseData = Field(default_factory=ResponseData)
    rules: list[RuleResource] | None = None
    sequence: SequenceResource | None = None

    @model_validator(mode="after")
    def validate_sequences(self):
        has_sequence = self.sequence is not None or any(rule.sequence is not None for rule in self.rules or [])
        if has_sequence and (self.cache_time or self.proxy_host):
            raise ValueError("Response sequences cannot be combined with mock-level proxy_host or response caching")
        if self.recording is not None:
            if self.recording.mode == "record" and not self.proxy_host:
                raise ValueError("Recording requires a mock-level proxy_host")
            if has_sequence or self.rules or self.cache_time:
                raise ValueError("Record/replay cannot be combined with rules, sequences or response caching")
        return self
