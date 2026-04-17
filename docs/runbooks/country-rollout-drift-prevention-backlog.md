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

### 1.1 Authorities deduplication

**Problem:** Authority rows live in two places today —
`platform-control/seeds/reference/authorities.yaml` (19 rows across
all countries) and each `country-overlays/<iso>/reference-data.yaml`
(same rows duplicated per country). Drift is guaranteed.

**Target:** Seeds become the single source of truth. Overlay
`reference-data.yaml` references authority IDs instead of re-embedding
rows.

**Steps:**
1. Update `contracts/schemas/country-overlay.schema.json`:
   `reference-data.yaml` gains an optional `authority_ids` list (string
   array matching `^auth_[a-z0-9_]+$`). Existing `authorities[]` remains
   valid until all overlays migrate.
2. `scripts/check_country_overlay_files.py` cross-check: if
   `authority_ids` present, each ID MUST exist in
   `seeds/reference/authorities.yaml` with matching `jurisdiction_id`.
3. Migrate CH/AT/DE/FR/IT/EU `reference-data.yaml` to use
   `authority_ids` shape; delete the embedded `authorities[]` rows.
4. Add per-country `required_authority_ids` to `check_country_overlay_files.py`
   (already exists); verify it still passes post-migration.
5. Remove now-dead code paths in anything that reads authority rows from
   overlay files.

**Files:** `contracts/schemas/country-overlay.schema.json`,
`scripts/check_country_overlay_files.py`, all six
`country-overlays/*/reference-data.yaml`.

**Estimated size:** ~200 LOC net (mostly removal).

### 1.2 Shared operator copy

**Problem:** `triage_overlays` and `detail_copy.translation_indicator`
wording is copy-pasted across six `operator-content.yaml` and six
`user-content.yaml` files. Any tweak requires touching six files.

**Target:** `country-overlays/_shared/operator-content.yaml` and
`_shared/user-content.yaml` own the default strings; per-country files
override only the values that truly differ (language choice, country
name in helper text).

**Steps:**
1. Ship `country-overlays/_shared/` directory with default
   `operator-content.yaml` and `user-content.yaml`.
2. Add a deep-merge loader in `platform-control/src/platform_control/overlays/`
   (new subpackage) that loads shared + per-country and returns the
   merged payload. Country values win.
3. Thin the six per-country files to country-specific overrides only.
4. Update `check_country_overlay_files.py` to validate the merged
   payload, not the raw file.
5. Document the merge order in
   `docs/architecture/vocabulary-standards.md` §"Single-source-of-truth
   rule".

**Files:** `country-overlays/_shared/*`,
`platform-control/src/platform_control/overlays/loader.py` (new),
six per-country `operator-content.yaml` + `user-content.yaml`,
`scripts/check_country_overlay_files.py`.

**Estimated size:** ~400 LOC (loader + migration).

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

### 1.5 Tier-name canonicalization decision

**Problem:** `hierarchyTier` in `subdivisions.json` currently uses local
words: `canton` / `state` / `land` / `region` / `region`. Any UI,
filter, or analytics surface that shows the tier word has to decide
per-country.

**Target options (pick one):**
- **(A) One canonical word.** Rename all tiers to `subdivision`; keep
  the label in `prefLabel` per language (e.g.
  `prefLabel.de: "Kanton"`, `prefLabel.de: "Bundesland"`).
- **(B) Embrace local words.** Keep today's values but publish a
  display-label map: `subdivisions.json` entry gains
  `tierLabel: { de: "Kanton", en: "canton", … }`.

**Recommendation:** (A) with `prefLabel` carrying the local label. One
canonical tier word in code paths, localized labels in UI.

**Files (if (A)):** `contracts/vocabularies/subdivisions.json`
(global rename), downstream references.

**Estimated size:** ~200 LOC token churn, no behavior change.

### 1.6 Per-country authority-seed expansion

**Problem:** Today's seeds have thin DE (2 rows) and FR (2 rows)
coverage. Overlays reference only what exists.

**Target:** Flesh out DE/FR/IT authorities to match CH/AT thoroughness
— at least constitutional, supreme, appellate, and one administrative
authority per country, plus the federal publication authority.

**Files:** `platform-control/seeds/reference/authorities.yaml`.
**Estimated size:** ~40 rows added.

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

### 4.1 EurLexSparqlProvider live adapter

Ticket: `docs/runbooks/eu-eur-lex-fast-loop-backlog.md`.

- Implement `_resolve_concrete_work_uri`, `_query_expression_uris`,
  `_select_expression_uris`, `_describe_graph`, `_query_title`,
  `_fetch_text_manifestation` mirroring Fedlex.
- Smoke anchor: CELEX `32016R0679` (GDPR), ELI
  `http://data.europa.eu/eli/reg/2016/679/oj`.
- Flip `live_ready = True` on the class.
- Enable `eur_lex_sparql_regulation_en` template.
- Capture evidence at
  `docs/runbooks/evidence/<date>-eu-eurlex-smoke-run1.md`.

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

### 4.4 Fedlex cantonal SPARQL filter — activate the hook

`FedlexSparqlProvider._canton_filter()` extracts the code today but
does not apply it to the SPARQL query. To enable: add a
`jolux:CantonOfOrigin` filter on `_EXPRESSION_QUERY` and
`_MEMBER_QUERY`, parameterized on the normalized code. Ship with an
acceptance run against a known cantonal concordat to verify.

## Tier 5 — Feature additions

Larger feature work that unlocks new surfaces once Tier 1–4 are stable.

### 5.1 ELI URI emission on canonical documents

`contracts/schemas/document.schema.json` gains optional
`metadata.eli_uri` (string, URI format). Providers that navigate ELI
(`fedlex_sparql`, `eur_lex_sparql`, future Légifrance) populate it.
Downstream projection carries it so external systems can round-trip
against canonical Evidara output.

### 5.2 Sub-federal UI filters

`legal-search/frontend` gains a `Jurisdiction` filter that accepts
both country codes (`CH`) and subdivision codes (`CH-ZH`). The admin
source-setup UI gains a subdivision picker when the selected overlay
has a non-empty `subdivisions` ancestor in `hierarchy_paths`.

Depends on Tier 2.3 (sub-federal query model).

### 5.3 Citation extractor coverage for DE / FR / IT

Today the extractor is heavy on CH (SR, BGE, article patterns) and EU
(CELEX, ECLI:EU, regulation/directive). Add:
- DE: BVerfGE, BGHSt, BGHZ, §-patterns, BGB / StGB abbreviations
- FR: Code civil / Code pénal articles, jurisprudence numbering
  (pourvoi references, Dalloz notation)
- IT: Codice civile articoli, sentenze Cassazione numbering

Each country adds ~50 LOC of regex + aliases and a new test class,
following the existing shape.

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

### 5.5 `icons.ts` generation

Tier 1.3's follow-up: move from parity test to code-generation.

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
