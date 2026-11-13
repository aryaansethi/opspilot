import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.auth.deps import DB, CurrentUser, Workspace
from app.workspaces.service import create_workspace, list_memberships

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: str


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(db: DB, user: CurrentUser) -> list[WorkspaceOut]:
    return [
        WorkspaceOut(id=m.workspace.id, name=m.workspace.name, slug=m.workspace.slug, role=m.role)
        for m in await list_memberships(db, user.id)
    ]


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create(body: WorkspaceCreate, db: DB, user: CurrentUser) -> WorkspaceOut:
    ws = await create_workspace(db, name=body.name, owner_id=user.id)
    await db.commit()
    return WorkspaceOut(id=ws.id, name=ws.name, slug=ws.slug, role="owner")


@router.get("/current", response_model=WorkspaceOut)
async def current(ctx: Workspace, db: DB) -> WorkspaceOut:
    """Resolves the workspace named in X-Workspace-Id (membership already verified)."""
    for m in await list_memberships(db, ctx.user.id):
        if m.workspace_id == ctx.workspace_id:
            return WorkspaceOut(
                id=m.workspace.id, name=m.workspace.name, slug=m.workspace.slug, role=m.role
            )
    raise AssertionError("membership verified by dependency")
