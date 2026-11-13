from httpx import AsyncClient


async def test_healthz(client: AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_readyz_reports_database_up(client: AsyncClient) -> None:
    r = await client.get("/readyz")
    assert r.status_code == 200 and r.json()["database"] == "up"


async def test_unknown_route_uses_error_envelope(client: AsyncClient) -> None:
    r = await client.get("/api/v1/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "http_error"
