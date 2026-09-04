import asyncio
import os
from collections import deque
from copy import deepcopy
from typing import Any

DEFAULT_TRAFFIC_MAX = 1000


def _default_max_items() -> int:
    raw = os.getenv("PROXY_MOCK_TRAFFIC_MAX", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return DEFAULT_TRAFFIC_MAX


class TrafficStore:
    def __init__(self, max_items: int | None = None):
        self._data = deque(maxlen=max_items or _default_max_items())
        self._lock = asyncio.Lock()

    @property
    def max_items(self) -> int:
        return self._data.maxlen

    async def set_max_items(self, value: int) -> None:
        """Change the storage limit. Excess records are dropped, the most recent ones are kept."""
        async with self._lock:
            if value != self._data.maxlen:
                self._data = deque(self._data, maxlen=value)

    async def count(self) -> int:
        async with self._lock:
            return len(self._data)

    async def add(self, item: dict[str, Any]) -> None:
        async with self._lock:
            self._data.append(item)

    async def patch_last(self, patch: dict[str, Any]) -> None:
        async with self._lock:
            if not self._data:
                return
            last = dict(self._data[-1])
            last.update(patch)
            self._data[-1] = last

    async def list(
        self,
        path: str | None = None,
        method: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        async with self._lock:
            items = list(self._data)

        if path:
            items = [x for x in items if x.get("request_path") == path]
        if method:
            method_u = method.upper()
            items = [x for x in items if str(x.get("request_method", "")).upper() == method_u]
        if limit is not None:
            items = items[-limit:]

        return deepcopy(items)

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()
