from enum import Enum


class ConfigureContentTypes(str, Enum):
    JSON = "application/json"
    BINARY = "application/octet-stream"

    @classmethod
    def array(cls) -> list[str]:
        return [item.value for item in cls]


class ParseError(Exception):
    def __init__(self, detail: str, code: int):
        self.detail = detail
        self.code = code
