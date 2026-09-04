import time
from http import HTTPMethod

from proxy_mock.client import ProxyMock
from tests.constants import TEST_RULES_DATA


class TestPatchConfigure:
    def test_base(self, client: ProxyMock, configure_mock_data):
        configure_response = client.configure_mock(**configure_mock_data)

        configure_mock_data = {"path": configure_mock_data["path"], "body": str(time.time())}
        patch_response = client.patch_mock(**configure_mock_data)

        assert configure_response["data"]["mock_data"]["body"] != patch_response["data"]["mock_data"]["body"]

        test_response = client.execute_request(
            HTTPMethod.POST,
            configure_mock_data["path"],
        )

        assert test_response.text == configure_mock_data["body"]

    def test_rules(self, client: ProxyMock, configure_mock_data):
        configure_mock_data["rules"] = [TEST_RULES_DATA[0]]
        configure_response = client.configure_mock(**configure_mock_data)

        assert len(configure_response["data"]["rules"]) == 1

        configure_mock_data = {"path": configure_mock_data["path"], "rules": [TEST_RULES_DATA[1]]}
        patch_response = client.patch_mock(**configure_mock_data)

        assert configure_response["data"]["mock_data"]["body"] == patch_response["data"]["mock_data"]["body"]
        assert len(patch_response["data"]["rules"]) == 2

    def test_fail(self, client: ProxyMock, configure_mock_data):
        patch_response = client.patch_mock(**configure_mock_data)

        assert not patch_response["success"]
        assert patch_response["error"] == f"There is no mock for {configure_mock_data['path']}"
