"""Import every model so Alembic autogenerate and relationship resolution see them."""

from app.models.documents import Document, DocumentChunk, DocumentIngestionJob
from app.models.identity import AuditEvent, RefreshToken, User, Workspace, WorkspaceMember
from app.models.investigations import (
    ActionApproval,
    EvidenceItem,
    Hypothesis,
    Investigation,
    InvestigationEvent,
    InvestigationReport,
)
from app.models.tools import (
    ConnectedIntegration,
    McpServer,
    ToolInvocation,
    ToolRegistryEntry,
)

__all__ = [
    "ActionApproval",
    "EvidenceItem",
    "Hypothesis",
    "Investigation",
    "InvestigationEvent",
    "InvestigationReport",
    "AuditEvent",
    "ConnectedIntegration",
    "McpServer",
    "ToolInvocation",
    "ToolRegistryEntry",
    "Document",
    "DocumentChunk",
    "DocumentIngestionJob",
    "RefreshToken",
    "User",
    "Workspace",
    "WorkspaceMember",
]
