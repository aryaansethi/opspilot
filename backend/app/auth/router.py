"""Register / login / refresh (rotating) / logout / me."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.auth.deps import DB, CurrentUser
from app.auth.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.core.config import get_settings
from app.core.errors import Conflict, Unauthorized
from app.core.logging import log
from app.core.ratelimit import limit
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.models import RefreshToken, User
from app.workspaces.service import create_workspace

router = APIRouter(prefix="/auth", tags=["auth"])
RefreshCookie = Annotated[str | None, Cookie(alias="opspilot_refresh")]


def _set_refresh_cookie(response: Response, raw: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.refresh_cookie_name,
        raw,
        max_age=s.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path=f"{s.api_prefix}/auth",
    )


async def _issue(db: DB, response: Response, user: User) -> TokenResponse:
    raw, digest = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=digest,
            expires_at=datetime.now(UTC) + timedelta(days=get_settings().refresh_token_ttl_days),
        )
    )
    await db.commit()
    _set_refresh_cookie(response, raw)
    return TokenResponse(
        access_token=create_access_token(user.id), user=UserOut.model_validate(user)
    )


_settings = get_settings()


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit("registration", _settings.register_rate_limit_per_hour, 3600))],
)
async def register(body: RegisterRequest, db: DB, response: Response) -> TokenResponse:
    user = User(
        email=body.email, password_hash=hash_password(body.password), display_name=body.display_name
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise Conflict("An account with this email already exists") from None
    await create_workspace(
        db, name=body.workspace_name or f"{body.display_name}'s workspace", owner_id=user.id
    )
    return await _issue(db, response, user)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(limit("login", _settings.login_rate_limit_per_minute, 60))],
)
async def login(body: LoginRequest, db: DB, response: Response) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == body.email))
    if not verify_password(body.password, user.password_hash if user else None) or user is None:
        # Never log the password; the email is hashed so failures can be correlated, not read.
        log.warning(
            "auth.login_failed",
            email_sha256=hashlib.sha256(body.email.lower().encode()).hexdigest()[:16],
            known_user=user is not None,
        )
        raise Unauthorized("Invalid email or password")
    return await _issue(db, response, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(db: DB, response: Response, token: RefreshCookie = None) -> TokenResponse:
    if not token:
        raise Unauthorized("Missing refresh token")
    row = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token))
    )
    now = datetime.now(UTC)
    if row is None or row.expires_at <= now:
        raise Unauthorized("Invalid refresh token")
    if row.revoked_at is not None:
        # Reuse of a rotated token: assume theft, revoke every session for this user.
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.commit()
        raise Unauthorized("Refresh token reuse detected; please sign in again")
    row.revoked_at = now
    user = await db.get(User, row.user_id)
    if user is None:
        raise Unauthorized("User no longer exists")
    return await _issue(db, response, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(db: DB, response: Response, token: RefreshCookie = None) -> None:
    if token:
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == hash_refresh_token(token),
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await db.commit()
    s = get_settings()
    response.delete_cookie(s.refresh_cookie_name, path=f"{s.api_prefix}/auth")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
