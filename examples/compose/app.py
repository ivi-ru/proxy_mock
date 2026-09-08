"""A tiny storefront whose inventory dependency is configured through its environment."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen


class Storefront(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = {"ok": True}
        elif self.path == "/products/sku-42":
            with urlopen(f"{os.environ['INVENTORY_URL']}/inventory/sku-42", timeout=5) as response:
                inventory = json.load(response)
            body = {"sku": "sku-42", "in_stock": inventory["available"] > 0}
        else:
            self.send_error(404)
            return

        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Storefront).serve_forever()
