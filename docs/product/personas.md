# Personas (proposal)

Owner: Product / Platform team
Last reviewed: 2026-04-28
Status: **Draft** — extracted from existing engineering surfaces; segmentation of the legal end-user is **not yet validated** against research and should be treated as a hypothesis.

## Purpose

Name the audiences Evidara serves, so PRDs, GA criteria, runbooks, and UX work share a single vocabulary. Today the repo names "user", "operator", and "agent" inconsistently across [`system-context`](../architecture/system-context.md), [`interaction-flow-validation`](../runbooks/interaction-flow-validation.md), and the multi-country playbook. This page consolidates them.

## How to read this page

Each persona has a **Grounded** block (what the repo / journeys actually demand of them today) and a **Hypothesis** block (segmentation that has not been validated). Treat the hypothesis blocks as starting points for user research, not as commitments.

## Persona map

| Persona | Surface | Grounded source |
|---|---|---|
| Legal end user | `legal-search/frontend` | [legal-search.md:55](../components/legal-search.md), [interaction-flow-validation.md:35](../runbooks/interaction-flow-validation.md) (Journey 4) |
| Content operator | `platform-control/admin` + platform-control API | [system-context.md:125](../architecture/system-context.md), [interaction-flow-validation.md](../runbooks/interaction-flow-validation.md) (Journeys 1–3, 5), [multi-country playbook](../runbooks/platform-control-multi-country-operator-playbook.md) |
| Reviewer (HITL) | Argilla + platform-control rescore loop | [argilla-review-routing-and-sync.md](../runbooks/argilla-review-routing-and-sync.md), [`smoke-hetzner-hitl-rescore.sh`](../runbooks/mvp-acceptance-scenario-pack.md) |
| Platform / SRE operator | platform-control API, infra, runbooks | [phase-5-go-no-go-memo.md](../runbooks/phase-5-go-no-go-memo.md), [DLQ triage](../runbooks/dlq-triage-and-replay.md), [release/rollback](../runbooks/release-rollback.md) |
| Agent / CLI operator | `tools/evidara-cli`, MCP-style scripted access | [evidara-cli README](../../tools/evidara-cli/README.md), [mvp-acceptance-scenario-pack.md](../runbooks/mvp-acceptance-scenario-pack.md) |

