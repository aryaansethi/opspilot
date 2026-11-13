import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceType = Literal["runbook", "architecture", "incident_report", "other"]
MimeType = Literal["application/pdf", "text/markdown", "text/plain"]


class UploadUrlRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\\x00]+$")
    mime_type: MimeType
    size_bytes: int = Field(gt=0)
    source_type: SourceType
    title: str | None = Field(default=None, max_length=255)
    service: str | None = Field(default=None, max_length=120)
    environment: str | None = Field(default=None, max_length=40)


class UploadUrlResponse(BaseModel):
    document_id: uuid.UUID
    upload_url: str
    headers: dict[str, str]


class CompleteUploadRequest(BaseModel):
    document_id: uuid.UUID


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    filename: str
    source_type: SourceType
    service: str | None
    environment: str | None
    mime_type: str
    size_bytes: int
    status: str
    error: str | None
    chunk_count: int
    indexed_at: datetime | None
    embedding_model: str | None
    created_at: datetime


class DocumentStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    status: str
    error: str | None
    chunk_count: int
    indexed_at: datetime | None


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    chunk_index: int
    section_path: str | None
    page_start: int | None
    page_end: int | None
    content: str
    token_estimate: int


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None
