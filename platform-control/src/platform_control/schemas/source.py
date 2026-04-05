from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from platform_control.domain import (
    AcquisitionProvider,
    FirecrawlMode,
    SourceStatus,
    SourceVersionStatus,
)

LanguageCode = Annotated[str, Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")]


class FirecrawlAcquisitionSpec(BaseModel):
    provider: AcquisitionProvider = AcquisitionProvider.FIRECRAWL
    seed_url: HttpUrl | None = None
    seed_urls: list[HttpUrl] = Field(default_factory=list)
    mode: FirecrawlMode = FirecrawlMode.CRAWL
    include_paths: list[str] = Field(default_factory=list)
    exclude_paths: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=500)
    max_discovery_depth: int = Field(default=2, ge=0, le=10)
    scrape_formats: list[str] = Field(default_factory=lambda: ["markdown", "html"])
    zero_data_retention: bool = False
    tenant_id: str = Field(default="tenant_public", pattern=r"^tenant_[a-z0-9_]+$")
    corpus_id: str = Field(default="corpus_public_default", pattern=r"^corpus_[a-z0-9_]+$")
    scope_type: Literal["global_public", "tenant_private", "tenant_shared"] = "global_public"
    source_origin_kind: Literal[
        "official_primary",
        "official_mirror",
        "licensed_provider",
        "community_curated",
        "tenant_internal",
    ] = "official_primary"
    trust_tier: Literal["authoritative", "preferred", "supplemental", "untrusted"] = "authoritative"
    language_codes: list[LanguageCode] = Field(default_factory=list)
    document_type_hint: str | None = None
    request_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    user_agent: str | None = None
    max_content_bytes: int = Field(default=2_000_000, ge=50_000, le=10_000_000)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_provider_config(self) -> FirecrawlAcquisitionSpec:
        if self.provider is AcquisitionProvider.FIRECRAWL:
            if self.mode is FirecrawlMode.CRAWL and self.seed_url is None:
                raise ValueError("firecrawl crawl mode requires seed_url")
            if self.mode is FirecrawlMode.BATCH_SCRAPE and not self.seed_urls:
                raise ValueError("firecrawl batch_scrape mode requires seed_urls")
            return self

        if self.provider is AcquisitionProvider.DETERMINISTIC_HTTP:
            if self.seed_url is None and not self.seed_urls:
                raise ValueError("deterministic_http provider requires seed_url or seed_urls")
            return self
        return self


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

    @model_validator(mode="after")
    def validate_has_changes(self) -> UpdateSourceVersionRequest:
        if (
            self.version_label is None
            and self.acquisition_spec is None
            and self.extractor_profile_id is None
        ):
            raise ValueError("At least one field must be provided.")
        return self


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
