"""The fixtures shipped with the package, exercised by running pytest inside pytest."""

from tests import HOST


class TestShippedFixtures:
    def test_fixtures_work_without_any_setup(self, pytester):
        # No conftest, no pytest_plugins line: the fixtures arrive through the pytest11 entry point.
        pytester.makepyfile(
            """
            import requests


            def test_mock_answers(proxy_mock, proxy_mock_url):
                proxy_mock.configure_mock(path="/from-plugin", body={"ok": True})

                response = requests.get(f"{proxy_mock_url}/from-plugin", timeout=5)

                assert response.json() == {"ok": True}


            def test_storage_is_reset_between_tests(proxy_mock):
                assert proxy_mock.get_storage()["data"] == {}
            """
        )

        result = pytester.runpytest_subprocess("-q")

        result.assert_outcomes(passed=2)

    def test_external_instance_is_used_when_the_env_var_is_set(self, pytester, monkeypatch):
        monkeypatch.setenv("PROXY_MOCK_URL", HOST)
        pytester.makepyfile(
            f"""
            def test_url_comes_from_the_environment(proxy_mock_url):
                assert proxy_mock_url == "{HOST}"
            """
        )

        result = pytester.runpytest_subprocess("-q")

        result.assert_outcomes(passed=1)
