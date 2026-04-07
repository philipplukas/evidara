# Multi-Country End-User Content Spec (CH, AT, DE, FR, IT)

## Purpose

Specify user-facing content behavior for scaling legal-search across five countries while keeping interaction patterns and label semantics stable.

## Surface mapping

| Surface | Content responsibilities | Must remain stable |
|---|---|---|
| Header search | placeholder, guidance microcopy | anchor intent and query confidence |
| ContextBar | jurisdiction/language/source-type labels | canonical term meanings |
| FilterPanel | facet labels, option labels, helper text | refinement semantics |
| Result cards | subtitle/context line, badges | cross-country comparability |
| Detail panel | tab labels, translation indicator text | detail-navigation predictability |
| Empty/error states | no-results guidance and recovery text | user recovery path quality |

## Canonical label set

### Top-level filter labels

| Canonical key | Primary label | Helper text intent |
|---|---|---|
| `jurisdiction` | Jurisdiction | legal system scope (country/canton/state where applicable) |
| `language` | Language | source language of document text |
| `source_family` | Source type | law, decision, commentary, administrative guidance |
| `official_only` | Official sources only | limit to authoritative/publicly official materials |
| `court_level` | Court level | hierarchy of deciding court |
| `effective_date` | Effective date | legal validity/publication recency |

### Source-type display policy

Use one global primary set in UI:

- `All`
- `Laws`
- `Decisions`
- `Commentary`

Country-specific local names may appear in helper text/tooltips only, never as the primary tab label.

## Country overlays (user-facing)

| Country | Overlay rule | Allowed localized helper additions |
|---|---|---|
| CH | clarify federal/canton split under jurisdiction | federal/canton examples |
| AT | emphasize national statutory corpus in source-type helper | Austrian court examples |
| DE | clarify federal/Länder scope in jurisdiction helper | Länder examples |
| FR | clarify judicial vs administrative decision families | Conseil d'Etat / Cassation examples |
| IT | clarify regional context where metadata includes locality | cassation/tribunal examples |

## Result-card content rules

### Subtitle template

Canonical structure:

`<jurisdiction_label> • <source_family_label> • <court_or_authority_label?> • <effective_date?>`

Rules:

- Keep order fixed across all countries.
- Omit missing fields; do not reorder remaining fields.
- Never substitute canonical source-family labels per country.

### Badge policy

| Badge | Display condition | Text rule |
|---|---|---|
| Official | `official_only` true or source flagged official | always use `Official` semantic, locale-translated |
| Translation | content language differs from UI locale | explicit machine-translation wording if applicable |
| Language | when non-default locale for active jurisdiction | show ISO-like concise code + localized language name |

## Detail panel content rules

### Tab naming

Primary tab semantics remain fixed:

- `Details`
- `Related`
- `References`
- `Annotation`
- `Structure`

Country overlays can only adjust explanatory text inside tabs, not tab names.

### Translation indicator copy

Required states:

- `Original language` (when UI locale matches source language)
- `Machine translated from <language>` (when translation applied)
- `Translation unavailable` (when requested locale not available)

## Empty/error-state copy matrix

| Scenario | Primary copy goal | Required recovery action |
|---|---|---|
| No results after filters | explain restrictive filters | CTA to clear filters |
| No results for jurisdiction | suggest adjacent jurisdictions/languages | CTA to broaden jurisdiction scope |
| Unsupported language combination | clarify language coverage limits | CTA to switch UI locale or remove language filter |
| Temporary search failure | preserve trust with explicit retry guidance | CTA to retry and operator-contact fallback |

## UX acceptance criteria

- A user can switch among CH/AT/DE/FR/IT without relearning primary filter labels.
- Result subtitle grammar stays consistent for all five countries.
- Users can always identify whether content is official and/or translated.
- Empty states provide one clear recovery path within one interaction.
