"""Bounded, inspectable HTTP recordings owned by one mock configuration generation."""

import asyncio
import base64
import hashlib
import json
from collections import OrderedDict
from copy import deepcopy
from urllib.parse import quote

from fastapi import Request, Response


def recording_id(request: dict) -> str:
    return hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def recording_size(entry: dict) -> int:
    return len(json.dumps(entry, ensure_ascii=True).encode())


# httpx decodes the body; framing and hop-by-hop metadata must not be replayed. Recording drops
# these headers and snapshot import rejects them. Content-Length is decided per reply: only a
# HEAD reply keeps it.
UNREPLAYABLE_HEADERS = frozenset(
    {
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
)


def response_headers(headers, *, preserve_length: bool = False) -> list[list[str]]:
    excluded = set(UNREPLAYABLE_HEADERS)
    # A HEAD reply has no body from which to recover the decoded representation length.
    encoding = headers.get("content-encoding", "").strip().lower()
    if not (preserve_length and encoding in {"", "identity"}):
        excluded.add("content-length")
    excluded.update(value.strip().lower() for value in headers.get("connection", "").split(","))
    # Header convenience accessors may decode UTF-8. Use a reversible byte mapping instead.
    return [
        [name.decode("latin-1").lower(), value.decode("latin-1")]
        for name, value in headers.raw
        if name.decode("latin-1").lower() not in excluded
    ]


def recorded_response(data: dict, *, method: str) -> Response:
    response = Response(base64.b64decode(data["body_b64"]), data["status_code"])
    if method == "HEAD" or any(name.lower() == "content-length" for name, _ in data["headers"]):
        response.raw_headers = [(k, v) for k, v in response.raw_headers if k != b"content-length"]
    response.raw_headers.extend((name.encode("latin-1"), value.encode("latin-1")) for name, value in data["headers"])
    return response


class RecordingStore:
    def __init__(self, config: dict, previous=None, *, entries: list[dict] | None = None):
        self.config = deepcopy(config)
        self._entries = deepcopy(previous._entries) if previous is not None else OrderedDict()
        if entries is not None:
            self._entries = OrderedDict((entry["id"], (deepcopy(entry), recording_size(entry))) for entry in entries)
        self._bytes = sum(size for _, size in self._entries.values())
        self._revision = 0
        self._active = True
        self._lock = asyncio.Lock()
        self._trim()

    def retire(self):
        """Detach this generation before a mock is updated or removed."""
        self._active = False

    def _trim(self):
        while len(self._entries) > self.config["max_items"] or self._bytes > self.config["max_bytes"]:
            _, (_, size) = self._entries.popitem(last=False)
            self._bytes -= size

    async def identify(self, request: Request) -> tuple[str, dict, int]:
        revision = self._revision
        raw_path = request.scope.get("raw_path")
        data = {
            "method": request.method,
            "path": raw_path.decode("ascii") if raw_path is not None else quote(request.scope["path"], safe="/"),
            "query": request.scope["query_string"].decode("ascii"),
            "body_b64": base64.b64encode(await request.body()).decode("ascii"),
            "headers": {name: request.headers.getlist(name) for name in self.config["match_headers"]},
        }
        key = recording_id(data)
        return key, data, revision

    async def save(self, key: str, request: dict, response, revision: int) -> str:
        entry = {
            "id": key,
            "request": request,
            "response": {
                "status_code": response.status_code,
                "headers": response_headers(response.headers, preserve_length=request["method"] == "HEAD"),
                "body_b64": base64.b64encode(response.content).decode("ascii"),
            },
        }
        size = recording_size(entry)
        async with self._lock:
            if not self._active or revision != self._revision:
                return "superseded"
            if size > self.config["max_bytes"]:
                return "too_large"
            old = self._entries.pop(key, None)
            if old is not None:
                self._bytes -= old[1]
            self._entries[key] = (entry, size)
            self._bytes += size
            self._trim()
            return "stored"

    async def read(self, key: str | None = None):
        async with self._lock:
            if key is not None:
                entry = self._entries.get(key)
                return deepcopy(entry[0]) if entry else None
            return [deepcopy(entry) for entry, _ in self._entries.values()]

    async def delete(self, key: str | None = None) -> bool:
        async with self._lock:
            if key is not None and key not in self._entries:
                return False
            # A successful deletion invalidates outstanding writes, so they cannot undo it.
            self._revision += 1
            if key is None:
                self._entries.clear()
                self._bytes = 0
            else:
                _, size = self._entries.pop(key)
                self._bytes -= size
            return True
