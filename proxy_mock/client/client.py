from http import HTTPMethod
from typing import Any

from proxy_mock.client import calls
from proxy_mock.client.calls import UNSET
from proxy_mock.client.route import Route


class ProxyMock(Route):
    def _call(self, call: calls.Call):
        method, route, options = call
        return super().execute_request_and_get_response_body(method, route, **options)

    def get_proxy_mock(self):
        return self._call(calls.service_info(self.admin_prefix))

    def configure_mock(
        self,
        path: str,
        body: Any = None,
        headers: dict | None = None,
        status_code: int | None = None,
        extra_info: dict | None = None,
        proxy_host: str | None = None,
        timeout: float | None = None,
        rules: list[dict] | None = None,
        methods: list[str] | None = None,
        sequence: dict | None = None,
        recording: dict | None = None,
        **kwargs,
    ):
        payload = calls.mock_payload(
            path,
            body=body,
            headers=headers,
            status_code=status_code,
            extra_info=extra_info,
            proxy_host=proxy_host,
            timeout=timeout,
            rules=rules,
            methods=methods,
            sequence=sequence,
            recording=recording,
            **kwargs,
        )
        return self._call(calls.configure(self.admin_prefix, HTTPMethod.PUT, payload))

    def patch_mock(
        self,
        path: str,
        body: Any = UNSET,
        headers: dict | None = UNSET,
        status_code: int | None = UNSET,
        extra_info: dict | None = UNSET,
        proxy_host: str | None = UNSET,
        timeout: float | None = UNSET,
        rules: list[dict] | None = UNSET,
        methods: list[str] | None = UNSET,
        sequence: dict | None = UNSET,
        recording: dict | None = UNSET,
        **kwargs,
    ):
        payload = calls.mock_payload(
            path,
            include_none=True,
            body=body,
            headers=headers,
            status_code=status_code,
            extra_info=extra_info,
            proxy_host=proxy_host,
            timeout=timeout,
            rules=rules,
            methods=methods,
            sequence=sequence,
            recording=recording,
            **kwargs,
        )
        return self._call(calls.configure(self.admin_prefix, HTTPMethod.PATCH, payload))

    def get_traffic(self, path: str | None = None, method: str | None = None, limit: int | None = None):
        return self._call(calls.get_traffic(self.admin_prefix, path, method, limit))

    def get_storage(self, path: str | None = None):
        return self._call(calls.get_mocks(self.admin_prefix, path))

    def clean_storage(self):
        """Delete all mocks. Use delete_mock(path) to delete one mock."""
        return self._call(calls.delete_mocks(self.admin_prefix))

    def export_mocks(self):
        """Export every configured mock as a snapshot document."""
        return self._call(calls.export_snapshot(self.admin_prefix))

    def import_mocks(self, snapshot: dict, mode: str = "merge"):
        """Load a snapshot: `merge` keeps the configured mocks, `replace` clears them first."""
        return self._call(calls.import_snapshot(self.admin_prefix, snapshot, mode))

    def delete_mock(self, path: str):
        return self._call(calls.delete_mocks(self.admin_prefix, path))

    def clean_traffic(self):
        return self._call(calls.clean_traffic(self.admin_prefix))

    def get_traffic_settings(self):
        return self._call(calls.get_traffic_settings(self.admin_prefix))

    def set_traffic_settings(self, record_unknown_traffic: bool | None = None, max_items: int | None = None):
        return self._call(calls.set_traffic_settings(self.admin_prefix, record_unknown_traffic, max_items))

    def get_sequence_state(self, path: str, rule_index: int | None = None) -> dict:
        """Read the cursor of a mock sequence, or a rule by its zero-based configuration index."""
        return self._call(calls.get_sequence_state(self.admin_prefix, path, rule_index))

    def reset_sequence(self, path: str, rule_index: int | None = None) -> dict:
        """Restart a sequence through a partial update of its state resource."""
        return self._call(calls.reset_sequence(self.admin_prefix, path, rule_index))

    def get_recordings(self, path: str, recording_id: str | None = None) -> dict:
        """Inspect recorded requests and responses; binary bodies are base64 strings."""
        return self._call(calls.get_recordings(self.admin_prefix, path, recording_id))

    def delete_recordings(self, path: str, recording_id: str | None = None) -> dict:
        """Delete one recorded response or the entire collection belonging to a mock."""
        return self._call(calls.delete_recordings(self.admin_prefix, path, recording_id))
