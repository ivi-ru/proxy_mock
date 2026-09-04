from __future__ import annotations

import asyncio
from copy import deepcopy

from proxy_mock.domain.models import MockDataSchema, MockPathSchema


def _normalize_path(path: str) -> str:
    path = (path or "").split("?")[0].strip()
    if not path.startswith("/"):
        path = "/" + path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path


class MockStorage:
    def __init__(self) -> None:
        self._storage: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def set_mock_data(
        self,
        path: str,
        methods: list[str],
        mock_data: dict,
        extra_info: dict,
        proxy_host: str | None,
        timeout: float,
        rules: list[dict],
        cache_time: int,
    ) -> dict:
        normalized_path = _normalize_path(path)

        payload = MockPathSchema(
            methods=methods,
            mock_data=MockDataSchema(**mock_data).model_dump(),
            extra_info=extra_info,
            proxy_host=proxy_host,
            timeout=timeout,
            rules=rules,
            cache_time=cache_time,
        ).model_dump()
        payload["path"] = normalized_path

        async with self._lock:
            self._storage[normalized_path] = payload
            return deepcopy(payload)

    async def get_mock_data(self, path: str) -> dict | None:
        normalized_path = _normalize_path(path)
        async with self._lock:
            data = self._storage.get(normalized_path)
            return deepcopy(data) if data else None

    async def get_storage(self) -> dict:
        async with self._lock:
            return deepcopy(self._storage)

    async def count(self) -> int:
        async with self._lock:
            return len(self._storage)

    async def clean_storage(self) -> bool:
        async with self._lock:
            self._storage.clear()
        return True

    async def delete_mock_data(self, path: str) -> bool:
        normalized_path = _normalize_path(path)
        async with self._lock:
            return self._storage.pop(normalized_path, None) is not None


mock_storage = MockStorage()
