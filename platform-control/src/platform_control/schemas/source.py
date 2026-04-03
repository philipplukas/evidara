from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from platform_control.domain import FirecrawlMode, SourceStatus, SourceVersionStatus


class FirecrawlAcquisitionSpec(BaseModel):
    seed_url: HttpUrl | None = None
    seed_urls: list[HttpUrl] = Field(default_factory=list)
    mode: FirecrawlMode = FirecrawlMode.CRAWL
    include_paths: list[str] = Field(default_factory=list)
    exclude_paths: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=500)
    max_discovery_depth: int = Field(default=2, ge=0, le=10)
    scrape_formats: list[str] = Field(default_factory=lambda: ["markdown", "html"])
    zero_data_retention: bool = False

    model_config = ConfigDict(extra="forbid")


class CreateSourceRequest(BaseModel):
    name: str
    description: str | None = None
    jurisdiction_id: str
    authority_id: str
    source_type: Literal["website"] = "website"
    document_family: str | None = None


class SourceResponse(BaseModel):
    source_id: str
    name: str
    description: str | None
    jurisdiction_id: str
    authority_id: str
    source_type: str
    document_family: str | None
    status: SourceStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SourceListResponse(BaseModel):
    data: list[SourceResponse]


class CreateSourceVersionRequest(BaseModel):
    version_label: str
    acquisition_spec: FirecrawlAcquisitionSpec
    extractor_profile_id: str | None = None


class UpdateSourceVersionRequest(BaseModel):
    version_label: str | None = None
    acquisition_spec: FirecrawlAcquisitionSpec | None = None
    extractor_profile_id: str | None = None


class SourceVersionResponse(BaseModel):
    source_version_id: str
    source_id: str
    extractor_profile_id: str | None
    version_label: str
    status: SourceVersionStatus
    acquisition_spec: FirecrawlAcquisitionSpec
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SourceVersionListResponse(BaseModel):
    data: list[SourceVersionResponse]
