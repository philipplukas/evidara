from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
    ValidationError,
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
    # FEDERAL only, still. A `scope_kind: canton` discovery mode existed here
    # until #716; it was removed because `jolux:CantonOfOrigin` does not exist
    # and Fedlex publishes no cantonal law at all (measured — see the SCOPE note
    # in services/fedlex_sparql_provider.py). Cantonal coverage needs a
    # per-canton provider, not a field on this spec. `enumeration` below does not
    # reopen that: it walks the federal Systematic Collection and nothing else.
    #
    # `sr_collection` resolves the seed works from the endpoint at run start
    # instead of from `seed_urls`. Without it this provider can only acquire what
    # an operator pasted in, which is why five enabled federal templates named 16
    # URIs between them.
    enumeration: Literal["sr_collection"] | None = None
    # Bounds an enumerating run. None means unbounded — ~17k works, so set it
    # deliberately. The provider reports whether the walk exhausted the collection
    # or stopped on this cap, so a truncated run is never read as the whole SR.
    max_works: int | None = Field(default=None, ge=1, le=50_000)

    @model_validator(mode="after")
    def validate_fedlex_sparql_config(self) -> FedlexSparqlAcquisitionSpec:
        # Seeds OR enumeration — never neither. An enumerating spec that also
        # carried seeds would silently ignore them at run start, so requiring
        # exactly one keeps the spec honest about what it will fetch.
        if self.enumeration is not None:
            if self.seed_url is not None or self.seed_urls:
                raise ValueError(
                    "fedlex_sparql enumeration resolves its own works; remove seed_url/seed_urls"
                )
            return self
        if self.seed_url is None and not self.seed_urls:
            raise ValueError(
                "fedlex_sparql provider requires seed_url or seed_urls, or enumeration"
            )
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
    # A template either SEARCHES a branch or ENUMERATES a corpus. Exactly one is
    # required, and the model validator below enforces it — so a config that would
    # be refused by the API, or that would silently sweep every entity, is refused
    # here instead of at request time.
    #
    # `systematic_digit_union`: one query per digit 0-9 over systematic numbers,
    # deduplicated by tol id. Matching is `contains` and every systematic number
    # carries a digit, so the union is the whole entity by construction. Verified
    # on ZH 2026-07-28 — 1377 unique records against a published total of 1377
    # (#816). The run reconciles itself against `entities/extended`.
    enumeration: Literal["systematic_digit_union"] | None = None
    # LexFind has NO list-everything call: the search endpoint rejects an empty
    # `search_text` with a 400 (verified live 2026-07-22), so a searching template
    # must supply one. Optional at this level only because an enumerating template
    # does not search at all.
    search_text: str | None = Field(default=None, min_length=1)
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

    @model_validator(mode="after")
    def _require_a_discovery_strategy(self) -> LexFindAcquisitionSpec:
        if self.enumeration is None and not self.search_text:
            raise ValueError(
                "lexfind_api requires search_text (a systematic-number prefix, e.g. "
                "'554') or enumeration: systematic_digit_union to hold the whole corpus"
            )
        if self.enumeration is not None and not self.entity_ids:
            raise ValueError(
                "lexfind_api enumeration requires entity_ids — an unscoped sweep "
                "would pull every entity LexFind carries (~33 000 texts of law)"
            )
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


#: The attributes a `SourceVersion` ORM row contributes to `SourceVersionResponse`.
#: Named explicitly because the `mode="before"` validator below has to normalise an
#: ORM instance into a mapping before it can inspect `acquisition_spec`, and reading
#: whatever happens to be on the object would drag relationships in with it.
_SOURCE_VERSION_RESPONSE_ATTRS = (
    "source_version_id",
    "source_id",
    "extractor_profile_id",
    "version_label",
    "status",
    "execution_mode",
    "acquisition_spec",
    "created_at",
    "updated_at",
)


def _summarise_spec_error(error: ValidationError) -> str:
    """One operator-readable line per failed location, joined.

    Pydantic's own `str(exc)` carries a docs URL and the full input on every line.
    The input is the stored spec, which can be large and can carry credentials in a
    provider config, so only the location and the message are reported.
    """
    parts = []
    for detail in error.errors():
        location = ".".join(str(item) for item in detail["loc"]) or "<root>"
        parts.append(f"{location}: {detail['msg']}")
    return "; ".join(parts) or "acquisition_spec did not validate"


