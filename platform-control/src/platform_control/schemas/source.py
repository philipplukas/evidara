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

from acquisition_core.providers import AcquisitionReadiness
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
    # Federal seed mode only. A `scope_kind: canton` discovery mode existed here
    # until #716; it was removed because `jolux:CantonOfOrigin` does not exist
    # and Fedlex publishes no cantonal law at all (measured — see the SCOPE note
    # in services/fedlex_sparql_provider.py). Cantonal coverage needs a
    # per-canton provider, not a field on this spec.

    @model_validator(mode="after")
    def validate_fedlex_sparql_config(self) -> FedlexSparqlAcquisitionSpec:
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


class LexFindAcquisitionSpec(BaseAcquisitionSpec):
    provider: Literal[AcquisitionProvider.LEXFIND_API] = AcquisitionProvider.LEXFIND_API
    # LexFind has NO list-everything call: `search_text` is required by the API
    # and an empty string is a 400 (verified live 2026-07-22). Discovery is
    # therefore always a query, and the enumeration strategy is a systematic
    # number prefix -- "554" scoped to entity 26 returns the whole ZH
    # animal-protection branch. Required here, with a min_length, so a template
    # that would be refused by the API is refused at config time instead.
    search_text: str = Field(min_length=1)
    # LexFind's own entity ids, not ISO codes: 26 = Zürich. There are 28
    # (26 cantons + Bund + a federal-court entity); an empty list means every
    # entity, which is legal but almost never intended.
    entity_ids: list[int] = Field(default_factory=list)
    category_ids: list[int] = Field(default_factory=list)
    language: LanguageCode = "de"
    results_per_page: int = Field(default=50, ge=1, le=100)
    max_pages: int = Field(default=40, ge=1, le=200)
    max_documents: int = Field(default=0, ge=0)
    # Floor for the capture guard. The smallest real cantonal act measured was
    # 84 740 bytes (Hundegesetz, 33 pages); this sits far below it so a short
    # ordinance is not refused, while #716's 142-byte stub cannot pass.
    min_pdf_bytes: int = Field(default=2000, ge=0)
    request_timeout_seconds: float = Field(default=20.0, gt=0)


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
    | LexFindAcquisitionSpec
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


class BlueprintSeedOverride(BaseModel):
    """Operator-supplied seeds applied over a blueprint template's spec (#710).

    The middle rung of the reuse ladder: "the existing template's shape, with my
    seeds". Only the seed lists are expressible here — the provider, the
    tenant/corpus/scope binding, the trust tier, and the portal-identifying
    config stay whatever the blueprint says, and the merged seeds must still sit
    on an origin the template itself reaches. See ADR-0046.
    """

    seed_url: HttpUrl | None = None
    seed_urls: list[HttpUrl] | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_not_empty(self) -> BlueprintSeedOverride:
        if self.seed_url is None and self.seed_urls is None:
            raise ValueError("blueprint_overrides must set seed_url and/or seed_urls.")
        if self.seed_urls is not None and not self.seed_urls:
            raise ValueError("blueprint_overrides.seed_urls must not be empty.")
        return self


class SourceBlueprintPreviewRequest(BaseModel):
    overlay_id: str
    provider_template_id: str
    blueprint_overrides: BlueprintSeedOverride | None = None


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
    blueprint_overrides: BlueprintSeedOverride | None = None
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
                "Provide either acquisition_spec or overlay_id/provider_template_id, not both. "
                "To reuse a template with different seeds, send overlay_id/"
                "provider_template_id plus blueprint_overrides."
            )
        if has_spec:
            if self.blueprint_overrides is not None:
                raise ValueError(
                    "blueprint_overrides applies to a blueprint template; it cannot accompany "
                    "a hand-written acquisition_spec."
                )
            return self
        if self.overlay_id and self.provider_template_id:
            return self
        raise ValueError("Provide acquisition_spec or both overlay_id and provider_template_id.")


