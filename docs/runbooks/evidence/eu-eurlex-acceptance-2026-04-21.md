# EU EUR-Lex Acceptance Evidence (2026-04-21)

## Summary

First successful EU EUR-Lex SPARQL provider run on dev. The GDPR
(Regulation 2016/679) was captured end-to-end via the Cellar SPARQL
endpoint with correct title, XHTML content, and CELEX metadata.

## Run details

- **Environment:** dev (Cloud Run)
- **Run ID:** `run_01kprvzmxx7h9z65e0bffm3mdh`
- **Source ID:** `src_01kprv0yc8emx2w8w78m0hmcwy`
- **Template:** `eur_lex_sparql_regulation_en`
- **Seed URI:** `http://data.europa.eu/eli/reg/2016/679/oj`
- **Status:** completed
- **Captured resources:** 1
- **Artifacts:** 1

## Captured document

| Field | Value |
|-------|-------|
| Title | Regulation (EU) 2016/679 of the European Parliament and of the Council of 27 April 2016 on the protection of natural persons with regard to the processing of personal data and on the free movement of such data, and repealing Directive 95/46/EC (General Data Protection Regulation) (Text with EEA relevance) |
| Content type | `application/xhtml+xml` |
| Final URL | `http://publications.europa.eu/resource/cellar/3e485e15-11bd-11e6-ba9a-01aa75ed71a1.0006.03` |
| CELEX | `32016R0679` |
| Language | English |

## Pipeline verification

| Step | Result |
|------|--------|
| ELI → Cellar URI resolution (owl:sameAs) | **pass** |
| Expression discovery (cdm:expression_belongs_to_work) | **pass** |
| Language selection (English preferred) | **pass** |
| Manifestation selection (XHTML preferred) | **pass** |
| Title extraction (cdm:expression_title) | **pass** |
| HTML content negotiation (Accept header) | **pass** |
| Content type | **pass** — `application/xhtml+xml` (not RDF) |

## Bugs fixed during acceptance

1. **EurLexSparqlAcquisitionSpec missing** — provider existed but Pydantic
   schema wasn't registered in discriminated union (PR #332)
2. **Blueprint `enabled` field** — passed through to spec parsing, rejected
   by `extra="forbid"` (direct fix, stripped in `resolve_source_blueprint`)
3. **SPARQL predicate direction** — CDM uses inverse predicates:
   `expression_belongs_to_work` not `work_has_expression`,
   `manifestation_manifests_expression` not `expression_manifested_by_manifestation`
4. **ELI URI host mismatch** — seed uses `data.europa.eu` but Cellar stores
   `publications.europa.eu` in owl:sameAs triples
5. **Manifestation format labels** — Cellar returns short labels (`xhtml`)
   not full authority IRIs (`http://.../file-type/XHTML`)
6. **Content negotiation** — manifestation URIs return RDF by default;
   needs `Accept: application/xhtml+xml` header (PR #336)

## Template enablement

Both EUR-Lex templates flipped from `enabled: false` to `enabled: true`:
- `eur_lex_sparql_regulation_en` (GDPR)
- `eur_lex_sparql_directive_en` (Copyright Directive 2019/790)