class SourceVersionResponse(BaseModel):
    source_version_id: str = Field(examples=["sv_01hzxk8a2bmne6g4r7j3k9l5"])
    source_id: str
    extractor_profile_id: str | None
    version_label: str
    status: SourceVersionStatus
    execution_mode: ExecutionMode
    # Both fields are declared without a default, so both stay `required` in the
    # generated contract: the key is always on the wire. A client that has to tell
    # "absent key" from "null value" from "missing field" is back to guessing, which
    # is the failure mode this whole change is about.
    acquisition_spec: AcquisitionSpec | None = Field(
        description=(
            "The stored acquisition spec. `null` **only** when the stored JSON no "
            "longer validates against any known provider, in which case "
            "`acquisition_spec_error` says why. A null spec is therefore never "
            "'this version has no spec' — see #953 and ADR-0052."
        ),
    )
    acquisition_spec_error: str | None = Field(
        description=(
            "Why the stored acquisition spec could not be read back, or `null` when "
            "it read back fine. Set together with a null `acquisition_spec`; exactly "
            "one of the two is always populated."
        ),
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def report_unreadable_acquisition_spec(cls, value: object) -> object:
        """Report a spec that no longer validates instead of raising over it (#953).

        `acquisition_spec` is a union discriminated on `provider`. A stored row whose
        JSON predates a provider, or was written past the service layer, therefore
        blows up **response construction** — which surfaces as an unhandled 500 on
        `GET /v1/sources/{id}/versions`, not as a report about one row. The admin's
        dashboard then rendered that 500 as an em dash, identical to "this source has
        no versions": a failure read as an absence, which is the defect ADR-0052 names.

        So the row still comes back, carrying the reason its spec is unreadable. The
        `mode="after"` guard below is what keeps the null from ever standing alone.
        """
        if isinstance(value, BaseModel):
            return value

        from_row = not isinstance(value, dict)
        if from_row:
            data = {
                name: getattr(value, name)
                for name in _SOURCE_VERSION_RESPONSE_ATTRS
                if hasattr(value, name)
            }
        else:
            data = dict(value)

        # An ORM row has no `acquisition_spec_error` attribute — this is the only
        # producer of that field, so it fills in the "nothing wrong" case too.
        data.setdefault("acquisition_spec_error", None)

        raw_spec = data.get("acquisition_spec")
        if isinstance(raw_spec, BaseModel):
            return data
        if raw_spec is None:
            # The column is `NOT NULL`, so this should be unreachable — but "should
            # be" is what the pre-#953 code assumed about the spec's shape, and the
            # mutual-exclusion guard below would turn a surprise here straight back
            # into the 500 this change exists to remove. A row is never dropped and
            # never silently blank: it says what we found.
            if from_row:
                data["acquisition_spec_error"] = (
                    data["acquisition_spec_error"] or "<root>: stored acquisition_spec is null"
                )
            return data

        try:
            AcquisitionSpecAdapter.validate_python(raw_spec)
        except ValidationError as exc:
            data["acquisition_spec"] = None
            data["acquisition_spec_error"] = _summarise_spec_error(exc)
        return data

    @model_validator(mode="after")
    def spec_is_readable_or_says_why(self) -> SourceVersionResponse:
        """Exactly one of `acquisition_spec` / `acquisition_spec_error` is populated.

        Without this, a null spec with no reason would be constructible, and the wire
        payload would say "no spec" for a version that has one we could not read —
        the same absent-vs-broken collapse one layer down. Deleting this guard makes
        `test_null_spec_without_a_reason_is_refused` fail.
        """
        has_spec = self.acquisition_spec is not None
        has_error = self.acquisition_spec_error is not None
        if has_spec == has_error:
            raise ValueError(
                "acquisition_spec and acquisition_spec_error are mutually exclusive "
                "and jointly exhaustive: a version either has a readable spec or a "
                "stated reason it has none."
            )
        return self


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
    """Operator flip of the ADR-0030 config key (#632), with its evidence (#854).

    Until #854 this carried `enabled` and a free-text `note`, and the note being
    non-empty was the entire precondition for arming a template. The CLI meanwhile
    required a cited acceptance run and refused with eight named codes, so the two
    paths to the same state differed sharply in rigour and **the easier one was the
    weaker one**. The guard now lives on the server and these are the inputs it needs.
    """

    enabled: bool
    note: str | None = Field(
        default=None,
        description=(
            "Why the key was flipped. Required in both directions: it is the only "
            "durable record of why this template was trusted, or why a portal was shut "
            "off."
        ),
    )
    evidence_run_id: str | None = Field(
        default=None,
        description=(
            "Run whose acceptance evidence earns the flip (ADR-0030 §5). Required to "
            "enable; ignored when disabling. The server re-derives the acceptance "
            "verdict from this run and binds it to this template — a run of a different "
            "template on the same provider is refused (#846)."
        ),
    )
    reopen_operator_kill_switch: bool = Field(
        default=False,
        description=(
            "Acknowledge reopening a key an operator deliberately shut. Acceptance "
            "evidence does not waive a kill switch (ADR-0030 §2, #768)."
        ),
    )
    acknowledge_provider_below_live: bool = Field(
        default=False,
        description=(
            "Acknowledge arming the config key before the provider's code key reaches "
            "`live`. ADR-0030 §2 wants LIVE first."
        ),
    )


class BlueprintTemplateEnablementRefusal(BaseModel):
    """One machine-readable reason the flip did not happen."""

    code: str = Field(
        description=(
            "Stable refusal code. The same vocabulary `evidara workflow coverage "
            "enable` reports, so an agent branches on the code and never on prose."
        ),
        examples=["operator_kill_switch_not_acknowledged"],
    )
    detail: str = Field(description="Operator-facing explanation of the refusal.")


class BlueprintTemplateAcceptanceVerdict(BaseModel):
    """Whether the cited run may be cited as ADR-0030 acceptance evidence."""

    is_acceptance_evidence: bool
    refusals: list[BlueprintTemplateEnablementRefusal] = Field(default_factory=list)
    run_id: str | None = None
    mode: str | None = None
    execution_mode: str | None = None
    captured_resources_count: int | None = None


EVIDENCE_BINDING_DESCRIPTION = (
    "How tightly the cited run is bound to *this* template. 'template' is exact — the "
    "run's source version records this overlay and provider template. "
    "'acquisition_spec' is near-exact — the version has no blueprint provenance but its "
    "resolved spec equals this template's, so `needs_human` is set. 'provider' and "
    "'none' are too weak to enable on and are refused: all 26 cantons and Bund sit "
    "behind the single `lexfind` provider (#846)."
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
    applied: bool = Field(
        default=True,
        description=(
            "The flip was confirmed by re-reading the template: the effective key is "
            "what was asked for AND the read model attributes it to an operator "
            "override. A 200 alone cannot tell a flip from a write that silently did "
            "nothing (#631, #713), so never report a flip on the status code."
        ),
    )
    needs_human: bool = Field(
        default=False,
        description=(
            "The flip happened but at least one thing was not decided for you — read "
            "`needs_human_reasons`. Set when the evidence bound to the template only by "
            "acquisition-spec equality, when the code key is still below `live`, or "
            "when an operator's kill switch was reopened."
        ),
    )
    needs_human_reasons: list[str] = Field(default_factory=list)
    evidence_run_id: str | None = None
    evidence_binding: str | None = Field(default=None, description=EVIDENCE_BINDING_DESCRIPTION)
    acceptance_verdict: BlueprintTemplateAcceptanceVerdict | None = None


class BlueprintTemplateEnablementRefusedResponse(BaseModel):
    """The 409 body when the ADR-0030 guard refuses to move the config key (#854).

    Carries `detail` so a client that only knows the uniform error envelope still gets
    a usable message, and `refusals` so one that does not can render the codes.
    """

    detail: str = Field(description="Human-readable summary — the first refusal's detail.")
    correlation_id: str | None = None
    overlay_id: str
    provider_template_id: str
    refusals: list[BlueprintTemplateEnablementRefusal]
    needs_human: bool = True
    write_attempted: bool = Field(
        description=(
            "False for a pre-write refusal: nothing was written and the key is "
            "unchanged. True only when the override row was written and the read-back "
            "then failed to confirm it — the key's state is then whatever the read-back "
            "reports, not what was requested."
        ),
    )
    evidence_run_id: str | None = None
    evidence_binding: str | None = Field(default=None, description=EVIDENCE_BINDING_DESCRIPTION)
    acceptance_verdict: BlueprintTemplateAcceptanceVerdict | None = None
