# Work packages & milestones — platform fork

Owner: Founder
Last reviewed: 2026-07-10
Status: **Draft** — execution plan derived from the locked working thesis in [`value-proposition-canvas.md`](./value-proposition-canvas.md). Turns strategy into sequenced, acceptance-gated work. Tags: **[grounded]** = concrete repo state today; **[new]** = to be built.

## How to read this

Milestones are ordered by **what unblocks what**, not by size. The **Validation track (V)** runs *in parallel* with build — because the riskiest unknown is commercial ("will a builder pay?"), not technical ("can we build it?"). Do not let M2/M3 (heavy build) run ahead of V (which tells you whether to build them at all).

**Critical path:** M0 → M1, with V1 starting immediately alongside M0.

---

## M0 — Make the seeded corpus actually searchable (P0, unblocks everything)

Today a seeded document is processed by DI and `document.processed` is published to NATS, **but it never reaches search** — two bridges are missing and one deploy pin is only live-patched. Until M0 is done, there is nothing to demo to a design partner. Small, do first.

| WP | Work | Acceptance | Grounding |
|---|---|---|---|
| **0.1** | Set `DOCUMENT_INTELLIGENCE_BASE_URL` (+ `DOCUMENT_INTELLIGENCE_API_KEY`) on legal-search-api so projections can fetch document bodies | `applyDocumentProcessed` fetches the lean doc and indexes it; no more "DI read API unavailable" skips | [grounded — `document-intelligence.config.ts`, `projections.service.ts`; DI service at `GET /v1/documents/{id}/lean`] |
| **0.2** | Build an **always-on NATS→projection bridge**: a consumer on `evidara.document-processed` that POSTs to `/v1/projections/events/document-processed` | Seeding a source → document appears in search **with no manual replay** | [grounded — logic already exists in `jobs/local_outbox_replay.py` (`_post_json`, `_post_projection`); mirror `nats_consumer.py` for the live loop] |
| **0.3** | Persist the di-consumer image pin (currently live-patched to the #513 digest) into `infra/hetzner/apps/kustomization.yaml` via PR | `kubectl apply -k` no longer reverts the fix; consumer stays on #513 build | [grounded — kustomization pins branch tag `claude-repo-status-check-cdso8i`; #513 fix must survive re-apply] |

**Exit gate:** end-to-end demo — seed a Swiss federal law, watch it become searchable in legal-search within minutes, unattended.

---

## M1 — Coverage diamond (prove the ingestion engine generalizes)

Proves the platform thesis: the same trust/provenance/citation machine holds across the *deep* and *wide* axes. ~4 sources, chosen to stress structure and locale — not breadth for its own sake. See [canvas §4c](./value-proposition-canvas.md).

| WP | Work | Acceptance | Axis proved |
|---|---|---|---|
| **1.1** | CH **federal** (Fedlex) baseline — already ingestible | Corpus > the 12-doc beta; provenance + in-force + citations intact | baseline |
| **1.2** | **+1 canton** adapter (e.g. Zürich) — `jur_ch_zh`, `auth_zh_*` | Cantonal law ingested; trust fields correct despite different publication | deep (1 level down) |
| **1.3** | **+1 municipality** adapter (e.g. city of Zürich) — `jur_ch_gemeinde_*` | Municipal law ingested from low-structure source; trust survives degradation | deep (worst case) |
| **1.4** | **+1 second-country federal** (AT RIS `auth_at_ris` **or** DE `auth_de_bundesrecht`) | New authority/language plugs into the same pipeline unchanged | wide |

**Exit gate:** all four ingested; a reviewer confirms provenance, in-force status, and citation links are trustworthy on the *messiest* (municipal) source. If the abstraction cracks here, fix it before widening.

> Grounding: the ID model already addresses all of these — `seeds/reference/{jurisdictions,authorities}.yaml` span CH/AT/DE/FR/IT/EU with municipal depth (2,169 jurisdictions). The **new** work is per-authority **ingestion adapters**, not schema.

---

## M2 — Productize the read API (turn endpoints into an external product) [gated by V]

Only invest here once V (below) shows a builder will pay. Today's read API (`GET /v1/documents/{id}` `/lean` `/text`, bearer auth) is a foundation, not a product.

| WP | Work |
|---|---|
| **2.1** | Discovery/list endpoint: `GET /v1/documents?jurisdiction=&authority=&in_force=&updated_since=` |
| **2.2** | Citation-graph traversal: `GET /v1/documents/{id}/citations` (inbound/outbound) |
| **2.3** | Coverage introspection: `GET /v1/jurisdictions`, `/v1/authorities` |
| **2.4** | API keys, usage metering, per-plan rate limits (self-serve onboarding) |
| **2.5** | Contract-first: update `contracts/api/document-intelligence.openapi.yaml` + schemas + regenerate clients + docs |

**Exit gate:** a design partner integrates against the documented external API without hand-holding.

> Related but distinct: the **reasoning-surface primitives + MCP** (the graph-traversal
> tools from [ADR-0033](../adr/0033-agentic-legal-reasoning.md), scoped to M13/M14) are
> broken out as sequenced work items in
> [`reasoning-surface-work-items.md`](./reasoning-surface-work-items.md). WP 2.4 (API keys /
> metering / rate limits) is shared with that doc's WI-10.

---

## M3 — Freshness engine (the standing operational commitment) [gated by V]

The part that makes the API worth paying for — and the part you own forever. Deep × wide multiplies this cost; do not scale coverage past what you can keep fresh.

| WP | Work |
|---|---|
| **3.1** | Scheduled re-crawl + change detection per source |
| **3.2** | In-force transition tracking (active→superseded/repealed) with events |
| **3.3** | `GET /v1/changes?since=` freshness feed + published staleness SLA + monitoring |

**Exit gate:** every covered source has a published staleness bound and an alert when it's breached.

---

## Validation track (V) — runs in parallel, gates M2/M3

| WP | Work | Acceptance |
|---|---|---|
| **V1** | 5–8 discovery interviews ([canvas Appendix A](./value-proposition-canvas.md)), incl. builder/legal-eng probes (Q11–12) | Written scorecard per interview; pain thesis confirmed or killed |
| **V2** | Land **1 design partner** on the live CH-federal API ([one-pager](./platform-api-one-pager.md)) | One real integration + honest build-cost data from them |
| **V3** | Pricing/packaging test (usage + coverage packs + freshness SLA) | A "yes, we'd pay $X for coverage Y at freshness Z" from ≥1 partner |

**Kill criterion:** if V1 (5+ interviews) surfaces no real build-cost pain and no spend around trustworthy primary-law data, **pause M2/M3** and revisit the fork (§4b) before building more.

---

## Sequence summary

1. **Now:** M0 (make search work) **+** start V1 (interviews).
2. **Next:** M1 (coverage diamond) while V1/V2 continue.
3. **Gate:** only start M2/M3 once V shows willingness to pay.
4. **Then:** widen coverage as a crank, keeping M3 (freshness) ahead of breadth.

## Open dependencies / risks

- M0.1 needs the DI service reachable from legal-search-api in-cluster (likely `http://document-service:8090`) + an API key — confirm the k8s service name/port before wiring.
- M1 adapters are the real effort sink; municipal (1.3) is the hardest and the most informative — don't skip it to make the diamond look easy.
- M3 is an *ongoing* cost, not a one-time build — budget it as such before promising SLAs.
