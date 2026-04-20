# EU EUR-Lex Fast-Loop Backlog

Owner: Platform / GA
Last reviewed: 2026-04-16
Last verified: 2026-04-16 (scaffold only; no live run yet)
Status: Code ready — adapter implemented with mocked tests; live acceptance run still pending
Applies to: EU EUR-Lex provider iteration on `dev`

## Purpose

Stand up the EUR-Lex SPARQL acquisition loop using the same shape
already proven for CH Fedlex:

1. change `eur_lex_sparql`
2. validate locally
3. deploy only `platform-control-api-dev`
4. run one tiny EU preview against a known-good CELEX
5. auto-check acquisition + DI + lifecycle + basic content quality
6. decide `keep`, `fix`, or `widen`

This backlog is the execution companion to:

- [Five-Country Content Rollout](../components/five-country-content-rollout.md)
- [CH Fedlex Fast-Loop Backlog](ch-fedlex-fast-loop-backlog.md) (directly reused pattern)

## Current state

Code ready:

- `platform_control/services/eur_lex_sparql_provider.py` implements the
  full work → expression → manifestation flow against the CDM ontology.
  - `_query_expressions` enumerates expressions + languages + CELEX.
  - `_select_expressions` ranks by `preferred_languages`.
  - `_pick_html_manifestation` prefers HTML over XHTML; skips PDFs in
    this scaffold (document-intelligence handles binary formats).
  - `_query_title` captures the expression title.
  - `_fetch_text_manifestation` fetches from Cellar and applies
    `max_content_bytes` safety.
  - ELI URI + CELEX round-trip to `ProviderResource.metadata`.
- 14 unit tests cover the GDPR end-to-end flow, language ranking, ISO
  639-1 ↔ authority-list mapping, ELI-URI validation, and seed input
  modes. `live_ready = True`.
- `provider_registry_factory.py` registers it; the two-key lock now
  accepts blueprint templates that reference it.
- Blueprint templates `eur_lex_sparql_regulation_en` (GDPR) and
  `eur_lex_sparql_directive_en` (DSM Copyright Directive) are still
  `enabled: false` pending acceptance-run evidence.
- `contracts/vocabularies/jurisdiction.json` includes `EU`.
- `platform-control/src/platform_control/seeds/reference/jurisdictions.yaml` includes `jur_eu`.
- `platform-control/src/platform_control/seeds/reference/authorities.yaml` includes all EU
  authorities.
- `country-overlays/eu/` carries the overlay YAML quartet.
- `document_intelligence/nlp/citation_extractor.py` recognizes CELEX
  and `ECLI:EU:*` identifiers.

Not yet done:

- First acceptance run against
  `http://publications.europa.eu/webapi/rdf/sparql` with CELEX
  `32016R0679` (GDPR). Needs GCP auth + dev environment.
- Flip `enabled: true` on at least one blueprint template once the
  acceptance run captures evidence.
- Evidence under `docs/runbooks/evidence/<date>-eu-eurlex-smoke-run1.md`.

## Known-good smoke targets

When wiring the first live adapter, anchor against:

| CELEX | ELI | Description |
|-------|-----|-------------|
| `32016R0679` | `http://data.europa.eu/eli/reg/2016/679/oj` | GDPR (Regulation 2016/679) |
| `32019L0790` | `http://data.europa.eu/eli/dir/2019/790/oj` | Copyright in the Digital Single Market (Directive 2019/790) |

Both are stable, widely cited, and exist in all 24 official languages — good
for round-tripping `preferred_languages` behavior.

## Primary objective

Port the `fedlex_sparql` loop shape 1:1 to EUR-Lex:

1. Seed ELI URI → work node resolution (CELEX → `cdm:work_has_expression`)
2. Language selection via `acquisition_spec.preferred_languages`
3. HTML manifestation fetch via Cellar endpoint
4. Emit `ProviderResource` records matching the `FedlexSparqlProvider` shape

## Exit condition

The scaffold is upgraded to live when:

- `EurLexSparqlProvider.start_run` resolves `32016R0679` end-to-end on `dev`
- a recorded smoke run surfaces `content_type=text/html`, ≥1 raw artifact, and lifecycle event `document.processed`
- runbook evidence is captured at `docs/runbooks/evidence/<YYYY-MM-DD>-eu-eurlex-smoke-run1.md`
- `enabled: true` is flipped on at least one of the `eur_lex_sparql_*` templates in `source_blueprints.yaml`

## Serialization notes

EU live fetch can land fully in parallel with sub-federal national work;
the only shared surface is `source_blueprints.yaml` (`overlays.eu`). Keep
edits scoped to that subtree while the AT per-state / DE Länder / IT
regione templates continue evolving under their own subtrees.
