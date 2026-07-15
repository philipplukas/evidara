# Reasoning-surface work items — execution breakdown of ADR-0033

Owner: Founder
Last reviewed: 2026-07-15
Status: **Draft** — turns [ADR-0033 "Agentic Legal Reasoning"](../adr/0033-agentic-legal-reasoning.md)
from a decision into sequenced, acceptance-gated, file-grounded work. ADR-0033 scopes this
work to **M13/M14** (the "dog question" acceptance test); this doc is the execution anchor
for that build order. It is a planning artifact — it *scopes* code work, it is not code.

## Why this doc exists

ADR-0033 settled the strategy (RAG to enter, graph to reason; MCP as the tool surface;
"do not build the MCP server first") and fixed the acceptance test: *can the city ban a
certain thing for dogs, year-round?* What it did **not** produce is an execution anchor —
which endpoints/producers to build, in what order, reusing which existing code, with what
acceptance and which narrowest test. This doc is that anchor.

**Substrate ≠ endpoint (the honest baseline).** It is tempting to say the reasoning
primitives are "live today." More precisely: the *logic/substrate* for several of them is
built and tested (norm hierarchy `level` + `subordinate_to` + in-force dates landed via
#591), but the *primitive-shaped endpoints* — section-granular, `as_of`-first,
provenance + `trust_tier` inline — mostly **do not exist yet**. That surface gap is the
work below. Verified against the repo on 2026-07-15.

> Naming: this doc uses ADR-0033's canonical tool names (`search_law`, `get_provision`,
> `resolve_citation`, `find_citing`, `norm_hierarchy`, `check_in_force`). The MCP tools are
> the *product* of the endpoints below; ADR-0033 §4 forces the endpoints first.

## Section 1 — Substrate vs. endpoint (verified)

