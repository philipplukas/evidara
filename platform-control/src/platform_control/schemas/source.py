from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
    field_validator,
    model_validator,
)

from platform_control.domain import (
    AcquisitionProvider,
    FirecrawlMode,
    SourceStatus,
    SourceVersionStatus,
)

LanguageCode = Annotated[str, Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")]


class BaseAcquisitionSpec(BaseModel):
    # --- Shared provenance / manifest defaults ---
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

    # --- HTTP transport ---
    request_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    user_agent: str | None = None
    max_content_bytes: int = Field(default=2_000_000, ge=50_000, le=10_000_000)

    model_config = ConfigDict(extra="forbid")

class FirecrawlAcquisitionSpec(BaseAcquisitionSpec):
    provider: Literal[AcquisitionProvider.FIRECRAWL] = AcquisitionProvider.FIRECRAWL
    seed_url: HttpUrl | None = None
    seed_urls: list[HttpUrl] = Field(default_factory=list)
    mode: FirecrawlMode = FirecrawlMode.CRAWL
    include_paths: list[str] = Field(default_factory=list)
    exclude_paths: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=500)
    max_discovery_depth: int = Field(default=2, ge=0, le=10)
    scrape_formats: list[str] = Field(default_factory=lambda: ["markdown", "html"])
    zero_data_retention: bool = False

    @model_validator(mode="after")
    def validate_firecrawl_config(self) -> FirecrawlAcquisitionSpec:
        if self.mode is FirecrawlMode.CRAWL and self.seed_url is None:
            raise ValueError("firecrawl crawl mode requires seed_url")
        if self.mode is FirecrawlMode.BATCH_SCRAPE and not self.seed_urls:
            raise ValueError("firecrawl batch_scrape mode requires seed_urls")
        return self


class DeterministicHttpAcquisitionSpec(BaseAcquisitionSpec):
    provider: Literal[AcquisitionProvider.DETERMINISTIC_HTTP] = (
        AcquisitionProvider.DETERMINISTIC_HTTP
    )
    seed_url: HttpUrl | None = None
    seed_urls: list[HttpUrl] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_deterministic_http_config(self) -> DeterministicHttpAcquisitionSpec:
        if self.seed_url is None and not self.seed_urls:
            raise ValueError("deterministic_http provider requires seed_url or seed_urls")
        return self


class RisOgdAcquisitionSpec(BaseAcquisitionSpec):
    provider: Literal[AcquisitionProvider.RIS_OGD] = AcquisitionProvider.RIS_OGD
    base_url: HttpUrl
    applikation: str | None = None
    preferred_formats: list[str] = Field(default_factory=lambda: ["Xml", "Html"])
    page_size: int = Field(default=20, ge=1, le=100)
    max_pages: int = Field(default=50, ge=1, le=500)


AcquisitionSpec = Annotated[
    FirecrawlAcquisitionSpec | DeterministicHttpAcquisitionSpec | RisOgdAcquisitionSpec,
    Field(discriminator="provider"),
]
AcquisitionSpecAdapter = TypeAdapter(AcquisitionSpec)


def parse_acquisition_spec(raw: object) -> AcquisitionSpec:
    return AcquisitionSpecAdapter.validate_python(raw)


class CreateSourceRequest(BaseModel):
    name: str
    description: str | None = None
    jurisdiction_id: str
    authority_id: str
    source_type: Literal["website", "api"] = "website"
    document_family: str | None = None


class CreateSourceWithVersionRequest(BaseModel):
    source: CreateSourceRequest
    source_version: CreateSourceVersionRequest


class SourceBlueprintPreviewRequest(BaseModel):
    overlay_id: str
    provider_template_id: str


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
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class CreateSourceVersionRequest(BaseModel):
    version_label: str
    acquisition_spec: AcquisitionSpec | None = None
    overlay_id: str | None = None
    provider_template_id: str | None = None
    extractor_profile_id: str | None = None

    @field_validator("acquisition_spec", mode="before")
    @classmethod
    def inject_default_provider_for_legacy_payload(cls, value: object) -> object:
        if isinstance(value, dict) and "provider" not in value:
            return {
                "provider": AcquisitionProvider.FIRECRAWL.value,
                **value,
            }
        return value

    @model_validator(mode="after")
    def validate_blueprint_or_spec(self) -> CreateSourceVersionRequest:
        has_spec = self.acquisition_spec is not None
        has_blueprint = bool(self.overlay_id or self.provider_template_id)
        if has_spec and has_blueprint:
            raise ValueError(
                "Provide either acquisition_spec or overlay_id/provider_template_id, not both."
            )
        if has_spec:
            return self
        if self.overlay_id and self.provider_template_id:
            return self
        raise ValueError(
            "Provide acquisition_spec or both overlay_id and provider_template_id."
        )


class UpdateSourceVersionRequest(BaseModel):
    version_label: str | None = None
    acquisition_spec: AcquisitionSpec | None = None
    overlay_id: str | None = None
    provider_template_id: str | None = None
    extractor_profile_id: str | None = None

    @field_validator("acquisition_spec", mode="before")
    @classmethod
    def inject_default_provider_for_legacy_payload(cls, value: object) -> object:
        if isinstance(value, dict) and "provider" not in value:
            return {
                "provider": AcquisitionProvider.FIRECRAWL.value,
                **value,
            }
        return value

    @model_validator(mode="after")
    def validate_has_changes(self) -> UpdateSourceVersionRequest:
        has_spec = self.acquisition_spec is not None
        has_blueprint = bool(self.overlay_id or self.provider_template_id)
        if has_spec and has_blueprint:
            raise ValueError(
                "Provide either acquisition_spec or overlay_id/provider_template_id, not both."
            )
        if has_blueprint and not (self.overlay_id and self.provider_template_id):
            raise ValueError("overlay_id and provider_template_id must be provided together.")

        if (
            self.version_label is None
            and self.acquisition_spec is None
            and self.overlay_id is None
            and self.provider_template_id is None
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
    acquisition_spec: AcquisitionSpec
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SourceVersionListResponse(BaseModel):
    data: list[SourceVersionResponse]


class CreateSourceWithVersionResponse(BaseModel):
    source: SourceResponse
    source_version: SourceVersionResponse


class SourceBlueprintPreviewResponse(BaseModel):
    overlay_id: str
    provider_template_id: str
    acquisition_spec: AcquisitionSpec


class SourceBlueprintTemplateResponse(BaseModel):
    overlay_id: str
    provider_template_id: str
    provider: str


class SourceBlueprintTemplateListResponse(BaseModel):
    data: list[SourceBlueprintTemplateResponse]
