import re
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record
from app.models import Workspace, WorkspaceMember


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "workspace"
    return f"{base}-{secrets.token_hex(3)}"


async def create_workspace(db: AsyncSession, *, name: str, owner_id: uuid.UUID) -> Workspace:
    ws = Workspace(name=name, slug=_slugify(name))
    db.add(ws)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=owner_id, role="owner"))
    record(
        db,
        workspace_id=ws.id,
        actor_user_id=owner_id,
        action="workspace.created",
        target_type="workspace",
        target_id=ws.id,
    )
    return ws


async def list_memberships(db: AsyncSession, user_id: uuid.UUID) -> list[WorkspaceMember]:
    rows = await db.scalars(
        select(WorkspaceMember)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(WorkspaceMember.created_at)
    )
    return list(rows)
