# GA criteria (proposal)

Owner: Product / Platform team
Last reviewed: 2026-04-28
Status: **Draft** — converts the milestone roadmap, the legal-search "Later expansion" list, and the phase-5 memo into a single launch-gate page. Owners and dates are placeholders until reviewed.

## Purpose

There is **no single source of truth today** for what "GA" means at Evidara. Two different things share the name:

1. **Phase-5 / vertical-slice GA** — the engineering release-readiness gate. Already signed off on **2026-04-21** per [`phase-5-go-no-go-memo.md` §1](../runbooks/phase-5-go-no-go-memo.md). Scope: one Firecrawl source family, one HTML artifact per bundle, Swiss content as the working reference ([first-vertical-slice.md:11](../components/first-vertical-slice.md)).
2. **Product GA** — broad external availability for the [legal end-user persona (P1)](https://github.com/philipplukas/evidara/blob/main/docs/product/personas.md). **Not yet defined.** This page proposes that definition.

This page covers **product GA**. For phase-5 release-readiness, keep using [phase-5-go-no-go-memo.md](../runbooks/phase-5-go-no-go-memo.md).

## How to read this page

Each lane has a **Today** row (grounded in the repo, with a source link), a **Required for GA** row (proposed bar), and a **Source** row showing where the requirement comes from. Anything I cannot ground is marked `proposal — needs decision`.

---

## Lanes

### Lane 1 — Content scope

What documents are searchable and credible.

| | State |
|---|---|
| **Today** | 12 Swiss federal laws (`internal-beta-v2`); CH-only; one Firecrawl source family; one HTML artifact per bundle |
| **Required for GA** | `proposal — needs decision`. Minimum: full CH federal corpus + one peer country (AT, DE, FR, or IT). Cantonal/sub-national left to post-GA. |
| **Source** | [internal-beta-user-flow-evidence.md:21](../runbooks/internal-beta-user-flow-evidence.md), [first-vertical-slice.md:11](../components/first-vertical-slice.md), [five-country-content-rollout.md](../components/five-country-content-rollout.md) |

**Open issues:** [#259] Swiss municipality registry, [#260] German municipality registry (M4 of [#279]).

### Lane 2 — Search experience

What the end user can actually do.

| | State |
|---|---|
| **Today** | Text query, faceted filters (jurisdiction / type / language), highlighted snippets, document detail with `content` / `sections` / `citations` / `details` tabs ([legal-search.md:13](../components/legal-search.md)) |
| **Required for GA** | Section-level navigation in detail view; citation-aware search; ranking that survives the chosen wedge persona's queries (see [personas.md P1](https://github.com/philipplukas/evidara/blob/main/docs/product/personas.md)). Semantic search and per-language analyzers may stay post-GA. |
| **Source** | [legal-search.md:61](../components/legal-search.md) "Later expansion"; section-level / citation-aware / semantic / per-language analyzers all listed there |

**Decision needed:** which "Next" capabilities are GA-blocking vs nice-to-have.

### Lane 3 — Internationalization

UI and document language coverage.

| | State |
|---|---|
| **Today** | German UI only; BFF locale-aware (ADR-0013 phases 1–2 done) |
| **Required for GA** | UI in the languages of the GA content lanes (at minimum DE; FR/IT if FR or IT is in Lane 1) |
| **Source** | [legal-search.md:67](../components/legal-search.md) "Later expansion"; ADR-0013 |

### Lane 4 — Tenant / corpus model

Multi-customer separation.

| | State |
|---|---|
| **Today** | `tenant_id`, `corpus_id`, `scope_type` carried through acquisition config and event provenance; **no first-class corpus CRUD** ([first-vertical-slice.md:18](../components/first-vertical-slice.md)) |
| **Required for GA** | `proposal — needs decision`. If GA is single-tenant (one shared corpus) the current model is acceptable. If GA serves multiple paying customers in the same deployment, first-class tenant + corpus CRUD is required. |
| **Source** | [first-vertical-slice.md:18](../components/first-vertical-slice.md) explicitly defers this; [security-and-tenancy.md](../architecture/security-and-tenancy.md) |

**Decision needed:** single-tenant or multi-tenant at GA.

### Lane 5 — Operator readiness

What internal staff need to run the product day-to-day.

| | State |
|---|---|
| **Today** | Source lifecycle journeys, run orchestration, DI ingest, cross-surface jump are all green ([interaction-flow-validation.md:30](../runbooks/interaction-flow-validation.md)). HITL rescore loop runs only on Hetzner staging ([mvp-acceptance-scenario-pack.md:27](../runbooks/mvp-acceptance-scenario-pack.md)). Multi-country playbook covers CH/AT/DE/FR/IT ([playbook](../runbooks/platform-control-multi-country-operator-playbook.md)). |
| **Required for GA** | Operator drills (withdrawal, DLQ, rollback) executed with evidence in prod; HITL loop available in the GA environment (or explicitly out-of-scope and documented as such). |
| **Source** | [post-mvp-engineering-workstreams.md](../runbooks/post-mvp-engineering-workstreams.md) (TAR-67); [phase-5-go-no-go-memo.md §2.1](../runbooks/phase-5-go-no-go-memo.md) |

### Lane 6 — Trust and credibility

Whether the detail view is something a lawyer would cite.

| | State |
|---|---|
| **Today** | "Trust loop" baseline — non-placeholder titles, controlled `law` type, Fedlex subtitle, ≥4 metadata rows, `content`/`sections`/`citations`/`details` tabs ([internal-beta-user-flow-evidence.md:54](../runbooks/internal-beta-user-flow-evidence.md)). Phase-5 memo §1.0 explicitly names "product-trust phase" as the current planning posture ([phase-5-go-no-go-memo.md §1.0](../runbooks/phase-5-go-no-go-memo.md)). |
| **Required for GA** | `proposal — needs decision`. Minimum: provenance chain visible on every detail; stable canonical citation; export/copy that preserves source pointer. |
| **Source** | [phase-5-go-no-go-memo.md §1.0](../runbooks/phase-5-go-no-go-memo.md) "trustworthy proof experience" milestone |

### Lane 7 — Reliability and infra

CI, environments, runtime stability.

| | State |
|---|---|
| **Today** | Phase-5 release-readiness signed off 2026-04-21. Open: image-build flakes ([#274]), temporal-test 403 ([#278]), compliance-policy migrations not applied to staging/prod ([#253]). |
| **Required for GA** | M1 (CI reliability) green; M2 (compliance migrations) applied in prod with seeded `cp_ch_fedlex` + `cp_at_ris_ogd`; alembic head matches in dev/staging/prod. |
| **Source** | [#279] M1, M2; [phase-5-go-no-go-memo.md §2](../runbooks/phase-5-go-no-go-memo.md) |

### Lane 8 — Architecture hygiene

Internal contracts that block scaling.

| | State |
|---|---|
| **Today** | Two ID-contract sources (`reference/` canonical, `hierarchies/` legacy); no canonical naming layer; direct `process.env` usage in places. |
| **Required for GA** | M3 (CH legal-hierarchy consolidation, ADR-0264 + retire `hierarchies/`) and M5 (config boundary, canonical names) at minimum to a green-lint state. M6 (design system) acceptable post-GA. |
| **Source** | [#279] M3, M5, M6; [#264], [#258], [#270]–[#273] |

### Lane 9 — Compliance and security

Legal posture for serving regulated content.

| | State |
|---|---|
| **Today** | Robots and rate-limit enforcement live in code; not yet seeded in prod (see Lane 7 / M2). [security-and-tenancy.md](../architecture/security-and-tenancy.md) covers IAM and Cloud Run audience tokens. |
| **Required for GA** | `proposal — needs decision`. Minimum: terms-of-use review by counsel for each GA jurisdiction; data-retention defaults documented; PII review for any user-submitted query logging. |
| **Source** | Not yet documented — gap |

### Lane 10 — Pricing, packaging, support

Commercial readiness.

| | State |
|---|---|
| **Today** | **No documentation in repo.** No pricing, no SLA, no support runbook for external users. |
| **Required for GA** | `proposal — needs decision`. Out of scope for engineering doc; this lane is here to make the gap visible. |
| **Source** | Gap |

---

## Open decisions (must close before this page leaves draft)

1. **Wedge persona** — which P1 sub-persona from [personas.md](https://github.com/philipplukas/evidara/blob/main/docs/product/personas.md) is the GA target?
2. **Content lanes** — CH-only or CH + one peer country at GA?
3. **Tenancy** — single-tenant or multi-tenant at GA?
4. **Search depth** — is citation-aware search GA-blocking, or post-GA?
5. **Agent surface** — is `tools/evidara-cli` and an MCP-style API a GA surface, or internal only?
6. **Compliance scope** — who owns Lane 9, and on what timeline?

---

## Anti-scope (explicit non-goals for first product GA)

These are **not** GA-blockers in this proposal. List them so they do not creep back in.

- Semantic / vector search ([legal-search.md:71](../components/legal-search.md))
- Per-language OpenSearch analyzers (same)
- Cantonal and sub-national CH coverage (post-M4)
- Design-system consolidation ([#277], M6)
- Public agent / MCP API (unless decision (5) above flips it in)

---

## Relationship to existing release docs

| Doc | Scope |
|---|---|
| **This page** | Product GA — when do we open to external customers |
| [phase-5-go-no-go-memo.md](../runbooks/phase-5-go-no-go-memo.md) | Engineering release-readiness gate (signed off 2026-04-21) |
| [first-vertical-slice-exit-gates.md](../runbooks/first-vertical-slice-exit-gates.md) | Vertical-slice exit criteria — supports phase-5, not product GA |
| [milestone-planning-rubric.md](../runbooks/milestone-planning-rubric.md) | Lens for milestone-by-milestone planning updates |

If this page conflicts with `phase-5-go-no-go-memo.md`, the memo wins for engineering release decisions; this page wins only for product GA framing.
