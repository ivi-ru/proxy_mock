from __future__ import annotations

import asyncio
from copy import deepcopy

from proxy_mock.client.migration import normalize_mock_path
from proxy_mock.domain.models import MockDataSchema, MockPathSchema


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
        sequence: dict | None = None,
        recording: dict | None = None,
    ) -> dict:
        normalized_path = normalize_mock_path(path)

        payload = MockPathSchema(
            methods=methods,
            mock_data=MockDataSchema(**mock_data).model_dump(),
            extra_info=extra_info,
            proxy_host=proxy_host,
            timeout=timeout,
            rules=rules,
            sequence=sequence,
            recording=recording,
        ).model_dump()
        payload["path"] = normalized_path

        async with self._lock:
            self._storage[normalized_path] = payload
            return deepcopy(payload)

    async def get_mock_data(self, path: str) -> dict | None:
        normalized_path = normalize_mock_path(path)
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
        normalized_path = normalize_mock_path(path)
        async with self._lock:
            return self._storage.pop(normalized_path, None) is not None