| ADR-0033 tool | Substrate today (verified) | Endpoint today | Gap = work |
|---|---|---|---|
| `check_in_force` | `legal-search/api/src/core/norm-hierarchy/in-force.ts` — `resolveInForceState`, `InForceFields`, `InForceState`, `inForceExclusionClauses`; tested (`in-force.spec.ts`) | none (used only inside norm-hierarchy) | expose as an endpoint |
| `find_citing` (inbound) | `documents/opensearch.adapter.ts` reverse-citation query on `target_document_id` (~L162); **document**-granular; tested | `GET /v1/documents/{id}/cited_by` (`documents.controller.ts:28`) | add **outbound** `cites`; section granularity (needs #573) |
| `norm_hierarchy` | `modules/norm-hierarchy/` hexagonal module; `subordinate_to` set at projection time; `level` (#591); tested | `GET /v1/norm-hierarchy/{jurisdiction_id}` (`norm-hierarchy.controller.ts:13`) | thin section→jurisdiction wrapper |
| coverage / refusal (ADR-0033 §2) | `coverage` sub-block inside the norm-hierarchy view (`norm-hierarchy.service.ts:102` — `covered_levels` / `missing_levels`) | none standalone | lift to a first-class endpoint |
| delegation (the WALK-UP step) | traversal substrate built; `delegates_to` **declared-only, produced nowhere** — `projections.service.ts:228` ("cannot be derived from the tree"), `projections.repository.ts:111` ("Declared, not yet produced"); schema in `contracts/schemas/{document,search-projection}.schema.json`; mapping in `core/opensearch/documents-index.mapping.ts:103` | none | **the moat: a `delegates_to` producer (HITL) + a traversal endpoint** |
| `resolve_citation` | `citation-targets` is index **config only** (`projections/opensearch.adapter.ts`, `core/config/opensearch.config.ts`) — never populated (ADR-0033: 504 citations extracted as strings, zero resolved) | none | endpoint **+ upstream: populate `citation-targets`** |
| `get_provision` / `search_law` | article-level sectioning (#573) still missing; search is BM25 `multi_match` only | search exists (BM25) | out of scope for *surfacing* — these are ADR-0033 build-order steps 1 & 5 |

## Section 2 — Reused patterns (grep before you create)

- **Hexagonal module.** controller → service → repository (interface + `Symbol` token) →
  `opensearch.adapter` → `dto` + `entities`. Canonical example and closest analog to a
  primitive: `legal-search/api/src/modules/norm-hierarchy/`. External-dependency variant
  (a port over a downstream service): `modules/documents/`.
- **Spec-first, CI-gated.** Edit `contracts/api/legal-search.openapi.yaml` **first**, then
  `cd legal-search/frontend && npm run openapi:generate`, and commit the generated client.
  Drift gate: `npm run openapi:check`. The `agent-discovery` tag already exists
  (`legal-search.openapi.yaml:37`) and is applied to search / documents / norm-hierarchy
  read endpoints — add it to each new read-only primitive.
- **In-force logic.** Reuse `core/norm-hierarchy/in-force.ts` (`resolveInForceState`,
  `InForceFields`). Do **not** re-implement the four-valued state machine.
- **Narrowest test = a unit `*.spec.ts` mocking the adapter** (pattern:
  `norm-hierarchy.service.spec.ts`). The `*.integration.spec.ts` tier is
  scaffolded-but-empty and not wired to any script — do **not** promise integration tests
  as a work item's proof.

## Section 3 — The work items

Sequenced by ADR-0033's forced build order (substrate → surface → MCP; §4 "do not build the
MCP server first") and the validation gate: **Phase 1 is the minimal primitives to put in
front of a design partner; Phases 2–4 stay gated on V (willingness to pay).**

### Phase 1 — Surface the substrate (thin wrappers, no new data, low risk)

- **WI-1 — `check_in_force` endpoint.** `GET /v1/sections/{id}/in-force?as_of=`. Wrap
  `resolveInForceState` over a section/document lookup; return state + provenance + an
  `as_of` echo. New module mirroring `norm-hierarchy/`. Launch at **document** granularity
  first (matches the existing `cited_by`), tighten to section as #573 lands.
  *Test:* service spec asserting each of the four in-force states.
- **WI-2 — `find_citing` outbound (`cites`) + section granularity.** Add
  `GET /v1/documents/{id}/cites` beside the existing `cited_by`
  (`documents.controller.ts:28`). Outbound is the *same* citations index keyed by source id
  — mirror the reverse-citation query in `documents/opensearch.adapter.ts` (~L162, which
  terms on `target_document_id`). *Test:* adapter spec + service spec.
- **WI-3 — `norm_hierarchy(section_id)` wrapper.** A thin endpoint resolving a
  section → its jurisdiction → the existing norm-hierarchy view. Reuse
  `norm-hierarchy.service` (`getHierarchy`). *Test:* service spec.
- **WI-4 — Shared primitive envelope.** One response wrapper carrying `provenance` +
  `as_of` + `trust_tier` inline (schema in `contracts/schemas/`, one mapper). Every
  primitive returns it. Define it here once so WI-1..3 and Phase 2 reuse it.
  *Test:* mapper spec.
- **WI-5 — coverage/refusal + discovery.** Lift the norm-hierarchy `coverage` sub-block
  (`norm-hierarchy.service.ts:102`, `covered_levels`/`missing_levels`) into a first-class
  `GET /v1/coverage?jurisdiction=`, plus `GET /v1/jurisdictions` and `/v1/authorities`
  backed by the reference seeds
  (`platform-control/src/platform_control/seeds/reference/{jurisdictions,authorities}.yaml`).
  This is the substrate for ADR-0033 §2 ("the agent must be able to refuse"). A freshness
  field is **M3 / out of scope** — mark the slot, don't fill it. *Test:* service spec over
  a seed fixture.

### Phase 2 — The moat: `delegates_to` producer + traversal [V-gated]

- **WI-6 — `delegates_to` producer via HITL curation.** The load-bearing item. The edge is
  declared with shape `{ target_level, target_jurisdiction_id, scope }` in
  `contracts/schemas/{document,search-projection}.schema.json` and mirrored so it projects
  **without a migration**; `projections.service.ts:228` explicitly declines to derive it
  ("cannot be derived from the tree"). Because asserting a delegation is a *legal judgment*,
  the first producer is **operator curation in a mandatory-review band**, not NLP.
  Sub-parts:
  - (a) Where operators assert an edge — **check the existing corrections lifecycle before
    inventing a type**: `platform-control/src/platform_control/services/correction_service.py`,
    `routers/corrections.py`, `schemas/correction.py`.
  - (b) Carry it through to the projection so `applyNormHierarchy`
    (`projections.service.ts:231`) populates `delegates_to` from the curated source.
  - (c) The review gate (mandatory-review band).

  *Test:* projection spec asserting a curated edge lands in the projection; state-machine
  test for the review band.
- **WI-7 — delegation-chain traversal.**
  `GET /v1/delegation-chain?topic=&jurisdiction=&as_of=`. Composes `subordinate_to`
  (pre-emption reachability) + `delegates_to` (competence) + per-layer in-force + the
  coverage/refusal block. The traversal can be **built against the substrate before WI-6
  lands** (returns an empty `delegates_to` set + an honest coverage gap), then lights up as
  curation adds edges. *Test:* service spec over a fixture graph including the refusal path
  (a missing layer → a correct refusal, per ADR-0033 §2).

### Phase 3 — `resolve_citation` [upstream data dependency]

- **WI-8 — `resolve_citation` endpoint.** `GET /v1/citations/resolve?ref=&as_of=`.
  **Blocked on populating `citation-targets`** (ADR-0033: 504 citations extracted as
  strings, zero resolved; `normalize_citation` in
  `document-intelligence/.../nlp/citation_extractor.py` already emits canonical keys
  `sr:210` / `celex:…`). That population is the citation-graph build (ADR-0033 build-order
  step 2 / #594) — flag it as a **prerequisite**, not part of the endpoint WI. The endpoint
  itself is thin once the index is populated.

### Phase 4 — Distribution [V-gated, build last]

- **WI-9 — product corpus MCP server.** Tools 1:1 over the Phase 1–3 primitives, over the
  legal-search API. New package — its structure may mirror `tools/zed-evidara-mcp/`
  (FastMCP), but it is **product-facing and distinct** from that dev-guide MCP; do not
  conflate them. Build **after** the primitives exist (ADR-0033 §4: "do not build the MCP
  server first").
- **WI-10 — API keys, usage metering, per-plan rate limits.** Self-serve onboarding infra;
  independent of the primitives and can proceed in parallel with Phases 2–3, but is not a
  demo blocker. (Overlaps `work-packages-milestones.md` §M2 WP 2.4 — the commercial-surface
  milestone — track the dependency there.)

**Contract-first is not a separate WI** — it is baked into every endpoint WI's definition
of done: edit the OpenAPI YAML → regenerate the orval client → `openapi:check` green → docs
updated.

## Dependency shape

```
ADR-0033 build order (data)          Endpoint surfacing (this doc)
─────────────────────────            ─────────────────────────────
#573 sectioning ─────────┐
                         ├─► Phase 1: WI-1 in_force · WI-2 cites ·
norm hierarchy (#591) ───┤            WI-3 norm_hierarchy · WI-4 envelope ·
subordinate_to ──────────┘            WI-5 coverage/refusal     [ships to design partner]
                                                │
delegates_to (declared,  ────────────► Phase 2: WI-6 HITL producer ─► WI-7 traversal  [V-gated]
 not produced)                                  │
citation-targets (empty) ────────────► Phase 3: WI-8 resolve_citation  [needs #594 populate]
                                                │
                                        Phase 4: WI-9 MCP (last) · WI-10 API keys  [V-gated]
```

## Filing the work

If these become GitHub issues, `/issue-execute <number>` per WI is the intended path. Each
WI's definition of done is: code + narrowest unit spec + contract regenerated + this doc /
the relevant component doc updated.