The first three are external; the last two are internal. GA criteria should distinguish them — see [ga-criteria.md](https://github.com/philipplukas/evidara/blob/main/docs/product/ga-criteria.md) once landed (companion PR [#490](https://github.com/philipplukas/evidara/pull/490)).

---

## P1 — Legal end user

The audience the product is **for**. Today only addressed in the singular ("a user can search, open detail, filter") in [legal-search.md:55](../components/legal-search.md).

### Grounded

- Issues a **text query** and selects from result list ([legal-search.md:30](../components/legal-search.md))
- Filters by **jurisdiction, document type, language** (BFF facets, [legal-search.md:13](../components/legal-search.md))
- Opens a **detail view** with `content`, `sections`, `citations`, `details` tabs ([internal-beta-user-flow-evidence.md:54](../runbooks/internal-beta-user-flow-evidence.md))
- Reads in **German** UI today; FR/IT planned (ADR-0013)
- The internal-beta corpus is **12 Swiss federal laws** — current trust loop is built around recognizing these documents and their metadata, not broad relevance

### Hypothesis: segmentation (not validated)

Three plausible sub-personas. **None of these has been confirmed by interviews or analytics** — call this out before referencing them in a PRD.

| Sub-persona | Primary task | What success looks like |
|---|---|---|
| **Practising lawyer** (in-house counsel, partner) | Find the controlling provision or precedent for a specific matter, fast | Top-3 result is the right citation; detail view is trustworthy enough to drop into a brief |
| **Legal researcher** (academic, librarian, knowledge manager) | Explore a topic across sources, build a reading list | Filters narrow effectively; section-level navigation; export / copy a stable citation |
| **Paralegal / junior associate** | Pull supporting material a senior asked for | Search recognises shorthand titles ("ZGB", "OR"); detail page surfaces canonical title and section anchors |

### Open questions for research

- Which of these three is the **wedge** persona for GA?
- How tolerant is each to a small (12-doc) corpus during early access?
- Do they expect citation-aware search before they consider the product credible?

---

## P2 — Content operator

Internal role. Manages the source-to-published pipeline through the admin UI.

### Grounded

- Creates sources, source versions, approves them, triggers runs ([interaction-flow-validation.md](../runbooks/interaction-flow-validation.md) Journeys 1–3)
- Operates per-country overlays (CH, AT, DE, FR, IT) with country-specific approval and triage hotspots ([multi-country playbook](../runbooks/platform-control-multi-country-operator-playbook.md))
- Jumps between admin and legal-search via the cross-surface header link with namespaced handoff context (`ls_return_to`, `ls_query`, …) ([interaction-flow-validation.md:75](../runbooks/interaction-flow-validation.md) Journey 5)
- Reads run lifecycle events, processing status, and document-lifecycle history through platform-control API
- Works in dev / staging / prod with audience-scoped Cloud Run ID tokens ([gcp-local-cloud-run-auth.md](../setup/gcp-local-cloud-run-auth.md))

### Pain points the docs already acknowledge

- Cross-surface handoff is intentional and **only partially complete** — it carries query/scope context but no broader operator state
- Country overlays are **CH first**; AT/DE/FR/IT depth varies
- HITL rescore loop is **internal staging only** (Hetzner), not productized

---

## P3 — Reviewer (HITL)

A specialist sub-role. Today represented by the Argilla review routing + rescore loop.

### Grounded

- Receives review tasks routed from extraction / processing
- Submits corrections that flow back through `rescore_request` → Temporal → metrics ([smoke-hetzner-hitl-rescore.sh](../runbooks/mvp-acceptance-scenario-pack.md))
- Operates on **Hetzner staging only** today

This persona is **not yet a product surface** — it is a Temporal + Argilla loop with smokes. Treat as forward-looking.

---

## P4 — Platform / SRE operator

Internal. Owns runtime health, releases, drills, evidence packets.

### Grounded

- Runs phase-5 / TAR-69 release-readiness evidence and gates ([phase-5-go-no-go-memo.md](../runbooks/phase-5-go-no-go-memo.md))
- Executes operational drills: withdrawal, DLQ, rollback ([post-mvp-engineering-workstreams.md](../runbooks/post-mvp-engineering-workstreams.md))
- Captures evidence as **GitHub Actions run URLs + GCS artifact bundles**, not screenshots
- Operates against **dev-first**; staging is optional when a staging GCP project is absent ([environment-strategy.md](../setup/environment-strategy.md))

---

## P5 — Agent / CLI operator

Programmatic access — humans-via-script today, agents soon.

### Grounded

- Drives `evidara workflow mvp-acceptance`, `evidara` pings, OpenAPI discovery ([evidara-cli README](../../tools/evidara-cli/README.md))
- Mints audience-scoped tokens for both platform-control and legal-search ([mvp-acceptance-scenario-pack.md:58](../runbooks/mvp-acceptance-scenario-pack.md))
- Treats **single-line JSON** as the default output (the `--human` mode is for operators, not agents)

This persona is internal today (CI, smokes, evidence packets). Whether it becomes a **public** API surface is a GA-scope decision, not a doc decision.

---

## What this page is **not**

- Not a marketing audience deck — no ICP, segment sizing, or pricing
- Not user research — none of the sub-segmentation under P1 has been interview-validated
- Not a commitment that all five personas are GA-targets — see [ga-criteria.md](https://github.com/philipplukas/evidara/blob/main/docs/product/ga-criteria.md) for which lanes need to be ready for which GA gate (companion PR [#490](https://github.com/philipplukas/evidara/pull/490))

## Next steps

1. Validate the P1 sub-segmentation with 5–8 interviews (practising lawyer, researcher, paralegal mix)
2. Decide which P1 sub-persona is the **wedge** for the first external GA
3. Decide whether P5 (agent / CLI) is in or out of scope for that GA
4. Promote this doc from **proposal** to **canonical** once the wedge is named
