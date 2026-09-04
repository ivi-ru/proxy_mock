import time
from http import HTTPMethod

from proxy_mock.client import ProxyMock


class TestCaching:
    """Tests for response caching."""

    def test_cache_enabled_with_cache_time(self, client: ProxyMock):
        """Caching works when cache_time is set."""
        # Create a mock cached for 10 seconds
        mock_data = {"methods": ["GET"], "body": {"message": "cached_response"}, "timeout": 0.5, "cache_time": 10}

        configure_response = client.configure_mock("/api/cached-endpoint", **mock_data)
        assert configure_response.get("success")

        # First request: expected to be a cache miss
        start_time = time.time()
        first_response = client.execute_request_and_get_response_body(HTTPMethod.GET, "/api/cached-endpoint")
        first_duration = time.time() - start_time
        assert first_response == {"message": "cached_response"}
        assert first_duration >= 0.5

        # Second request: expected to be a cache hit (faster)
        start_time = time.time()
        second_response = client.execute_request_and_get_response_body(HTTPMethod.GET, "/api/cached-endpoint")
        second_duration = time.time() - start_time
        assert second_response == {"message": "cached_response"}
        assert second_duration < 0.5

    def test_cache_disabled_without_cache_time(self, client: ProxyMock):
        """Caching is disabled when cache_time is not set."""
        mock_data = {
            "methods": ["GET"],
            "body": {"message": "uncached_response"},
            "timeout": 0.5,
        }

        configure_response = client.configure_mock("/api/uncached-endpoint", **mock_data)
        assert configure_response.get("success")

        # Both requests should behave the same
        start_time = time.time()
        first_response = client.execute_request_and_get_response_body(HTTPMethod.GET, "/api/uncached-endpoint")
        second_response = client.execute_request_and_get_response_body(HTTPMethod.GET, "/api/uncached-endpoint")

        assert first_response == {"message": "uncached_response"}
        assert second_response == {"message": "uncached_response"}
        assert time.time() - start_time >= 1

    def test_cache_respects_query_parameters(self, client: ProxyMock):
        """Different query parameters produce different cache keys."""
        mock_data = {"methods": ["GET"], "body": {"results": []}, "timeout": 0.5, "cache_time": 30}

        configure_response = client.configure_mock("/api/search", **mock_data)
        assert configure_response.get("success")

        # Request with different parameters
        start_time = time.time()
        response1 = client.execute_request_and_get_response_body(HTTPMethod.GET, "/api/search?query=test1")
        response2 = client.execute_request_and_get_response_body(HTTPMethod.GET, "/api/search?query=test2")

        assert response1 == {"results": []}
        assert response2 == {"results": []}
        assert time.time() - start_time >= 1

    def test_cache_ttl_expiration(self, client: ProxyMock):
        """The cache entry expires after its TTL."""
        mock_data = {"methods": ["GET"], "body": {"value": "initial"}, "timeout": 0.5, "cache_time": 1}

        configure_response = client.configure_mock("/api/temporary", **mock_data)
        assert configure_response.get("success")

        # First request
        response1 = client.execute_request_and_get_response_body(HTTPMethod.GET, "/api/temporary")
        assert response1 == {"value": "initial"}

        # Wait for the TTL to expire
        time.sleep(1.1)

        # A fresh cache miss is expected
        start_time = time.time()
        response2 = client.execute_request_and_get_response_body(HTTPMethod.GET, "/api/temporary")
        assert response2 == {"value": "initial"}
        assert time.time() - start_time >= 0.5


class TestCacheAPI:
    """Tests for the cache management API."""

    def test_clear_entire_cache(self, client: ProxyMock):
        """Clearing the whole cache."""
        # Create several cached mocks
        mock1 = {"methods": ["GET"], "body": {"message": "cached_response1"}, "timeout": 0.5, "cache_time": 60}
        mock2 = {"methods": ["GET"], "body": {"message": "cached_response2"}, "timeout": 0.5, "cache_time": 60}

        client.configure_mock("/api/cache-test-1", **mock1)
        client.configure_mock("/api/cache-test-2", **mock2)

        # Issue requests to populate the cache
        client.execute_request_and_get_response_body(HTTPMethod.GET, "/api/cache-test-1")
        client.execute_request_and_get_response_body(HTTPMethod.GET, "/api/cache-test-2")

        # Clear the cache through the API
        clear_response = client.clean_cache()
        assert clear_response.get("success")

        # Verify the cache is empty
        start_time = time.time()
        client.execute_request_and_get_response_body(HTTPMethod.GET, "/api/cache-test-1")
        client.execute_request_and_get_response_body(HTTPMethod.GET, "/api/cache-test-2")
        assert time.time() - start_time >= 1
