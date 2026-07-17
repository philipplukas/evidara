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
    ExecutionMode,
    FirecrawlMode,
    SourceStatus,
    SourceVersionStatus,
)

LanguageCode = Annotated[str, Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")]

# Court hint for the ch_court_decisions provider. Federal courts use their
# abbreviation (bger, bvger, bstger, bpger); cantonal courts (aggregated via
# entscheidsuche.ch) use the lowercase cantonal code (e.g. zh, be, bs). Kept as
# a validated lowercase token rather than a closed Literal so cantonal coverage
# does not require an enum edit per canton (#531). The provider passes this hint
# straight into ProviderResource.metadata["court"].
CourtHint = Annotated[str, Field(pattern=r"^[a-z]{2,8}$")]


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


class FedlexSparqlAcquisitionSpec(BaseAcquisitionSpec):
    provider: Literal[AcquisitionProvider.FEDLEX_SPARQL] = AcquisitionProvider.FEDLEX_SPARQL
    seed_url: HttpUrl | None = None
    seed_urls: list[HttpUrl] = Field(default_factory=list)
    sparql_endpoint: HttpUrl = "https://fedlex.data.admin.ch/sparqlendpoint"
    preferred_languages: list[LanguageCode] = Field(default_factory=list)
    query_mode: Literal["work_to_expression"] = "work_to_expression"
    max_expressions: int = Field(default=1, ge=1, le=10)
    # Cantonal-discovery mode (#531): scope_kind="canton" discovers works via
    # jolux:CantonOfOrigin instead of seed URIs. See the FedlexSparqlProvider
    # start_run wiring and country-rollout-drift-prevention §4.4.
    scope_kind: Literal["seed", "canton"] = "seed"
    canton: str | None = Field(default=None, pattern=r"^(?:CH-)?[A-Za-z]{2}$")
    max_works: int = Field(default=50, ge=1, le=500)

    @model_validator(mode="after")
    def validate_fedlex_sparql_config(self) -> FedlexSparqlAcquisitionSpec:
        if self.scope_kind == "canton":
            if not self.canton:
                raise ValueError("fedlex_sparql scope_kind=canton requires canton (ISO 3166-2:CH)")
            return self
        if self.seed_url is None and not self.seed_urls:
            raise ValueError("fedlex_sparql provider requires seed_url or seed_urls")
        return self


class RisOgdAcquisitionSpec(BaseAcquisitionSpec):
    provider: Literal[AcquisitionProvider.RIS_OGD] = AcquisitionProvider.RIS_OGD
    base_url: HttpUrl
    applikation: str | None = None
    preferred_formats: list[str] = Field(default_factory=lambda: ["Xml", "Html"])
    page_size: int = Field(default=20, ge=1, le=100)
    max_pages: int = Field(default=50, ge=1, le=500)


class LegifranceAcquisitionSpec(BaseAcquisitionSpec):
    provider: Literal[AcquisitionProvider.LEGIFRANCE] = AcquisitionProvider.LEGIFRANCE
    code_ids: list[str] = Field(default_factory=list)
    max_articles: int = Field(default=100, ge=1, le=5000)
    page_size: int = Field(default=25, ge=1, le=100)


class EurLexSparqlAcquisitionSpec(BaseAcquisitionSpec):
    provider: Literal[AcquisitionProvider.EUR_LEX_SPARQL] = AcquisitionProvider.EUR_LEX_SPARQL
    seed_url: HttpUrl | None = None
    seed_urls: list[HttpUrl] = Field(default_factory=list)
    sparql_endpoint: HttpUrl = "http://publications.europa.eu/webapi/rdf/sparql"
    preferred_languages: list[LanguageCode] = Field(default_factory=list)
    query_mode: Literal["work_to_expression"] = "work_to_expression"
    max_expressions: int = Field(default=1, ge=1, le=10)

    @model_validator(mode="after")
    def validate_eur_lex_sparql_config(self) -> EurLexSparqlAcquisitionSpec:
        if self.seed_url is None and not self.seed_urls:
            raise ValueError("eur_lex_sparql provider requires seed_url or seed_urls")
        return self


class ChCourtDecisionsAcquisitionSpec(BaseAcquisitionSpec):
    provider: Literal[AcquisitionProvider.CH_COURT_DECISIONS] = (
        AcquisitionProvider.CH_COURT_DECISIONS
    )
    seed_url: HttpUrl | None = None
    seed_urls: list[HttpUrl] = Field(default_factory=list)
    index_urls: list[HttpUrl] = Field(default_factory=list)
    court: CourtHint | None = None
    link_pattern: str | None = None
    allowed_hosts: list[str] = Field(default_factory=list)
    max_documents: int = Field(default=50, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_ch_court_decisions_config(self) -> ChCourtDecisionsAcquisitionSpec:
        if self.seed_url is None and not self.seed_urls and not self.index_urls:
            raise ValueError(
                "ch_court_decisions provider requires seed_url, seed_urls, or index_urls"
            )
        return self


class CantonHttpAcquisitionSpec(BaseAcquisitionSpec):
    provider: Literal[AcquisitionProvider.CANTON_HTTP] = AcquisitionProvider.CANTON_HTTP
    # ISO 3166-2:CH cantonal code (e.g. CH-ZH). The provider allow-lists a
    # portal host per code, so an unknown or foreign code is rejected at run.
    canton_code: str = Field(pattern=r"^CH-[A-Z]{2}$")
    seed_url: HttpUrl | None = None
    seed_urls: list[HttpUrl] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_canton_http_config(self) -> CantonHttpAcquisitionSpec:
        if self.seed_url is None and not self.seed_urls:
            raise ValueError("canton_http provider requires seed_url or seed_urls")
        return self


class GemeindeHttpAcquisitionSpec(BaseAcquisitionSpec):
    provider: Literal[AcquisitionProvider.GEMEINDE_HTTP] = AcquisitionProvider.GEMEINDE_HTTP
    # Swiss municipalities have NO ISO 3166-2 code (that standard stops at the
    # canton), so — unlike canton_http/bundesland_http/regione_http — this
    # provider keys its portal allow-list on the BFS/OFS Gemeindenummer, the
    # federal statistical id. It is the same key the 2,110 `jur_ch_gemeinde_*`
    # jurisdiction seeds are generated from, so a template's bfs_number maps
    # 1:1 onto `jur_ch_gemeinde_<bfs_number>` (Zürich = 261).
    bfs_number: int = Field(ge=1, le=9999)
    seed_url: HttpUrl | None = None
    seed_urls: list[HttpUrl] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_gemeinde_http_config(self) -> GemeindeHttpAcquisitionSpec:
        if self.seed_url is None and not self.seed_urls:
            raise ValueError("gemeinde_http provider requires seed_url or seed_urls")
        return self


class BundeslandHttpAcquisitionSpec(BaseAcquisitionSpec):
    provider: Literal[AcquisitionProvider.BUNDESLAND_HTTP] = AcquisitionProvider.BUNDESLAND_HTTP
    # ISO 3166-2:DE Bundesland code (e.g. DE-BY). The provider allow-lists a
    # portal host per code, so an unknown or foreign code is rejected at run.
    bundesland: str = Field(pattern=r"^DE-[A-Z]{2}$")
    seed_url: HttpUrl | None = None
    seed_urls: list[HttpUrl] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_bundesland_http_config(self) -> BundeslandHttpAcquisitionSpec:
        if self.seed_url is None and not self.seed_urls:
            raise ValueError("bundesland_http provider requires seed_url or seed_urls")
        return self


class RegioneHttpAcquisitionSpec(BaseAcquisitionSpec):
    provider: Literal[AcquisitionProvider.REGIONE_HTTP] = AcquisitionProvider.REGIONE_HTTP
    # ISO 3166-2:IT regione code (e.g. IT-25). The provider allow-lists a
    # portal host per code, so an unknown or foreign code is rejected at run.
    regione: str = Field(pattern=r"^IT-[0-9]{2}$")
    seed_url: HttpUrl | None = None
    seed_urls: list[HttpUrl] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_regione_http_config(self) -> RegioneHttpAcquisitionSpec:
        if self.seed_url is None and not self.seed_urls:
            raise ValueError("regione_http provider requires seed_url or seed_urls")
        return self


AcquisitionSpec = Annotated[
    FirecrawlAcquisitionSpec
    | DeterministicHttpAcquisitionSpec
    | FedlexSparqlAcquisitionSpec
    | RisOgdAcquisitionSpec
    | LegifranceAcquisitionSpec
    | EurLexSparqlAcquisitionSpec
    | ChCourtDecisionsAcquisitionSpec
    | CantonHttpAcquisitionSpec
    | GemeindeHttpAcquisitionSpec
    | BundeslandHttpAcquisitionSpec
    | RegioneHttpAcquisitionSpec,
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
    source_id: str = Field(examples=["src_01hzxk7v3qmjy4t5n2p8r6w9"])
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
    execution_mode: ExecutionMode = ExecutionMode.LIVE

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
        raise ValueError("Provide acquisition_spec or both overlay_id and provider_template_id.")


class UpdateSourceVersionRequest(BaseModel):
    version_label: str | None = None
    acquisition_spec: AcquisitionSpec | None = None
    overlay_id: str | None = None
    provider_template_id: str | None = None
    extractor_profile_id: str | None = None
    execution_mode: ExecutionMode | None = None

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
            and self.execution_mode is None
        ):
            raise ValueError("At least one field must be provided.")
        return self


class SourceVersionResponse(BaseModel):
    source_version_id: str = Field(examples=["sv_01hzxk8a2bmne6g4r7j3k9l5"])
    source_id: str
    extractor_profile_id: str | None
    version_label: str
    status: SourceVersionStatus
    execution_mode: ExecutionMode
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
    enabled: bool = Field(
        description="Effective ADR-0030 config key: DB override an operator flipped, "
        "else the shipped source_blueprints.yaml default (fail-closed).",
    )
    live_ready: bool = Field(
        description="ADR-0030 code key: the resolved provider can physically acquire this "
        "format. Stays in code — it is an engineering assertion, not operator state.",
    )
    launchable: bool = Field(
        description="Both keys turned — a live run will not be blocked by the two-key lock.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Human-readable explanation of any closed key (why the template is inert).",
    )


class SourceBlueprintTemplateResponse(BaseModel):
    overlay_id: str
    provider_template_id: str
    provider: str
    enabled: bool = Field(
        description="Effective ADR-0030 config key: DB override an operator flipped, "
        "else the shipped source_blueprints.yaml default (fail-closed).",
    )
    live_ready: bool = Field(
        description="ADR-0030 code key: the resolved provider can physically acquire this format.",
    )
    launchable: bool = Field(
        description="Both keys turned — a live run will not be blocked by the two-key lock.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Human-readable explanation of any closed key (why the template is inert).",
    )


class SourceBlueprintTemplateListResponse(BaseModel):
    data: list[SourceBlueprintTemplateResponse]


class BlueprintTemplateEnablementRequest(BaseModel):
    """Operator flip of the ADR-0030 config key (#632)."""

    enabled: bool
    note: str | None = Field(
        default=None,
        description="Why the key was flipped — e.g. a link to captured acceptance-run evidence.",
    )


class BlueprintTemplateEnablementResponse(BaseModel):
    overlay_id: str
    provider_template_id: str
    enabled: bool = Field(description="Effective config key after the flip.")
    default_enabled: bool = Field(description="The shipped source_blueprints.yaml default.")
    source: str = Field(description="'override' (an operator flipped it) or 'default' (shipped).")
    note: str | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None
