from proxy_mock._server import require_server_dependencies

require_server_dependencies()

from proxy_mock.app.factory import create_app

__all__ = ["create_app"]
