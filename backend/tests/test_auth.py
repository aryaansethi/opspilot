from httpx import AsyncClient

from tests.conftest import register

API = "/api/v1"


async def test_register_returns_token_cookie_and_personal_workspace(client: AsyncClient) -> None:
    u = await register(client)
    assert u["user"]["email"] == "alice@example.com"
    assert "opspilot_refresh" in client.cookies
    ws = (await client.get(f"{API}/workspaces", headers=u["headers"])).json()
    assert len(ws) == 1 and ws[0]["role"] == "owner"


async def test_duplicate_email_conflicts_case_insensitively(client: AsyncClient) -> None:
    await register(client, "bob@example.com")
    r = await client.post(
        f"{API}/auth/register",
        json={"email": "BOB@example.com", "password": "another-long-pass", "display_name": "B"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


async def test_short_password_rejected(client: AsyncClient) -> None:
    r = await client.post(
        f"{API}/auth/register",
        json={"email": "c@example.com", "password": "short", "display_name": "C"},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


async def test_login_success_and_failure(client: AsyncClient) -> None:
    await register(client)
    ok = await client.post(
        f"{API}/auth/login",
        json={"email": "alice@example.com", "password": "correct-horse-battery"},
    )
    assert ok.status_code == 200 and ok.json()["access_token"]
    bad = await client.post(
        f"{API}/auth/login", json={"email": "alice@example.com", "password": "wrong-password!!"}
    )
    unknown = await client.post(
        f"{API}/auth/login", json={"email": "nobody@example.com", "password": "whatever-long"}
    )
    assert bad.status_code == unknown.status_code == 401
    assert bad.json()["error"]["message"] == unknown.json()["error"]["message"]


async def test_me_requires_valid_token(client: AsyncClient) -> None:
    u = await register(client)
    assert (await client.get(f"{API}/auth/me", headers=u["headers"])).json()["email"] == (
        "alice@example.com"
    )
    assert (await client.get(f"{API}/auth/me")).status_code == 401
    bad = await client.get(f"{API}/auth/me", headers={"Authorization": "Bearer garbage"})
    assert bad.status_code == 401


async def test_refresh_rotates_and_detects_reuse(client: AsyncClient) -> None:
    await register(client)
    first = client.cookies["opspilot_refresh"]
    r = await client.post(f"{API}/auth/refresh")
    assert r.status_code == 200
    second = client.cookies["opspilot_refresh"]
    assert second != first
    # Replaying the old (rotated) token revokes all sessions…
    client.cookies.set("opspilot_refresh", first, path="/api/v1/auth")
    assert (await client.post(f"{API}/auth/refresh")).status_code == 401
    # …including the newest one.
    client.cookies.set("opspilot_refresh", second, path="/api/v1/auth")
    assert (await client.post(f"{API}/auth/refresh")).status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    await register(client)
    token = client.cookies["opspilot_refresh"]
    assert (await client.post(f"{API}/auth/logout")).status_code == 204
    client.cookies.set("opspilot_refresh", token, path="/api/v1/auth")
    assert (await client.post(f"{API}/auth/refresh")).status_code == 401


async def test_login_is_rate_limited_per_ip(client: AsyncClient) -> None:
    await register(client)
    body = {"email": "alice@example.com", "password": "wrong-password!!"}
    codes = [(await client.post(f"{API}/auth/login", json=body)).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    r = await client.post(f"{API}/auth/login", json=body)
    assert (
        r.json()["error"]["code"] == "rate_limited"
        and r.json()["error"]["details"]["retry_after_seconds"] > 0
    )
