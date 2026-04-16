# Vocabulary standards

Owner: Contracts / Architecture
Last reviewed: 2026-04-16
Applies to: the controlled vocabularies under `contracts/vocabularies/`
and the overlay schema under `contracts/schemas/country-overlay.schema.json`

## Purpose

Evidara needs vocabularies that are **accurate with respect to law** and
**scale** across the five source countries (CH, AT, DE, FR, IT), the
European Union, and eventually further European jurisdictions. This
document records the decision on which external standards we anchor on,
which we do not adopt, and which Evidara file owns each concept.

## Anchor standards

| Concept | Standard anchored on | Evidara file |
|---|---|---|
| Country codes | **ISO 3166-1 alpha-2** | [`contracts/vocabularies/jurisdiction.json`](../../contracts/vocabularies/jurisdiction.json) |
| Sub-federal subdivision codes | **ISO 3166-2** | [`contracts/vocabularies/subdivisions.json`](../../contracts/vocabularies/subdivisions.json) |
| Legislation identity | **ELI** (European Legislation Identifier) on top of **FRBR** Work / Expression / Manifestation | Emitted by providers (e.g. `fedlex_sparql_provider.py`); carried in `metadata.eli` per [`contracts/schemas/document.schema.json`](../../contracts/schemas/document.schema.json) |
| Case law identity | **ECLI** (European Case Law Identifier) | Citation extractor recognizes `ECLI:EU:*`; carried in `metadata.ecli` |
| Document class | **ELI `legal_type`** + **Akoma Ntoso** document-class hierarchy | [`contracts/vocabularies/source-family.json`](../../contracts/vocabularies/source-family.json) (canonical UI set + ELI-aligned richer set with `broader` links) |
| Court hierarchy | **ECLI court codes** per country | [`contracts/vocabularies/court-level.json`](../../contracts/vocabularies/court-level.json) |
| Language | **ISO 639-1** | [`contracts/vocabularies/language.json`](../../contracts/vocabularies/language.json) |
| Subject / topic | **EuroVoc** (SKOS thesaurus, 7k+ concepts, 24 languages) | deferred; no Evidara file yet |
| Vocabulary serialization | **SKOS** field names (`prefLabel`, `altLabel`, `broader`) inside plain JSON | all Evidara vocabulary files use this shape |

## Why this combination

- **ELI + ECLI are the real contract of European legal publishing.** Fedlex,
  Légifrance, EUR-Lex, several DE Länder, the Italian Normattiva portal, and
  AT RIS all either publish or accept these identifiers. Anchoring on them
  means our canonical output can round-trip against any of these systems
  without a bespoke translation layer.
- **FRBR is the model underneath ELI.** The Work/Expression/Manifestation
  triple is already how `fedlex_sparql_provider.py` navigates. Making FRBR
  explicit in docs lets the EUR-Lex scaffold reuse the exact same code path.
- **ISO 3166-1 / 3166-2 is the only workable country + subdivision code.**
  ISO 3166-2 gives us unambiguous codes for all 26 CH cantons, 9 AT
  Bundesländer, 16 DE Länder, 18 FR régions and 20 IT regioni. Everything
  downstream (hierarchy path, icon key, provider token) derives from the
  ISO code through `subdivisions.json`.
- **Akoma Ntoso gives us the deepest document-class hierarchy** when we
  need it (act, bill, judgment, report, statement, debaterecord,
  documentcollection, doc). We take the class vocabulary only, not the
  XML serialization.
- **EuroVoc** covers subject classification and will land when we start
  faceting by topic. Staying on SKOS field names now makes that future
  jump a data migration, not a data-model migration.
- **SKOS field naming** (`prefLabel` / `altLabel` / `broader`) is the W3C
  standard vocabulary shape and round-trips trivially to RDF / Turtle if
  we ever need to expose our vocabularies as linked data.

## What we don't adopt

- **Schema.org Legal** — `Legislation`, `LegislationObject`, `Court`,
  `CourtDecision` are too thin for our per-country authority and
  subdivision granularity.
- **Full Akoma Ntoso XML** — heavy format; overkill for serving
  projections. We take the class vocabulary only.
- **CELEX as primary identifier** — CELEX stays as EU-specific metadata
  (carried on EUR-Lex documents); ELI is the canonical URI across all
  European jurisdictions including the EU itself.
- **Proprietary legal-citation formats** (Bluebook, OSCOLA, various
  national styles) — not suited to machine round-tripping. We extract
  them in text with the citation extractor; canonical identity stays
  on ELI / ECLI.

## Single-source-of-truth rule

Every concept above has exactly one Evidara file that owns it.
Downstream consumers (legal-search frontend icons, admin UI filters,
Fedlex cantonal SPARQL filter, RIS per-state applikation selector,
projection mappers) MUST read from that file. They MUST NOT re-encode
the mapping locally.

Concretely, for sub-federal identity:

- ISO 3166-2 code `CH-ZH` is the canonical identifier.
- `subdivisions.json` maps it to `slug=zh`, `iconKey=ch-zh`,
  `hierarchyTier=canton`, `hierarchyPath=ch/canton/zh`, and the provider
  tokens `fedlex_sparql_canton=ZH`.
- `legal-search/frontend/src/lib/icons.ts`, provider adapters, and any
  future admin filter MUST derive their value from this registry.

The two-key live-ready lock (blueprint `enabled: true` AND
`provider.live_ready: true`) enforces the same principle on the runtime
side: a scaffold provider cannot fire by accident.

## Tests that enforce this

- [`scripts/check_country_overlay_files.py`](../../scripts/check_country_overlay_files.py)
  cross-checks each country overlay against `language.json`,
  `source-family.json`, `court-level.json`, the jurisdiction vocab and
  the platform-control seeds. Run with `--country <ISO>`.
- [`scripts/tests/test_check_country_overlay_files.py`](../../scripts/tests/test_check_country_overlay_files.py)
  asserts all 6 shipped overlays pass the validator and that the
  validator catches the drift classes it claims to catch.
- [`platform-control/tests/unit/test_blueprint_provider_parity.py`](../../platform-control/tests/unit/test_blueprint_provider_parity.py)
  asserts every `provider:` string in `source_blueprints.yaml` is an
  `AcquisitionProvider` enum member, and the four core live providers
  retain at least one template.
- [`scripts/validate_json_schemas.py`](../../scripts/validate_json_schemas.py)
  exercises each JSON Schema against its corresponding example document.

## Deferred

- Migration of existing overlay `court_level_overlay.expected_levels`
  and `source_family_overlay.canonical` entries to reference the token
  IDs introduced here (still tolerated today because the validator is
  additive; a follow-up commit tightens the overlays).
- `country-overlays/_shared/operator-content.yaml` for the
  cross-country operator copy that is currently duplicated per country.
- Authority deduplication (`seeds/reference/authorities.yaml` vs each
  overlay's `reference-data.yaml`).
- `icons.ts` generation from `subdivisions.json` at build time.
- EuroVoc integration.
