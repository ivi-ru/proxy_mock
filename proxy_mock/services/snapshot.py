"""Versioned JSON snapshots of configuration and completed HTTP recordings.

Format 2 carries sequences and recorded replies. Format 1 remains readable for legacy mocks.
Sequence cursors, traffic and requests in flight are intentionally not serialized.
"""

import base64
import binascii
from typing import Any

from fastapi import FastAPI
from pydantic import ValidationError
from starlette.routing import compile_path

from proxy_mock.api.errors import safe_error_data
from proxy_mock.api.schemas import MockResource
from proxy_mock.client.migration import normalize_mock_path
from proxy_mock.domain.models import RecordingEntry
from proxy_mock.repositories.mock_storage import mock_storage
from proxy_mock.services.mock_service import cleanup_storage, mock_initialization, validate_mock_path
from proxy_mock.services.recordings import recording_id, recording_size

SNAPSHOT_FORMAT = 2
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
    if not isinstance(section, dict) or not isinstance(section.get("body"), bytes):
        return section
    encoded = dict(section)
    encoded["body_b64"] = base64.b64encode(encoded.pop("body")).decode("ascii")
    return encoded


def _decode_section(section: Any) -> Any:
    if not isinstance(section, dict) or "body_b64" not in section:
        return section
    if "body" in section:
        raise SnapshotError("Specify either 'body' or 'body_b64', not both")
    decoded = dict(section)
    raw = decoded.pop("body_b64")
    if not isinstance(raw, str):
        raise SnapshotError("Field 'body_b64' must be a base64 string")
    try:
        decoded["body"] = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as err:
        raise SnapshotError(f"Field 'body_b64' is not valid base64: {err}") from err
    return decoded


def _map_sequence(sequence: Any, convert) -> Any:
    if not isinstance(sequence, dict) or not isinstance(sequence.get("responses"), list):
        return sequence
    return {**sequence, "responses": [convert(response) for response in sequence["responses"]]}


def _map_rules(rules: Any, convert) -> Any:
    if not isinstance(rules, list):
        return rules
    mapped = []
    for rule in rules:
        if not isinstance(rule, dict):
            mapped.append(rule)
            continue
        converted = dict(rule)
        for key in RULE_SECTIONS:
            if key in converted:
                converted[key] = convert(converted[key])
        if "sequence" in converted:
            converted["sequence"] = _map_sequence(converted["sequence"], convert)
        mapped.append(converted)
    return mapped


def _convert_mock(mock: dict, convert) -> dict:
    result = dict(mock)
    for key in BODY_SECTIONS:
        if key in result:
            result[key] = convert(result[key])
    if "rules" in result:
        result["rules"] = _map_rules(result["rules"], convert)
    if "sequence" in result:
        result["sequence"] = _map_sequence(result["sequence"], convert)
    return result


async def export_snapshot(app: FastAPI) -> dict:
    """Export mock configuration and each recording collection in oldest-write order."""
    storage = await mock_storage.get_storage()
    mocks = []
    for mock in storage.values():
        value = _convert_mock(mock, _encode_section)
        if mock.get("recording") is not None:
            value["recordings"] = await app.state.recordings[mock["path"]].read()
        mocks.append(value)
    return {
        "format": SNAPSHOT_FORMAT,
        "protocol": SNAPSHOT_PROTOCOL,
        "generated_by": f"proxy_mock {app.state.version}",
        "mocks": mocks,
    }


def _validate_recordings(mock: dict, entries: Any) -> list[dict]:
    if not isinstance(entries, list):
        raise ValueError("recordings must be a list")
    config = mock.get("recording")
    if config is None:
        raise ValueError("recordings requires record/replay configuration")
    if len(entries) > config["max_items"]:
        raise ValueError("Recording count exceeds max_items")
    validated, seen, total = [], set(), 0
    excluded = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "content-encoding",
        "x-proxy-mock-recording",
    }
    for raw_entry in entries:
        entry = RecordingEntry.model_validate(raw_entry).model_dump()
        request, response = entry["request"], entry["response"]
        if set(request["headers"]) != set(config["match_headers"]):
            raise ValueError("Recorded request headers must match configured match_headers")
        for values in request["headers"].values():
            if any(
                any(ord(char) > 255 or (ord(char) < 32 and char != "\t") or ord(char) == 127 for char in value)
                for value in values
            ):
                raise ValueError("Recorded request header values must use valid Latin-1 octets")
        if entry["id"] != recording_id(request):
            raise ValueError("Recording id does not match its request")
        if entry["id"] in seen:
            raise ValueError("Duplicate recording id")
        seen.add(entry["id"])
        lengths = []
        for name, value in response["headers"]:
            if name.lower() in excluded:
                raise ValueError("Recorded replies must not contain transport or diagnostic headers")
            if name.lower() == "content-length":
                lengths.append(value)
        if lengths and (
            request["method"] != "HEAD" or len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit()
        ):
            raise ValueError("Only HEAD recordings may carry a single numeric Content-Length")
        if (request["method"] == "HEAD" or response["status_code"] in {204, 304}) and response["body_b64"]:
            raise ValueError("HEAD, 204 and 304 recordings must have empty response bodies")
        total += recording_size(entry)
        if total > config["max_bytes"]:
            raise ValueError("Recording data exceeds max_bytes")
        validated.append(entry)
    return validated


