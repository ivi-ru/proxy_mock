"""Process-local response cache, used only on the application's event loop."""

import asyncio
from typing import Any


class TTLCache:
    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._timers: dict[str, asyncio.TimerHandle] = {}

    def _delete(self, key: str) -> None:
        self._values.pop(key, None)
        timer = self._timers.pop(key, None)
        if timer is not None:
            timer.cancel()

    async def get(self, key: str) -> Any:
        return self._values.get(key)

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        # There are no suspension points: replacing a value and its timer is atomic on this loop.
        self._delete(key)
        self._values[key] = value
        if ttl:
            self._timers[key] = asyncio.get_running_loop().call_later(ttl, self._delete, key)

    async def clear(self) -> None:
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()
        self._values.clear()

    async def close(self) -> None:
        await self.clear()
