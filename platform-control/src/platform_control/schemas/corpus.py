from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateCorpusRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    tenant_id: str = Field(default="tenant_public", pattern=r"^tenant_[a-z0-9_]+$")
    scope_type: Literal["global_public", "tenant_private", "tenant_shared"] = "global_public"


class UpdateCorpusRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    scope_type: Literal["global_public", "tenant_private", "tenant_shared"] | None = None


class ArchiveCorpusRequest(BaseModel):
    """Request body for archiving a corpus (sets status → archived)."""


class CorpusResponse(BaseModel):
    corpus_id: str
    name: str
    description: str | None
    tenant_id: str
    scope_type: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CorpusListResponse(BaseModel):
    data: list[CorpusResponse]
    total: int | None = None
    limit: int | None = None
    offset: int | None = None
