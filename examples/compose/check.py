"""Configure the mock, call the storefront, and verify its outgoing request."""

import json
from urllib.request import Request, urlopen

MOCK_URL = "http://proxy-mock:5000"
APP_URL = "http://app:8000"


def request(url, method="GET", body=None):
    payload = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=payload, method=method, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=5) as response:
        assert 200 <= response.status < 300
        return json.load(response)


def main():
    request(f"{MOCK_URL}/storage", method="DELETE")
    request(f"{MOCK_URL}/traffic", method="DELETE")
    configured = request(
        f"{MOCK_URL}/configure_mock",
        method="POST",
        body={"path": "/inventory/sku-42", "methods": ["GET"], "mock_data": {"body": {"available": 3}}},
    )
    assert configured["success"]

    product = request(f"{APP_URL}/products/sku-42")
    assert product == {"sku": "sku-42", "in_stock": True}, product

    traffic = request(f"{MOCK_URL}/traffic?path=%2Finventory%2Fsku-42&method=GET")
    assert traffic["count"] == 1, traffic
    assert traffic["data"][0]["request_path"] == "/inventory/sku-42"
    assert traffic["data"][0]["request_method"] == "GET"
    print("PASS: storefront response and captured inventory request")


if __name__ == "__main__":
    main()
