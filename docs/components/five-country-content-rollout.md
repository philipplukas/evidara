# Five-Country Content Rollout (CH, AT, DE, FR, IT)

## Purpose

Define one shared content model for legal-search users and platform-control operators that scales across Switzerland, Austria, Germany, France, and Italy without country-specific drift.

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
