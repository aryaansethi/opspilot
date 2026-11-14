"""Security review regressions: tokens, rate limits, stream caps, headers, isolation, logging."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.security import create_access_token
from tests.conftest import register
from tests.test_documents import ws_headers

API = "/api/v1"


def forge(claims: dict[str, Any]) -> str:
    s = get_settings()
    return jwt.encode(claims, s.jwt_secret.get_secret_value(), algorithm=s.jwt_algorithm)


async def test_tokens_require_issuer_audience_and_type(client: AsyncClient) -> None:
    u = await register(client)
    uid = u["user"]["id"]
    now = datetime.now(UTC)
    base = {"sub": uid, "iat": now, "exp": now + timedelta(minutes=5), "type": "access"}
    for bad in (
        base,  # no iss/aud (e.g. old or foreign token)
        {**base, "iss": "someone-else", "aud": "opspilot-app"},
        {**base, "iss": "opspilot-api", "aud": "another-app"},
        {**base, "iss": "opspilot-api", "aud": "opspilot-app", "type": "refresh"},
        {**base, "iss": "opspilot-api", "aud": "opspilot-app", "exp": now - timedelta(seconds=1)},
    ):
        r = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {forge(bad)}"})
        assert r.status_code == 401, bad
    ok = await client.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {create_access_token(uuid.UUID(uid))}"}
    )
    assert ok.status_code == 200
    none_alg = jwt.encode(
        {**base, "iss": "opspilot-api", "aud": "opspilot-app"}, key=None, algorithm="none"
    )
    assert (
        await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {none_alg}"})
    ).status_code == 401


async def test_expensive_endpoints_are_rate_limited_per_user(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.rag.generation.llm import set_llm
    from tests.test_search_and_ask import FakeLLM

    u = await register(client)
    set_llm(FakeLLM({"answer": "", "claims": [], "insufficient_evidence": True}))
    try:
        codes = [
            (
                await client.post(
                    f"{API}/ask", headers=ws_headers(u), json={"question": "why slow?"}
                )
            ).status_code
            for _ in range(get_settings().ask_rate_limit_per_minute + 1)
        ]
    finally:
        set_llm(None)
    assert codes[-1] == 429 and set(codes[:-1]) == {200}
    other = await register(client, "bob@example.com")  # limits are per user
    set_llm(FakeLLM({"answer": "", "claims": [], "insufficient_evidence": True}))
    try:
        assert (
            await client.post(
                f"{API}/ask", headers=ws_headers(other), json={"question": "why slow?"}
            )
        ).status_code == 200
    finally:
        set_llm(None)


async def test_live_streams_are_capped_per_user(client: AsyncClient) -> None:
    from app.core import ratelimit

    u = await register(client)
    r = await client.post(
        f"{API}/investigations", headers=ws_headers(u), json={"question": "Why is it slow today?"}
    )
    inv = r.json()["id"]
    slots = [
        ratelimit.StreamSlot(u["user"]["id"], get_settings().max_live_streams_per_user).__enter__()
        for _ in range(get_settings().max_live_streams_per_user)
    ]  # five streams already open
    blocked = await client.get(
        f"{API}/investigations/{inv}/events?follow=false", headers=ws_headers(u)
    )
    assert blocked.status_code == 429
    for s in slots:
        s.__exit__()
    assert (
        await client.get(f"{API}/investigations/{inv}/events?follow=false", headers=ws_headers(u))
    ).status_code == 200
    assert ratelimit._streams[u["user"]["id"]] == 0  # the slot is released after the stream ends


async def test_security_headers(client: AsyncClient) -> None:
    r = await client.post(
        f"{API}/auth/login", json={"email": "x@example.com", "password": "wrong-password"}
    )
    assert (
        r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    )
    assert r.headers["cache-control"] == "no-store"


async def test_failed_login_is_logged_without_secrets(
    client: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    await client.post(
        f"{API}/auth/login", json={"email": "victim@example.com", "password": "hunter2-password"}
    )
    out = capsys.readouterr().out
    assert "auth.login_failed" in out and "hunter2" not in out and "victim@example.com" not in out


@pytest.mark.parametrize(
    "path",
    [
        "/documents",
        "/integrations",
        "/investigations",
        "/approvals",
        "/audit-events",
        "/tool-invocations",
    ],
)
async def test_workspace_header_is_required_and_checked(client: AsyncClient, path: str) -> None:
    alice = await register(client, "alice@example.com")
    bob = await register(client, "bob@example.com")
    assert (
        await client.get(f"{API}{path}", headers=alice["headers"])
    ).status_code == 422  # no workspace
    cross = await client.get(
        f"{API}{path}", headers={**alice["headers"], "X-Workspace-Id": bob["workspace_id"]}
    )
    assert cross.status_code == 403
    assert (await client.get(f"{API}{path}")).status_code in (401, 422)  # no token
