import asyncio

from proxy_mock.repositories.ttl_cache import TTLCache


def test_expiration_releases_the_value_without_another_read():
    async def scenario():
        cache = TTLCache()
        await cache.set("key", {"body": b"cached"}, ttl=0.01)
        assert await cache.get("key") == {"body": b"cached"}
        await asyncio.sleep(0.03)
        assert await cache.get("key") is None
        assert not cache._values
        assert not cache._timers

    asyncio.run(scenario())


def test_overwriting_cancels_the_old_expiration():
    async def scenario():
        cache = TTLCache()
        await cache.set("key", "old", ttl=0.01)
        await cache.set("key", "new", ttl=60)
        await asyncio.sleep(0.03)
        assert await cache.get("key") == "new"
        await cache.close()

    asyncio.run(scenario())


def test_clear_cancels_timers_and_allows_reuse():
    async def scenario():
        cache = TTLCache()
        await cache.set("key", "old", ttl=0.01)
        await cache.clear()
        assert await cache.get("key") is None
        assert not cache._timers
        await cache.set("key", "new", ttl=0)
        await asyncio.sleep(0.03)
        assert await cache.get("key") == "new"
        await cache.close()
        assert await cache.get("key") is None

    asyncio.run(scenario())


def test_instances_do_not_share_values_or_timers():
    async def scenario():
        first, second = TTLCache(), TTLCache()
        await first.set("key", "first")
        await second.set("key", "second", ttl=60)
        await first.clear()
        assert await first.get("key") is None
        assert await second.get("key") == "second"
        await second.close()

    asyncio.run(scenario())
