import json
from typing import Any


def formatted_data(data: str | bytes):
    if not data:
        return None

    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return data

    if isinstance(data, bytes):
        try:
            return json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # latin-1 decodes any byte sequence, so no further fallback is needed.
            return data.decode("latin-1")

    return data


def convert_bytes_to_str(data: Any):
    if isinstance(data, dict):
        return {key: convert_bytes_to_str(value) for key, value in data.items()}
    if isinstance(data, list):
        return [convert_bytes_to_str(item) for item in data]
    if isinstance(data, bytes):
        return formatted_data(data)
    return data