class UpdateSourceVersionRequest(BaseModel):
    version_label: str | None = None
    acquisition_spec: AcquisitionSpec | None = None
    overlay_id: str | None = None
    provider_template_id: str | None = None
    blueprint_overrides: BlueprintSeedOverride | None = None
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
                "Provide either acquisition_spec or overlay_id/provider_template_id, not both. "
                "To reuse a template with different seeds, send overlay_id/"
                "provider_template_id plus blueprint_overrides."
            )
        if has_spec and self.blueprint_overrides is not None:
            raise ValueError(
                "blueprint_overrides applies to a blueprint template; it cannot accompany "
                "a hand-written acquisition_spec."
            )
        if has_blueprint and not (self.overlay_id and self.provider_template_id):
            raise ValueError("overlay_id and provider_template_id must be provided together.")

        if (
            self.version_label is None
            and self.acquisition_spec is None
            and self.overlay_id is None
            and self.provider_template_id is None
            and self.blueprint_overrides is None
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
        description="ADR-0030 code key, as a boolean: true only when acquisition_readiness "
        "is 'live'. Retained so existing clients keep working; prefer "
        "acquisition_readiness, which distinguishes a scaffold from a provider that is "
        "merely awaiting acceptance evidence (#743).",
    )
    acquisition_readiness: AcquisitionReadiness = Field(
        default=AcquisitionReadiness.SCAFFOLD,
        description=(
            "ADR-0030 code key, three-state. 'scaffold' = the provider cannot acquire its "
            "targets and needs engineering (usually a stub start_run, sometimes a real one "
            "facing sources it cannot fetch); 'awaiting_evidence' = implemented and "
            "verified, but no acceptance run captured yet (the operator can run one "
            "themselves); 'live' = evidence accepted. `live_ready` is the legacy boolean "
            "projection of this field and is true only for 'live'."
        ),
    )
    launchable: bool = Field(
        description="Both keys turned — a live run will not be blocked by the two-key lock.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Human-readable explanation of any closed key (why the template is inert).",
    )
    plan_notes: list[str] = Field(
        default_factory=list,
        description=(
            "The provider's own `plan()` notes for this spec (#634) — seed URLs it would "
            "hit, config errors, and provider-specific caveats. Distinct from `notes`, "
            "which explains the two-key lock; these describe the acquisition itself. "
            "Empty when the provider exposes no plan or plan computation failed."
        ),
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
        description="ADR-0030 code key, as a boolean: true only when acquisition_readiness "
        "is 'live'. Retained so existing clients keep working; prefer "
        "acquisition_readiness (#743).",
    )
    acquisition_readiness: AcquisitionReadiness = Field(
        default=AcquisitionReadiness.SCAFFOLD,
        description=(
            "ADR-0030 code key, three-state. 'scaffold' = the provider cannot acquire its "
            "targets and needs engineering (usually a stub start_run, sometimes a real one "
            "facing sources it cannot fetch); 'awaiting_evidence' = implemented and "
            "verified, but no acceptance run captured yet (the operator can run one "
            "themselves); 'live' = evidence accepted. `live_ready` is the legacy boolean "
            "projection of this field and is true only for 'live'."
        ),
    )
    launchable: bool = Field(
        description="Both keys turned — a live run will not be blocked by the two-key lock.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Human-readable explanation of any closed key (why the template is inert).",
    )
    default_enabled: bool = Field(
        description="The shipped source_blueprints.yaml default for the config key.",
    )
    source: str = Field(
        description="Provenance of the effective config key: 'override' (an operator flipped "
        "it) or 'default' (running on the shipped value, never touched).",
    )
    note: str | None = Field(
        default=None,
        description="Evidence note the operator recorded with the override, if any.",
    )
    updated_by: str | None = Field(
        default=None,
        description="Operator identity that last flipped the override. Key-shaped, not "
        "person-shaped: every human sharing an operator API key resolves to the same row.",
    )
    updated_at: datetime | None = Field(
        default=None, description="When the override was last written."
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
