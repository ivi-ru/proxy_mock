"""Each application owns its mock configuration, routes and response state."""

import asyncio
from contextlib import asynccontextmanager

import httpx2

from proxy_mock.app import create_app
from tests.test_snapshot_v2 import snapshot_with_entry


@asynccontextmanager
async def application_client():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test") as client:
            yield client


def test_recreated_application_starts_with_empty_mock_and_response_state():
    async def scenario():
        async with application_client() as first:
            snapshot = snapshot_with_entry()
            snapshot["mocks"].append({"path": "/ordered", "sequence": {"responses": [{"body": "first"}]}})
            assert (await first.put("/__admin/snapshot", json=snapshot)).status_code == 200
            assert (await first.get("/recorded")).content == b"\x00\xffsaved"
            assert (await first.get("/ordered")).text == "first"
            assert len((await first.get("/__admin/snapshot")).json()["mocks"]) == 2

        async with application_client() as second:
            exported = await second.get("/__admin/snapshot")
            assert exported.status_code == 200
            assert exported.json()["mocks"] == []
            assert (await second.get("/__admin")).json()["mocks_count"] == 0
            for resource in ("mocks", "recordings", "sequence-state"):
                assert (await second.get(f"/__admin/{resource}?path=/recorded")).status_code == 404
            assert (await second.get("/recorded")).status_code == 404

    asyncio.run(scenario())


def test_concurrent_applications_keep_configuration_recordings_and_sequences_independent():
    async def scenario():
        async with application_client() as first, application_client() as second:
            snapshot = snapshot_with_entry()
            snapshot["mocks"].append(
                {"path": "/ordered", "sequence": {"responses": [{"body": "first-1"}, {"body": "first-2"}]}}
            )
            assert (await first.put("/__admin/snapshot", json=snapshot)).status_code == 200
            for path, config in (
                ("/recorded", {"mock_data": {"body": "second-static"}}),
                ("/ordered", {"sequence": {"responses": [{"body": "second-1"}, {"body": "second-2"}]}}),
            ):
                assert (await second.put("/__admin/mocks", params={"path": path}, json=config)).status_code == 201

            assert (await first.get("/recorded")).content == b"\x00\xffsaved"
            assert (await second.get("/recorded")).text == "second-static"
            assert (await first.get("/ordered")).text == "first-1"
            assert (await second.get("/ordered")).text == "second-1"
            for client in (first, second):
                assert (await client.get("/__admin")).json()["mocks_count"] == 2
                state = await client.get("/__admin/sequence-state?path=/ordered")
                assert state.json()["data"]["position"] == 1
            assert (await second.get("/__admin/recordings?path=/recorded")).status_code == 404
            assert (
                await second.patch("/__admin/mocks?path=/recorded", json={"mock_data": {"body": "updated"}})
            ).status_code == 200
            assert (await first.get("/recorded")).content == b"\x00\xffsaved"

            assert (await second.delete("/__admin/mocks?path=/ordered")).status_code == 200
            assert (await first.get("/ordered")).text == "first-2"
            assert (await first.get("/__admin/sequence-state?path=/ordered")).json()["data"]["position"] == 2
            assert (await second.delete("/__admin/mocks")).status_code == 200
            assert (await second.get("/__admin/snapshot")).json()["mocks"] == []
            assert len((await first.get("/__admin/snapshot")).json()["mocks"]) == 2

            # A replace import also belongs to only the addressed application.
            assert (await second.put("/__admin/snapshot", json={"format": 2, "mocks": []})).status_code == 200
            assert (await first.get("/__admin/recordings?path=/recorded")).json()["data"] == snapshot["mocks"][0][
                "recordings"
            ]

    asyncio.run(scenario())
