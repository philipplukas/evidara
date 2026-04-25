# Five-Country Content Rollout (CH, AT, DE, FR, IT)

## Purpose

Define one shared content model for legal-search users and platform-control operators that scales across Switzerland, Austria, Germany, France, and Italy without country-specific drift.

## Current state

This document is the **authoritative product and operator content model** for the five-country rollout. Shared taxonomy dimensions and overlay principles are agreed; phased implementation follows [Rollout sequencing and quality gates](#rollout-sequencing-and-quality-gates) below. Legal-search filters, copy, and platform-control onboarding text should converge on the canonical keys described here before expanding country-specific UI.

## Source of truth

| Layer | Source of truth |
|-------|-----------------|
| Canonical keys (`jurisdiction`, `source_family`, `court_level`, etc.) | `contracts/` (schemas, vocabularies, OpenAPI) — changes require contract review |
| Country overlay defaults and templates | Versioned overlay packages / YAML treated as policy (not mutated by crawls at runtime) |
| Operator procedures | `docs/runbooks/platform-control-multi-country-operator-playbook.md` and related runbooks |
| End-user copy and facet labels | `legal-search/` (must map to canonical keys; no ad hoc per-country keys) |

## Minimal next tasks

- [ ] Complete Phase 1 (CH + AT): reference content pack, stable labels, executable operator checklist (see gates below).
- [ ] Add DE + FR overlays (Phase 2) without changing canonical keys unless contracts change.
- [ ] Add IT overlay and run five-country terminology diff (Phase 3).
- [ ] Track progress with [Five-country acceptance checklist](#five-country-acceptance-checklist).

## Later expansion

| Phase | Focus |
|-------|--------|
| After Phase 3 | Shared glossary published across user and operator docs; automated diff between overlay YAML and UI strings |
| Future | Additional countries reusing the same canonical layer; optional locale-specific display names behind stable keys |

## Dependencies

| Dependency | Role |
|------------|------|
| Contracts / vocabularies | Stable keys for jurisdictions, source families, and facets |
| Legal-search frontend | Surfaces labels and filters bound to canonical keys |
| Platform-control | Source onboarding, approvals, and run segmentation aligned to the model |
| Document intelligence / corpus metadata | Language and document-type signals feeding trust and translation UX |

## Testing

- **Contract tests** — any new canonical key or vocabulary value must ship with schema/OpenAPI updates and validation in CI.
- **UX / copy review** — Phase gates require no unresolved label conflicts between active country pairs (e.g. CH vs AT for Phase 1).
- **Operator drills** — Runbook checklist executed end-to-end per phase gate before expanding to the next country set.

## Drift risks

| Risk | Mitigation |
|------|------------|
| Country-specific aliases without canonical mapping | Overlay write policy: discovery emits candidates only; humans approve mapping changes |
| Divergent UI labels for the same key | Single glossary; legal-search uses canonical keys internally |
| Runtime mutation of overlay config | Acquisition runs must not edit overlay files; use reviewed config changes only |
| Contract key drift from marketing or legal wording | Changes flow through contracts first, then UI and runbooks |

## Problem statement

The product already supports multi-jurisdiction filtering and operator run flows, but content semantics are not yet explicitly normalized for:

- cross-country legal source families,
- court hierarchy naming differences,
- language defaults and translation expectations,
- operator triage patterns when jurisdiction mapping fails.

Without a shared model, each country rollout risks introducing inconsistent terms in filters, result context, and runbook procedures.

## Scope

- End-user content model for legal-search surfaces (filters, result metadata, detail labels, guidance text).
- Operator content model for platform-control flows (onboarding, approval, run execution, incident triage).
- CH, AT, DE, FR, IT overlays on top of a single shared taxonomy.

## Shared taxonomy (canonical layer)

### Dimension model

| Dimension | Canonical key | End-user usage | Operator usage |
|---|---|---|---|
| Jurisdiction | `jurisdiction` | filter chips and result metadata | source scope and run segmentation |
| Source family | `source_family` | source-type tabs and facet labels | source onboarding template selection |
| Authority type | `authority_type` | secondary detail context | approval checks and mapping QA |
| Court level | `court_level` | refinement facet and subtitles | parser/mapping validation |
| Language | `language` | language chips and translation badge | expected corpus language coverage |
| Official status | `official_only` | trust/official toggle | source reliability guardrail |
| Temporal validity | `effective_date` | recency filters and timeline context | version freshness checks |

### Source family normalization

| Canonical source family | User-facing meaning | Typical artifacts |
|---|---|---|
| `law` | statutory/legal code text | federal/national laws, ordinances, regional statutes |
| `decision` | court decisions and judgments | supreme and lower-court case law |
| `commentary` | explanatory secondary materials | doctrine/commentary notes and analysis |
| `administrative_guidance` | regulator/ministry interpretive guidance | circulars, guidance notes |

## Country overlays

| Country | Primary legal structure pattern | Key court hierarchy pattern | Primary languages | Content risk to guard |
|---|---|---|---|---|
| CH | federal + canton coexistence | federal supreme + cantonal courts | de, fr, it | canton naming inconsistency in filters |
| AT | federal statutes with strong national layers | supreme + appellate + regional | de | decision vs commentary boundary blur |
| DE | federal + Länder legal surfaces | federal constitutional/supreme + Länder courts | de | state-level labels diverging from canonical keys |
| FR | centralized codes + administrative tracks | cassation + administrative courts | fr | legal family naming drift in translated UI |
| IT | national codes with region-sensitive practice | cassation + appellate + tribunal | it | inconsistent metadata quality across decisions |

## Sub-federal hierarchy paths

Country overlays MUST encode sub-federal jurisdiction in `hierarchy_paths`
using ISO 3166-2 subdivision codes lowercased. The canonical path shape is:

`<iso-3166-1-alpha-2-lowercased>/<subdivision-tier>/<iso-3166-2-subdivision-lowercased>`

| Country | Sub-federal tier | Path pattern | Example |
|---|---|---|---|
| CH | canton | `ch/canton/<code>` | `ch/canton/zh` (Zürich) |
| AT | state (Bundesland) | `at/state/<code>` | `at/state/w` (Wien) |
| DE | Land | `de/land/<code>` | `de/land/by` (Bayern) |
| FR | région | `fr/region/<code>` | `fr/region/idf` (Île-de-France) |
| IT | regione | `it/region/<code>` | `it/region/25` (Lombardia) |

For EU the analogous nesting is member-state, not a subdivision of a single
country: `eu/member-state/<iso-3166-1-alpha-2-lowercased>` (e.g.
`eu/member-state/de`). National sub-federal paths stay under their own
country overlay regardless of EU membership.

Additive rule: a country overlay's `hierarchy_paths` MUST include
`<country>`, SHOULD include `<country>/federal`, and MAY include the
`<country>/<sub-federal-tier>` umbrella. Concrete sub-federal subdivision
paths live on the individual provider templates and are emitted at
discovery time, not pinned at overlay level.

### CH municipality coverage (hero / demo path)

CH is the hero demo path and ships **full municipality coverage** as
first-class jurisdictions. All ~2,110 active Swiss municipalities from
the BFS Amtliches Gemeindeverzeichnis are promoted into
`platform-control/src/platform_control/seeds/reference/jurisdictions.yaml`
under the `jur_ch_gemeinde_<bfs_number>` ID convention, each parented to
its canton row (e.g. `jur_ch_gemeinde_261` → `parent_id: jur_ch_zh`).

Regenerate after a BFS overlay refresh:

```
python scripts/generate_ch_municipality_jurisdictions.py
```

The script is idempotent and validates that every generated row's
`parent_id` resolves against an existing canton row before writing. Other
countries (AT/DE/FR/IT/EU) currently model only country + sub-federal
tier; municipality-level rollout is deferred until those overlays
mature. See issue #424.

## End-user content principles

1. Show canonical concepts first, local naming second.
2. Keep one meaning per label across countries.
3. Use helper text for legal-structure differences instead of changing primary labels.
4. Prefer explicit translation indicators when content language differs from UI language.

## Operator content principles

1. One runbook flow with country overlays, not separate country playbooks.
2. Approval checklists must include jurisdiction mapping and court-level normalization.
3. Incident triage must distinguish content-model errors from upstream acquisition errors.
4. Country overlays should be additive only (no custom state-machine per country).

## Overlay write policy

Overlay configuration is policy, not runtime state. Treat country overlay YAML files as versioned, human-reviewed configuration.

1. Acquisition/discovery runs must not modify overlay files directly.
2. Discovery can emit candidate mappings or patch suggestions only.
3. Overlay updates require operator review and explicit approval.
4. Every accepted overlay change should preserve canonical keys and include a brief rationale.

## Dependency and ownership map

| Area | Primary owner | Secondary owner | Update trigger |
|---|---|---|---|
| User-facing taxonomy labels | legal-search | contracts | changed filter semantics |
| Jurisdiction/source-family keys | contracts | legal-search, platform-control | new country/source family added |
| Operator onboarding/triage wording | platform-control | docs | new provider or run failure mode |
| Translation and language indicators | legal-search | document-intelligence | new language or translation policy |
| Shared vocabularies (subdivisions, source-family, court-level, language) | contracts | platform-control, legal-search | new country, new provider token, new court level |
| Country-overlay schema + validator | contracts | platform-control | schema tightening / new required field |

## Vocabulary standards

Evidara anchors on ISO 3166-1/3166-2, ELI, ECLI, FRBR, Akoma Ntoso
document classes, EuroVoc (deferred), and SKOS serialization field
names. Full rationale and single-source-of-truth rules are in
[`docs/architecture/vocabulary-standards.md`](../architecture/vocabulary-standards.md).

Overlay drift is caught by
[`scripts/check_country_overlay_files.py --country <ISO>`](../../scripts/check_country_overlay_files.py),
which cross-checks every overlay against the shared vocabularies and
platform-control seeds.

## Rollout sequencing and quality gates

### Phase 1 (CH + AT baseline hardening)

- Build reference content pack for CH and AT with shared taxonomy keys.
- Validate that filter labels, helper copy, and operator checklist terms are stable.

Gate:

- zero unresolved label conflicts between CH and AT overlays,
- operator onboarding checklist executable end-to-end for both countries.

### Phase 2 (DE + FR expansion)

- Add DE and FR overlays with no canonical key changes unless contract-reviewed.
- Validate legal family naming and court-level mapping clarity in UI and runbooks.

Gate:

- no country-specific alias added without canonical mapping,
- translation/locale guidance complete for FR surfaces.

### Phase 3 (IT integration + five-country consistency pass)

- Add IT overlay and run cross-country terminology diff.
- Resolve wording divergence and finalize country matrix.

Gate:

- one shared glossary used in user and operator docs,
- five-country acceptance checklist complete.

## Five-country acceptance checklist

- [ ] All five countries mapped to canonical taxonomy dimensions.
- [ ] End-user filters use consistent primary labels across countries.
- [ ] Result/detail context strings follow shared subtitle rules.
- [ ] Operator onboarding checklist has country overlays for all five countries.
- [ ] Triage playbook has country-specific mapping checks and fallback actions.
- [ ] No contract key drift introduced by country overlays.
