import logging
import tomllib
from http import HTTPMethod

from proxy_mock.client import ProxyMock
from proxy_mock.core.serializers import convert_bytes_to_str, formatted_data
from proxy_mock.core.settings import get_version_from_pyproject


class TestFormattedData:
    def test_empty(self):
        assert formatted_data(b"") is None
        assert formatted_data("") is None

    def test_str_json(self):
        assert formatted_data('{"a": 1}') == {"a": 1}

    def test_str_plain(self):
        assert formatted_data("hello") == "hello"

    def test_bytes_json(self):
        assert formatted_data(b'{"a": 1}') == {"a": 1}

    def test_bytes_non_utf8_falls_back_to_latin1(self):
        assert formatted_data(b"\xff\xfe") == b"\xff\xfe".decode("latin-1")


class TestConvertBytesToStr:
    def test_nested_structures(self):
        data = {"a": b'{"x": 1}', "b": [b"raw", {"c": b"y"}]}
        assert convert_bytes_to_str(data) == {"a": {"x": 1}, "b": ["raw", {"c": "y"}]}


class TestVersionDetection:
    logger = logging.getLogger("test")

    def test_version_from_own_pyproject(self):
        with open("pyproject.toml", "rb") as f:
            expected = tomllib.load(f)["project"]["version"]
        assert get_version_from_pyproject(self.logger) == expected

    def test_no_pyproject_in_cwd_does_not_crash(self, tmp_path, monkeypatch):
        # proxy_mock is installed as a library and there is no pyproject.toml in the CWD
        monkeypatch.chdir(tmp_path)
        version = get_version_from_pyproject(self.logger)
        assert isinstance(version, str) and version

    def test_foreign_pyproject_is_ignored(self, tmp_path, monkeypatch):
        # the CWD holds the consumer project's pyproject.toml, whose version must not be used
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "consumer"\nversion = "9.9.9"\n')
        monkeypatch.chdir(tmp_path)
        assert get_version_from_pyproject(self.logger) != "9.9.9"


class TestConfigureParsing:
    def test_empty_body_returns_400(self, client: ProxyMock):
        response = client.execute_request(
            HTTPMethod.POST, "/configure_mock", data=b"", headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400

    def test_bad_json_returns_400(self, client: ProxyMock):
        response = client.execute_request(
            HTTPMethod.POST, "/configure_mock", data="{bad", headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400

    def test_unsupported_content_type_returns_415(self, client: ProxyMock):
        response = client.execute_request(
            HTTPMethod.POST, "/configure_mock", data=b"whatever", headers={"Content-Type": "text/plain"}
        )
        assert response.status_code == 415

    def test_broken_msgpack_returns_400(self, client: ProxyMock):
        # Malformed msgpack (ExtraData/ValueError) must produce a 400, not a 500.
        for payload in (b"\xff\xff\xff", b"\x93\x01"):
            response = client.execute_request(
                HTTPMethod.POST,
                "/configure_mock",
                data=payload,
                headers={"Content-Type": "application/octet-stream"},
            )
            assert response.status_code == 400