def parse_snapshot(snapshot: Any) -> list[dict]:
    """Validate the complete document before CLI startup or any administrative mutation."""
    if not isinstance(snapshot, dict):
        raise SnapshotError("The snapshot must be a JSON object")
    snapshot_format = snapshot.get("format")
    if type(snapshot_format) is not int or snapshot_format not in {1, 2}:
        raise SnapshotError(f"Unsupported snapshot format: {snapshot_format!r} (expected 1 or 2)")
    protocol = snapshot.get("protocol", SNAPSHOT_PROTOCOL)
    if protocol != SNAPSHOT_PROTOCOL:
        raise SnapshotError(f"Unsupported snapshot protocol: {protocol!r} (expected {SNAPSHOT_PROTOCOL!r})")
    if snapshot_format == 2:
        if set(snapshot) - {"format", "protocol", "generated_by", "mocks"}:
            raise SnapshotError("Unknown snapshot envelope fields")
        if "generated_by" in snapshot and not isinstance(snapshot["generated_by"], str):
            raise SnapshotError("generated_by must be a string")
    mocks = snapshot.get("mocks")
    if not isinstance(mocks, list):
        raise SnapshotError("Field 'mocks' must be a list")

    validated, seen_paths = [], set()
    for index, mock in enumerate(mocks):
        try:
            if not isinstance(mock, dict) or not mock.get("path"):
                raise ValueError("Every mock must be an object with a non-empty path")
            if snapshot_format == 1 and (
                has_sequences(mock) or mock.get("recording") is not None or "recordings" in mock
            ):
                raise ValueError("Sequences and recordings require snapshot format 2")
            data = _convert_mock(mock, _decode_section)
            if "cache_time" in data:
                cache_time = data.pop("cache_time")
                if cache_time is not None and not (type(cache_time) is int and cache_time == 0):
                    raise ValueError(
                        "cache_time has been removed; remove it or replace cached proxying with record/replay"
                    )
            entries = data.pop("recordings", None)
            value = MockResource.model_validate(data).model_dump()
            value["path"] = normalize_mock_path(data["path"])
            compile_path(value["path"])
            if value["path"] in seen_paths:
                raise ValueError("Duplicate normalized mock path in snapshot")
            seen_paths.add(value["path"])
            if "recordings" in mock:
                value["recordings"] = _validate_recordings(value, entries)
            elif value["recording"] is not None:
                value["recordings"] = []
            validated.append(value)
        except (ValidationError, ValueError, TypeError, AssertionError, SnapshotError) as err:
            errors = safe_error_data(err.errors()) if isinstance(err, ValidationError) else str(err)
            raise SnapshotError(
                {"mock_index": index, "path": mock.get("path") if isinstance(mock, dict) else None, "errors": errors}
            ) from err
    return validated


async def import_snapshot(app: FastAPI, snapshot: Any, mode: str = "merge") -> dict:
    """Merge replaces complete mocks by path; replace removes all omitted mocks.

    All configuration, recording data, limits and reserved paths are checked before mutation.
    Every imported sequence starts at zero; imported recordings keep their eviction order.
    """
    if mode not in ("merge", "replace"):
        raise SnapshotError(f"Unknown mode: {mode!r} (expected 'merge' or 'replace')", code=400)
    mocks = parse_snapshot(snapshot)
    for index, mock in enumerate(mocks):
        try:
            mock["path"] = validate_mock_path(app, mock["path"])
        except (ValueError, TypeError, AssertionError) as err:
            raise SnapshotError({"mock_index": index, "path": mock["path"], "errors": str(err)}) from err
    if mode == "replace":
        await cleanup_storage(app)
    for mock in mocks:
        entries = mock.pop("recordings", None)
        await mock_initialization(app, mock, recording_entries=entries)
    return {"imported": len(mocks), "mode": mode, "paths": [mock["path"] for mock in mocks]}
