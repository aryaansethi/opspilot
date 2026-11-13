from httpx import AsyncClient

from tests.conftest import register

API = "/api/v1"


async def test_create_and_list_workspaces(client: AsyncClient) -> None:
    u = await register(client)
    r = await client.post(f"{API}/workspaces", json={"name": "Platform Team"}, headers=u["headers"])
    assert r.status_code == 201 and r.json()["slug"].startswith("platform-team-")
    names = {
        w["name"] for w in (await client.get(f"{API}/workspaces", headers=u["headers"])).json()
    }
    assert "Platform Team" in names and len(names) == 2


async def test_workspace_header_is_enforced(client: AsyncClient) -> None:
    alice = await register(client, "alice@example.com")
    bob = await register(client, "bob@example.com")
    own = await client.get(
        f"{API}/workspaces/current",
        headers={**alice["headers"], "X-Workspace-Id": alice["workspace_id"]},
    )
    assert own.status_code == 200
    # Alice cannot use Bob's workspace id.
    cross = await client.get(
        f"{API}/workspaces/current",
        headers={**alice["headers"], "X-Workspace-Id": bob["workspace_id"]},
    )
    assert cross.status_code == 403
    missing = await client.get(f"{API}/workspaces/current", headers=alice["headers"])
    assert missing.status_code == 422
