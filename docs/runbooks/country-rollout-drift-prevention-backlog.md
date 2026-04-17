# Country rollout & drift-prevention backlog

Owner: Contracts / Platform
Last reviewed: 2026-04-16
Status: Active — updated after commit `2a02573` on `claude/plan-next-steps-OANlO`
Applies to: everything still needed to ship five-country + EU coverage without
accumulating drift

## Purpose

Consolidate every open thread from the five-country + EU rollout and the
drift-prevention track into one prioritized backlog. Three recent commits
on branch `claude/plan-next-steps-OANlO` (PR #241) have landed:

1. Design-tokens unification across legal-search + admin
2. CH / IT / DE / FR / EU overlays + sub-federal scaffolding + EUR-Lex /
   Bundesland / Regione provider stubs
3. Shared vocabularies (subdivisions, source-family, court-level,
   language) + country-overlay meta-schema + generalized validator +
   two-key live-ready lock + ELI/ECLI/FRBR anchor doc

This backlog captures what's still needed, grouped by class of work so
owners can pick lanes without stepping on each other.

## Tier 1 — Code-only drift prevention (near-term, low-risk)

Work that reduces duplication, hardens invariants, and finishes the
rollout-platform seam. All additive, none blocks on live acquisition
runs or operator work.

### 1.1 Authorities deduplication ✅ LANDED

**Problem:** Authority rows lived in two places — `platform-control/seeds/reference/authorities.yaml` and each `country-overlays/<iso>/reference-data.yaml`. Drift was guaranteed.

**Outcome:** Seeds are now the single source of truth. Each overlay
`reference-data.yaml` carries only `jurisdiction_id` (single string)
and `authority_ids` (string list). The validator cross-checks every ID
against the seed index and fails on unknown authority IDs or
jurisdiction mismatches. Schema enforces the new shape; embedded
`authorities[]` arrays in overlays are no longer valid. 2 new negative
tests cover unknown-authority and jurisdiction-mismatch drift classes.

**Landed in:** commit following `1220c66`, same branch.

### 1.2 Shared operator copy ✅ LANDED

**Outcome:** `country-overlays/_shared/` now owns the default
`result_subtitle_pattern`, the `triage_overlays` block, and the
"authority taxonomy correctness" approval hotspot.
`platform_control.overlays.loader` deep-merges per-country overrides
on top and substitutes `{country_code}`. 17 unit tests cover merge and
substitution behavior. The file-level schema relaxes to reflect that
the shared default supplies certain fields; a new merged-view invariant
check in `scripts/check_country_overlay_files.py` enforces that both
`result_subtitle_pattern` and `triage_overlays` still appear in the
merged payload even if the per-country file omits them. All 6 country
overlays pass post-migration.

**Landed in:** commit following `9549fba`, same branch.

### 1.3 `icons.ts` ↔ `subdivisions.json` parity test

**Problem:** `legal-search/frontend/src/lib/icons.ts` duplicates the
`iconKey` field from `subdivisions.json`. Adding a new subdivision in
the vocabulary but forgetting the icon entry (or vice-versa) ships
silently.

**Target (this PR):** vitest parity test that reads both files and
asserts every `iconKey` in `subdivisions.json` has an entry in
`icons.ts`.

**Target (follow-up):** `icons.ts` is generated from `subdivisions.json`
at frontend build-time via a small `scripts/generate-icons.ts`, and
`prebuild`/`predev` runs it. Hand-maintenance is removed.

**Files (this PR):**
`legal-search/frontend/src/__tests__/icons-subdivisions-parity.test.ts`.
**Files (follow-up):** `legal-search/frontend/scripts/generate-icons.ts`,
`package.json` scripts.

**Estimated size:** ~40 LOC test (this PR); ~80 LOC generator
(follow-up).

### 1.4 Merge `at:` + `at_subfederal:` in `source_blueprints.yaml`

**Problem:** The blueprint YAML currently has two sections for AT
(federal + sub-federal). Every consumer must join them back to iterate
AT's templates.

**Target:** one `at:` section with all templates; sub-federal templates
either co-exist or move under a sub-key like `at.subfederal_templates`.
Apply the same rule to any future country that gains sub-federal
templates.

**Files:** `platform-control/src/platform_control/hierarchies/source_blueprints.yaml`,
one blueprint consumer in `platform-control/src/platform_control/services/`
if any currently iterates by overlay name.

**Estimated size:** ~50 LOC moved.

### 1.5 Tier-name canonicalization decision ✅ LANDED

**Outcome:** Pragmatic hybrid of options A and B. Each country in
`contracts/vocabularies/jurisdiction.json` gains a `subdivisionTier`
block with a canonical `slug` (matches `subdivisions.json` `hierarchyTier`)
and a `prefLabel` with per-language display labels. Code paths use the
slug (`canton` / `state` / `land` / `region`); UI surfaces the
localized label (`Kanton`, `Bundesland`, `Land`, `région`, `regione`).
The `hierarchyPath` wire format stays the same so no URLs break.

**Landed in:** commit following `6b726a9`, same branch.

### 1.6 Per-country authority-seed expansion ✅ LANDED

**Outcome:** `platform-control/seeds/reference/authorities.yaml` grew
from 19 to 30 rows. DE: 2 → 7 (added BGH, BVerwG, BFH, BAG, BSG). FR: 2
→ 4 (added Conseil d'État, Conseil constitutionnel). IT: 4 → 5 (added
Corte Costituzionale). Per-country `REQUIRED_AUTHORITIES` minimums in
the validator tightened accordingly. DE/FR/IT overlays now cite these
richer sets.

**Landed in:** commit following `1220c66`, same branch.

## Tier 2 — Design decisions pending

Decisions the team should make before committing a lot of code along
one path.

### 2.1 Multi-tenant provider vs per-portal providers

Today's `BundeslandHttpProvider` and `RegioneHttpProvider` are
multi-tenant: one class, inline dict of supported state→URL mappings.
This keeps imports tidy but every new Land becomes a dict entry PLUS a
custom adapter, and the adapters will diverge (different HTML, different
authentication, different pagination).

**Options:**
- **Multi-tenant (status quo)** — one class per country, state-switched
  at runtime. Pro: one import. Con: class becomes a pile of
  conditionals.
- **Per-portal provider** — one class per state. Pro: clean
  isolation. Con: 16 DE + 20 IT + up to 13 FR providers.
- **Declarative per-state config** — one generic scraper driven by
  per-state URL templates + CSS selectors. Pro: zero code per state.
  Con: real-world portals often need adapter-level logic that doesn't
  fit declarative config.

**Recommendation:** pick per-portal, but share a `BasePortalHttpProvider`
that owns the generic shape (pagination, HTML normalization). Decide
before the second live state adapter lands.

### 2.2 Overlay + seed merge policy

Closely related to Tier 1.1 and 1.2. Spec is:
- **Seeds** — authoritative for reference data (jurisdictions,
  authorities). Overlays reference IDs.
- **Shared overlays** — authoritative for default operator / user copy.
  Per-country overlays override.
- **Per-country overlays** — authoritative for country-specific
  structural overlays (hierarchy paths, language defaults, court
  levels).

Document this in `docs/architecture/vocabulary-standards.md` once 1.1
and 1.2 land.

### 2.3 Sub-federal query model

When a user searches "Mietrecht, Bayern only", the query path needs to
know:
- Filter projection by `subdivision = DE-BY`
- Route discovery to `bundesland_http` with `bundesland=DE-BY`
- Label the result with `hierarchyPath=de/land/by`

**Decision to make:** where does the `subdivision` filter live in the
BFF contract (`contracts/api/legal-search.openapi.yaml`)? Options:
- Top-level `jurisdiction` param accepts `DE-BY` as well as `DE` (ISO
  3166 mixed granularity)
- Separate `subdivision` param

**Recommendation:** top-level `jurisdiction` accepts both forms; BFF
normalizes. Fewer params, matches ISO 3166 intent.

## Tier 3 — Content / operator work (external, non-code)

Work that ships only by running acceptance flows against dev environments
and recording evidence. Tracked on GA operator board under TAR-239 /
TAR-240.

### 3.1 DE acceptance run evidence

- Run `deterministic_http_bundesrecht` against dev
- Capture evidence under `docs/runbooks/evidence/<date>-de-bundesrecht-*.md`
- Confirm canonical keys, filter labels, subtitles follow shared rules
- Verify DE authority taxonomy surfaces correctly

### 3.2 FR acceptance run evidence

- Same pattern against `deterministic_http_legifrance_codes`
- Watch for translated-UI naming drift (a known FR risk in
  `five-country-content-rollout.md`)

### 3.3 IT acceptance run evidence

- Run `deterministic_http_normattiva_legislation` against dev
- Confirm Cassazione / Consiglio di Stato / constitutional distinctions
  map cleanly
- Capture per-regione metadata quality baseline

### 3.4 CH + AT widened-discovery evidence

- AT: `scripts/at-ris-fast-loop.sh --widen-discovery` (now supported)
- CH: Fedlex batch run across federal laws
- Update `docs/runbooks/five-country-acceptance-a.md`

## Tier 4 — Live-adapter enablement

Each scaffold provider needs its live adapter. All three are independent
and can run in parallel.

### 4.1 EurLexSparqlProvider live adapter 🟡 CODE LANDED; ACCEPTANCE RUN PENDING

**Code landed:**
- `platform_control/services/eur_lex_sparql_provider.py` implements
  the full CDM work → expression → manifestation flow (mirrors Fedlex
  structure): `_query_expressions`, `_select_expressions` (ranked by
  preferred language), `_pick_html_manifestation` (HTML > XHTML,
  skips PDF), `_query_title`, `_fetch_text_manifestation`.
- ISO 639-1 → EUR-Lex 3-letter authority-list language IRI
  translation for 24 EU languages.
- ELI URI validation (host + path prefix).
- `ProviderResource.metadata` round-trips `eli_uri`, `celex`,
  `expression_uri`, `language_iri`, `language` for T5.1 downstream
  wiring.
- `live_ready = True`; two-key lock now accepts blueprint templates
  that reference `eur_lex_sparql`.
- 14 unit tests: GDPR end-to-end, language ranking, ISO/authority
  mapping, ELI validation, seed input modes.

**Still needed:**
- First acceptance run against `http://publications.europa.eu/webapi/rdf/sparql`
  with CELEX `32016R0679` (GDPR), seed URI
  `http://data.europa.eu/eli/reg/2016/679/oj`. Needs GCP auth + dev.
- Flip `enabled: true` on `eur_lex_sparql_regulation_en` once
  evidence captures `content_type=text/html`, ≥1 raw artifact, and
  lifecycle event `document.processed`.
- Evidence under `docs/runbooks/evidence/<date>-eu-eurlex-smoke-run1.md`.

### 4.2 BundeslandHttpProvider Bayern adapter

- Portal: `gesetze-bayern.de`
- First target: a known statute (e.g. BayVwVfG) reachable by stable URL
- Flip `live_ready = True` on the class
- Enable `bundesland_http_bayern` template
- Runbook: create `docs/runbooks/de-by-bundesland-fast-loop.md`

### 4.3 RegioneHttpProvider Lombardia adapter

- Portal: `normelombardia.consiglio.regione.lombardia.it`
- First target: a known legge regionale
- Flip `live_ready = True` on the class
- Enable `regione_http_lombardia` template
- Runbook: create `docs/runbooks/it-lombardia-regione-fast-loop.md`

### 4.4 Fedlex cantonal SPARQL filter — partially landed

**Landed (scaffolding):**
- `_canton_filter(acquisition_spec)` normalizes ISO 3166-2:CH codes.
- `_canton_iri(code)` maps to the Fedlex canton vocabulary IRI
  (`https://fedlex.data.admin.ch/vocabulary/canton/ZH`).
- `_build_canton_discovery_query(code, limit)` renders the
  `jolux:CantonOfOrigin` discovery SPARQL.
- `_discover_works_by_canton(...)` async method executes the query and
  returns work URIs; not yet wired into `start_run()`.
- 5 unit tests cover the mapping, query shape, default limit, and
  rejection of garbage codes.

**Still needed:**
- Wire `_discover_works_by_canton` into a new
  `acquisition_spec.scope_kind = "canton"` mode in `start_run()`.
- Run a live acceptance test against a known cantonal concordat
  (proposal: a Valais inter-cantonal concordat as first target).
- Flip the scope mode live-ready + land evidence under
  `docs/runbooks/evidence/<date>-ch-fedlex-cantonal-*.md`.

## Tier 5 — Feature additions

Larger feature work that unlocks new surfaces once Tier 1–4 are stable.

### 5.1 ELI URI emission on canonical documents ✅ LANDED

**Outcome:** `contracts/schemas/document.schema.json` gains three
optional metadata fields: `eli_uri` (URI format), `celex` (EU CELEX
regex), and `subdivision` (ISO 3166-2 regex). Fedlex SPARQL provider
emits `eli_uri` on every captured resource via a new
`_eli_uri_for_work()` helper that prefers the abstract seed URI
(`https://fedlex.data.admin.ch/eli/cc/1999/404`) over the dated
concrete form — matching what external ELI consumers expect. 4 new
Fedlex tests assert the round-trip. Projection-layer wiring
(persisting `metadata.eli_uri` on canonical output) lands in a
follow-up alongside the live EUR-Lex adapter.

**Landed in:** commit following `bfe163e`, same branch.

### 5.2 Sub-federal UI filters 🟡 CONTRACT + PARSER LANDED; UI WIRING PENDING

**Landed (contract + parsers):**
- `contracts/api/legal-search.openapi.yaml` `jurisdiction` param now
  documents both country (`CH`) and subdivision (`CH-ZH`) shapes with
  regex validation and helper text.
- `legal-search/api/src/modules/search/dto/jurisdiction-token.ts`
  ships `parseJurisdictionToken` + `parseJurisdictionList`, returning
  `{country, subdivision?}`. Covered by 11 unit tests.
- `SearchQueryDto.getParsedJurisdictions()` returns parsed tokens for
  downstream consumers.
- `legal-search/frontend/src/lib/jurisdiction-filter.ts` mirrors the
  parser and exposes `subdivisionsForCountry(country, lang)` and
  `labelForSubdivisionToken(token, lang)` by reading the generated
  `SUBDIVISION_REGISTRY`. 9 frontend tests cover parsing, localized
  labels, and empty-list for subdivisionless countries.

**Still needed (UI surface):**
- Wire `subdivisionsForCountry()` into the filter panel component so
  users can toggle between country-wide and subdivision-scoped filters.
- Wire `getParsedJurisdictions()` into the OpenSearch adapter so
  subdivision-scoped queries hit the `subdivision` field (requires an
  index mapping change).
- Admin source-setup UI: add a subdivision picker when the selected
  overlay has a sub-federal hierarchy tier.

Design decision (T2.3 close-out): `jurisdiction` accepts mixed
granularity in a single param; the BFF normalizer splits country vs.
subdivision. No separate `subdivision` param. Rationale:
- Fewer params = smaller API surface.
- Matches ISO 3166 intent (subdivision codes encode the country).
- User input ("CH-ZH" or "CH") never has to think about routing.

### 5.3 Citation extractor coverage for DE / FR / IT ✅ LANDED

**Outcome:** `document-intelligence/src/document_intelligence/nlp/citation_extractor.py`
grew from CH + EU coverage to include:
- **DE:** BVerfGE volume+page citations, BVerfG docket numbers
  (1 BvR 1234/56 style), BGHZ/BGHSt, ECLI:DE:*, § paragraph references
  with a curated list of ~30 common German statute abbreviations
  (BGB, StGB, ZPO, GG, …).
- **FR:** Code articles (civil, pénal, commerce, procédure civile/pénale,
  travail, environnement, consommation, santé publique, assurances) with
  L./R./D. prefixes; pourvoi numbers; Cassation chamber prefixes;
  Conseil d'État dockets; ECLI:FR:*.
- **IT:** Codice civile / penale / procedura civile + penale articles;
  Cassazione judgments (civil + penal with sezione); Consiglio di
  Stato; ECLI:IT:*.
- 22 new test cases added (43 total citation tests pass).

**Landed in:** commit following `6b726a9`, same branch.

### 5.4 EuroVoc topic classification

SKOS thesaurus with 7k+ concepts. Integration shape:

1. Ship `contracts/vocabularies/topic.json` (bootstrap from a subset —
   Evidara-relevant branches only: tax, data protection, employment,
   financial services, etc.).
2. Document-intelligence gains a topic-classification step that
   outputs `metadata.topics: string[]` keyed on EuroVoc concept IDs.
3. Legal-search exposes topic faceting.

Non-trivial: classification model + evaluation. Scope as a full
workstream.

### 5.5 `icons.ts` generation ✅ LANDED

**Outcome:**
- `legal-search/frontend/scripts/generate-subdivision-icons.mjs`
  emits `src/lib/subdivisions.generated.ts` from
  `contracts/vocabularies/subdivisions.json`.
- The generated file exports `SUBDIVISION_REGISTRY`,
  `SUBDIVISIONS_BY_COUNTRY`, and `SUBDIVISION_ICONS` — one source of
  truth for every sub-federal data view the frontend needs.
- `icons.ts` now imports `SUBDIVISION_ICONS` and spreads it alongside
  the hand-maintained country + meta icons.
- All 89 subdivisions gained an `iconText` field in
  `subdivisions.json` as the canonical text-label source.
- `npm run generate:icons` regenerates on demand;
  `predev`/`prebuild`/`pretest`/`check` run it automatically. The
  generated file is gitignored (per the repo's `*.generated.*`
  pattern) and regenerated on every run — no committed copy to drift.
- Parity test asserts `iconText` from `subdivisions.json` round-trips
  through `getIcon()`.

**Landed in:** commit following `bfe163e`, same branch.

## Tier 6 — Platform chokepoints (serialized, on GA operator board)

These are tracked on `docs/runbooks/ga-operator-board.md`. Not in our
direct execution scope, but they gate end-to-end release readiness.

- **TAR-70** gate policy hardening — emitted-check vs required-check
  drift. One owner at a time (branch-protection change).
- **TAR-238** runner reliability — same pattern causing PR #241's fast-
  fail CI; re-runs succeed on fresh runners.
- **TAR-241** relevance baseline — `scripts/run-staging-relevance-query-pack.sh`
  against dev, record in `docs/runbooks/relevance-eval-result-template.md`.
- **TAR-214** release evidence refresh — re-verify TAR-77 + TAR-64 +
  TAR-85; mirror into phase-5 memo.

## Sequencing

```text
T1.1 authorities dedup ──┐
T1.2 shared copy ────────┼── structural refactor wave (one PR)
T1.4 blueprint merge ────┘
T1.3 icons parity test ──── (lands with T1.1)
T1.5 tier-name decision ──── (prerequisite for Tier 5.2)
T1.6 seed expansion ──── (unblocks Tier 3)

T2.1 provider pattern ──── (prerequisite for T4.2 + T4.3)
T2.3 sub-federal query ──── (prerequisite for T5.2)

T3.1-3.3 DE/FR/IT evidence ──── operator work, unblocks GA sign-off

T4.1 EurLex live ──── independent; ship once ready
T4.2 Bayern live ──── needs T2.1
T4.3 Lombardia live ──── needs T2.1
T4.4 Cantonal filter ──── independent

T5.1 ELI URI ──── needs T4.1 for end-to-end value
T5.2 sub-federal UI ──── needs T1.5 + T2.3
T5.3 citation coverage ──── fully parallel
T5.4 EuroVoc ──── standalone workstream
T5.5 icons gen ──── needs T1.3

T6.* chokepoints ──── GA operator board owns
```

## Ownership map

| Tier | Suggested primary owner |
|------|-------------------------|
| T1.* (code-only drift prevention) | contracts |
| T2.* (design decisions) | architecture + platform-control |
| T3.* (acceptance runs) | platform-control ops |
| T4.* (live adapters) | platform-control per country |
| T5.1 (ELI URI) | contracts + document-intelligence |
| T5.2 (sub-federal UI) | legal-search |
| T5.3 (citations) | document-intelligence |
| T5.4 (EuroVoc) | document-intelligence + legal-search |
| T5.5 (icons gen) | legal-search |
| T6.* (platform chokepoints) | GA operator board |

## Done means

This backlog retires when:

- Tier 1 items 1.1–1.5 are merged and no country overlay carries
  duplicate rows or free-form tier words.
- Tier 3 has evidence for each of DE / FR / IT.
- Tier 4 has at least one live adapter beyond Fedlex and RIS (most
  likely EurLex, since its value-per-hour is highest).
- Tier 5.1 (ELI URI) ships; projections carry it.
- `docs/architecture/vocabulary-standards.md` "Deferred" section is
  empty.

## Related

- [`docs/architecture/vocabulary-standards.md`](../architecture/vocabulary-standards.md)
- [`docs/components/five-country-content-rollout.md`](../components/five-country-content-rollout.md)
- [`docs/runbooks/ga-operator-board.md`](ga-operator-board.md)
- [`docs/runbooks/eu-eur-lex-fast-loop-backlog.md`](eu-eur-lex-fast-loop-backlog.md)
- [`docs/runbooks/ch-fedlex-fast-loop-backlog.md`](ch-fedlex-fast-loop-backlog.md)
