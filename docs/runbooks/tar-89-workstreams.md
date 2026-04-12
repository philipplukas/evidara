# TAR-89 — workstreams (repo checklist)

Owner: Platform / legal-search  
Last reviewed: 2026-04-11  
Last verified: 2026-04-11  
Applies to: Linear **[TAR-89](https://linear.app/tart-baozi/issue/TAR-89)** (search/detail metadata credibility)

This file splits TAR-89 into **three implementation tracks** so work can be filed as sub-issues (or child issues) in Linear without duplicating acceptance text. **Canonical acceptance** remains [metadata quality plan status](metadata-quality-plan-status.md) **section 3.5** and the TAR-89 issue description — keep them in sync per that doc’s section 5.

---

## Track 1 — Data path (acquisition → DI)

| Sub-issue idea | Scope | Primary code / docs |
|----------------|-------|---------------------|
| **Bundle hints** | Richer metadata in bundle manifest / acquisition so lean rows carry `document_type_hint`, citation, language | `platform-control` workers, bundle registration |
| **Normalizer** | HTML/XML normalization, `source_defaults`, `extracted_metadata`, official citation | [`document-intelligence`](../../document-intelligence/README.md) pipeline, `document_intelligence/extractors/metadata.py` |
| **LLM pilot** | Optional extractor; default **off**; observability + cost bounds before staging/prod | DI README “LLM extraction policy”, `DI_ENABLE_LLM_EXTRACTOR` |

**Exit (track):** agreed corpus lean payloads (local **3.5.1** and staging **3.5.2**) contain mappable hints so projections are not guessing from empty fields.

---

## Track 2 — Serving path (projections → BFF → UI)

| Sub-issue idea | Scope | Primary code / docs |
|----------------|-------|---------------------|
| **Projections** | Map lean → search document; title/type fallbacks | [`legal-search/api/src/modules/projections/projections.service.ts`](../../legal-search/api/src/modules/projections/projections.service.ts) |
| **Search rank shape** | Field boosts (separate Linear **TAR-82** when tuning) | [`legal-search/api/src/modules/search/opensearch.adapter.ts`](../../legal-search/api/src/modules/search/opensearch.adapter.ts) |
| **Detail trust** | `MetadataRow` labels/icons, `MetadataSection` | [`legal-search/frontend/src/components/detail/MetadataSection.tsx`](../../legal-search/frontend/src/components/detail/MetadataSection.tsx), [`metadata-icons.ts`](../../legal-search/api/src/core/presentation/metadata-icons.ts) |

**Exit (track):** section **3.5** “Search / list” and “Detail” bullets pass for the agreed IDs after fresh index rows exist.

---

## Track 3 — Environment truth (remote dev / optional staging / demo)

| Sub-issue idea | Scope | Primary docs |
|----------------|-------|----------------|
| **Re-projection** | Refresh OpenSearch after BFF/projection changes without full DI | [staging projection replay](staging-projection-replay.md) |
| **Remote acceptance** | Verify **3.5.2** IDs (dev or staging inventory); sign-off template **3.5.3** | [metadata quality plan](metadata-quality-plan-status.md) §3.5.2–3.5.3 |
| **Local reference** | Lean stack + fixture trace | [legal-search lean local](../setup/legal-search-lean-local.md), plan §3.5.1 / §6.8 |

**Exit (track):** Linear comment per **3.5.3** with date, IDs, replay/re-index note, owner — only when criteria are **actually** met (replay alone is insufficient if lean lacks hints; see staging projection replay runbook).

---

## Filing in Linear

1. Create **child issues** (or linked issues) under TAR-89 named roughly: `TAR-89 / data`, `TAR-89 / serving`, `TAR-89 / staging verification`.
2. Paste the relevant table row(s) into each issue description and link back to this file.
3. Do **not** fork acceptance wording; edit **section 3.5** in the metadata plan first, then mirror to Linear.

## Related

- [Metadata quality plan status](metadata-quality-plan-status.md) — done vs outstanding, **3.5** acceptance
- [MVP demo release recommendation](mvp-demo-release-recommendation.md) — conditional GO, TAR-89 risk callout
- [Phase 5 go / no-go memo](phase-5-go-no-go-memo.md) — release gates adjacent to metadata
