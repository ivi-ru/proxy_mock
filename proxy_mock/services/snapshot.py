"""Export and import of the mock storage as a single JSON document.

The snapshot is a public contract, so it carries its own format version. Bodies that are bytes
cannot be expressed in JSON and travel base64-encoded in ``body_b64`` instead of ``body``.
"""

import base64
import binascii
import json
from typing import Any

from fastapi import FastAPI
from pydantic import ValidationError

from proxy_mock.api.schemas import MockResource
from proxy_mock.repositories.mock_storage import mock_storage
from proxy_mock.services.mock_service import cleanup_storage, mock_initialization, validate_mock_path

SNAPSHOT_FORMAT = 1
SNAPSHOT_PROTOCOL = "http"

BODY_SECTIONS = ("mock_data",)
RULE_SECTIONS = ("input_data", "output_data")


class SnapshotError(Exception):
    """The snapshot cannot be read: a wrong format, a broken body or an invalid mock."""

    def __init__(self, detail: Any, code: int = 422) -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code


def has_sequences(mock: dict) -> bool:
    rules = mock.get("rules")
    return mock.get("sequence") is not None or (
        isinstance(rules, list) and any(isinstance(rule, dict) and rule.get("sequence") is not None for rule in rules)
    )


def _encode_section(section: Any) -> Any:
    """Replace a bytes body with its base64 form, leaving everything else untouched."""
    if not isinstance(section, dict) or not isinstance(section.get("body"), bytes):
        return section

    encoded = dict(section)
    encoded["body_b64"] = base64.b64encode(encoded.pop("body")).decode("ascii")
    return encoded


def _decode_section(section: Any) -> Any:
    if not isinstance(section, dict) or "body_b64" not in section:
        return section

    decoded = dict(section)
    raw = decoded.pop("body_b64")
    if not isinstance(raw, str):
        raise SnapshotError("Field 'body_b64' must be a base64 string")

    try:
        decoded["body"] = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as err:
        raise SnapshotError(f"Field 'body_b64' is not valid base64: {err}") from err

    return decoded


def _map_rules(rules: Any, convert) -> Any:
    if not isinstance(rules, list):
        return rules

    mapped = []
    for rule in rules:
        if not isinstance(rule, dict):
            mapped.append(rule)
            continue
        converted = dict(rule)
        converted.pop("sequence", None)
        for key in RULE_SECTIONS:
            if key in converted:
                converted[key] = convert(converted[key])
        mapped.append(converted)
    return mapped


def _convert_mock(mock: dict, convert) -> dict:
    result = dict(mock)
    result.pop("sequence", None)
    result.pop("recording", None)
    for key in BODY_SECTIONS:
        if key in result:
            result[key] = convert(result[key])
    if "rules" in result:
        result["rules"] = _map_rules(result["rules"], convert)
    return result


async def export_snapshot(version: str) -> dict:
    """Build a snapshot of every configured mock."""
    storage = await mock_storage.get_storage()
    if any(mock.get("recording") is not None for mock in storage.values()):
        raise SnapshotError("Snapshot format 1 cannot represent recordings; format 2 support is pending", 409)
    if any(has_sequences(mock) for mock in storage.values()):
        raise SnapshotError("Snapshot format 1 cannot represent response sequences; format 2 support is pending", 409)
    return {
        "format": SNAPSHOT_FORMAT,
        "protocol": SNAPSHOT_PROTOCOL,
        "generated_by": f"proxy_mock {version}",
        "mocks": [_convert_mock(mock, _encode_section) for mock in storage.values()],
    }


def parse_snapshot(snapshot: Any) -> list[dict]:
    """Validate the envelope and return the mocks it carries, with bodies decoded."""
    if not isinstance(snapshot, dict):
        raise SnapshotError("The snapshot must be a JSON object")

    snapshot_format = snapshot.get("format")
    if snapshot_format != SNAPSHOT_FORMAT:
        raise SnapshotError(f"Unsupported snapshot format: {snapshot_format!r} (expected {SNAPSHOT_FORMAT})")

    protocol = snapshot.get("protocol", SNAPSHOT_PROTOCOL)
    if protocol != SNAPSHOT_PROTOCOL:
        raise SnapshotError(f"Unsupported snapshot protocol: {protocol!r} (expected {SNAPSHOT_PROTOCOL!r})")

    mocks = snapshot.get("mocks")
    if not isinstance(mocks, list):
        raise SnapshotError("Field 'mocks' must be a list")

    for index, mock in enumerate(mocks):
        if not isinstance(mock, dict):
            raise SnapshotError(f"Mock #{index} must be a JSON object")
        if not mock.get("path"):
            raise SnapshotError(f"Mock #{index} has no 'path'")
        if mock.get("recording") is not None:
            raise SnapshotError("Record/replay is not supported by snapshot format 1")
        if has_sequences(mock):
            raise SnapshotError("Response sequences are not supported by snapshot format 1")

    return [_convert_mock(mock, _decode_section) for mock in mocks]


async def import_snapshot(app: FastAPI, snapshot: Any, mode: str = "merge") -> dict:
    """Load a snapshot into the running instance.

    ``merge`` adds the mocks to whatever is already configured, ``replace`` wipes the storage
    first. Validation happens before anything is written, so a broken snapshot cannot leave the
    storage half-loaded.
    """
    if mode not in ("merge", "replace"):
        raise SnapshotError(f"Unknown mode: {mode!r} (expected 'merge' or 'replace')", code=400)

    mocks = parse_snapshot(snapshot)

    validated = []
    seen_paths = set()
    for index, mock in enumerate(mocks):
        try:
            value = MockResource.model_validate(mock).model_dump()
            value["path"] = validate_mock_path(app, mock["path"])
            if value["path"] in seen_paths:
                raise ValueError("Duplicate normalized mock path in snapshot")
            seen_paths.add(value["path"])
            validated.append(value)
        except ValidationError as err:
            raise SnapshotError(
                {"mock_index": index, "path": mock.get("path"), "errors": json.loads(err.json())}
            ) from err
        except (ValueError, TypeError, AssertionError) as err:
            raise SnapshotError({"mock_index": index, "path": mock.get("path"), "errors": str(err)}) from err

    if mode == "replace":
        await cleanup_storage(app)

    for mock in validated:
        await mock_initialization(app, mock)

    return {"imported": len(validated), "mode": mode, "paths": [mock["path"] for mock in validated]}
