"""Run with: python -m pytest -q examples/test_http_dependency.py."""

import json

import requests


def test_http_dependency(proxy_mock, proxy_mock_url):
    proxy_mock.configure_mock(path="/inventory/sku-42", methods=["GET"], body={"available": 3})

    response = requests.get(f"{proxy_mock_url}/inventory/sku-42", timeout=5)

    assert response.status_code == 200
    assert response.json() == {"available": 3}
    traffic = proxy_mock.get_traffic(path="/inventory/sku-42", method="GET")
    assert traffic["count"] == 1
    assert traffic["data"][0]["request_path"] == "/inventory/sku-42"


def test_reuse_a_mock_snapshot(proxy_mock, proxy_mock_url, tmp_path):
    proxy_mock.configure_mock(path="/catalog/42", methods=["GET"], body={"title": "Example article"})
    snapshot_file = tmp_path / "mocks.json"
    snapshot_file.write_text(json.dumps(proxy_mock.export_mocks()), encoding="utf-8")

    # Restore the saved configuration after discarding the original in-memory mocks.
    proxy_mock.clean_storage()
    snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
    proxy_mock.import_mocks(snapshot, mode="replace")

    response = requests.get(f"{proxy_mock_url}/catalog/42", timeout=5)

    assert response.status_code == 200
    assert response.json() == {"title": "Example article"}
    assert proxy_mock.get_traffic(path="/catalog/42")["count"] == 1
