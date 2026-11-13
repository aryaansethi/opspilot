"""Request dependencies: current user and workspace scope.

Tenant isolation is enforced here: every workspace-scoped route depends on
`get_workspace_ctx`, which verifies membership for the X-Workspace-Id header.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models import User, WorkspaceMember

DB = Annotated[AsyncSession, Depends(get_session)]
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> User:
    if creds is None:
        raise Unauthorized("Missing bearer token")
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise Unauthorized("Invalid or expired token")
    user = await db.get(User, user_id)
    if user is None:
        raise Unauthorized("User no longer exists")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass(frozen=True)
class WorkspaceCtx:
    user: User
    workspace_id: uuid.UUID
    role: str

    def require_write(self) -> None:
        if self.role == "viewer":
            raise Forbidden("Viewers cannot modify this workspace")


async def get_workspace_ctx(
    db: DB,
    user: CurrentUser,
    x_workspace_id: Annotated[uuid.UUID, Header(alias="X-Workspace-Id")],
) -> WorkspaceCtx:
    member = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == x_workspace_id, WorkspaceMember.user_id == user.id
        )
    )
    if member is None:
        # Same response whether the workspace doesn't exist or isn't yours.
        raise Forbidden("No access to this workspace")
    return WorkspaceCtx(user=user, workspace_id=x_workspace_id, role=member.role)


Workspace = Annotated[WorkspaceCtx, Depends(get_workspace_ctx)]
