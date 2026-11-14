"""Password hashing (Argon2id), JWT access tokens, opaque refresh tokens."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()
# Used to keep login timing similar whether or not the email exists.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


TOKEN_ISSUER = "opspilot-api"  # noqa: S105 - an issuer name, not a secret
TOKEN_AUDIENCE = "opspilot-app"  # noqa: S105 - an audience name, not a secret


def create_access_token(user_id: uuid.UUID) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_ttl_minutes),
        "type": "access",
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
    }
    return jwt.encode(payload, s.jwt_secret.get_secret_value(), algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID | None:
    s = get_settings()
    try:
        payload = jwt.decode(
            token,
            s.jwt_secret.get_secret_value(),
            algorithms=[s.jwt_algorithm],
            issuer=TOKEN_ISSUER,
            audience=TOKEN_AUDIENCE,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        return None


def new_refresh_token() -> tuple[str, str]:
    """Returns (raw token for the cookie, sha256 hash for the database)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
