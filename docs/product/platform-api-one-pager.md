# Evidara — Primary Law as an API (design-partner one-pager)

Owner: Founder
Last reviewed: 2026-07-10
Status: **Draft** — a design-partner-facing pitch/spec for the platform fork (see [`value-proposition-canvas.md` §4b/§4c](./value-proposition-canvas.md)). Tags: **[live]** = shipped and callable today; **[roadmap]** = designed, not yet exposed. Do not treat [roadmap] as a commitment.

---

## The one line

**Trustworthy primary law as an API** — canonical text, provenance, in-force status, and a citation graph for DACH legislation and case law, so you don't have to build and maintain ingestion yourself.

## Who this is for

Teams building **legal AI, research, or compliance products** who need primary law *as clean data* and currently face a bad choice:

- **Scrape it yourself** — Fedlex, RIS, Légifrance, Normattiva, and a long tail of cantonal/municipal sources each publish differently; you own parsing, in-force tracking, citation linking, and *continuous freshness* forever.
- **License a black box** — incumbent databases (Swisslex, Weblaw) give you a UI, not structured, provenanced data you can build on.

Evidara is the third option: **one API, provenance-first, built to be cited.**

## What "trustworthy" means here (concretely)

Not a marketing word — it's specific fields and guarantees:

- **Provenance on every document** — `authority`, `jurisdiction`, `trust_tier` (e.g. `authoritative`), `source_origin_kind` (e.g. `official_primary`), and a traceable link to the official source. **[live — modelled in the canonical document.]**
- **In-force status** — `lifecycle_status` (active / superseded / repealed / withdrawn) so you never cite dead law. **[live — modelled; per-source accuracy scales with coverage.]**
- **Citation graph** — documents parsed into `sections`, `citations`, and `citation-targets`, not full-text blobs. **[live — canonical structure + OpenSearch projection.]**
- **Operator-approved ingestion** — sources pass through an approval lifecycle before publish; human-in-the-loop corrections feed back. **[live — platform-control lifecycle; HITL is internal-staging today.]**
- **Freshness SLA** — per-source re-crawl + change detection with a published staleness bound. **[roadmap — the core operational commitment of the platform.]**

## API surface

**Available today [live]** (document-intelligence Document Service, bearer auth):

| Method | Path | Returns |
|---|---|---|
| `GET` | `/v1/documents/{id}` | Full canonical document (sections, citations, metadata) |
| `GET` | `/v1/documents/{id}/lean` | Lean document (IDs + structure, no heavy body) |
| `GET` | `/v1/documents/{id}/text` | Plain text |

Plus **search** over the corpus via legal-search (query + jurisdiction / document-type / language facets). **[live]**

**Proposed for the external product [roadmap]:**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/documents?jurisdiction=&authority=&in_force=&updated_since=` | List / discover with filters |
| `GET` | `/v1/documents/{id}/citations` | Traverse the citation graph (outbound/inbound) |
| `GET` | `/v1/changes?since=` | Freshness feed — what changed, for incremental sync |
| `GET` | `/v1/jurisdictions`, `/v1/authorities` | Coverage introspection (what we cover, at what depth) |
| — | API keys, usage metering, per-plan rate limits | Self-serve onboarding |

> Canonical entity shapes live in [`contracts/`](../../contracts/) (schemas + OpenAPI). The API is contract-first, not invented per-endpoint.

## Coverage — where we are and where we're going

- **Today [live]:** Swiss **federal** law (Fedlex), small curated corpus (internal beta).
- **Addressable now [live]:** the ID model already spans **CH, AT, DE, FR, IT, EU** and drills to **municipal** level (2,169 jurisdictions seeded). Coverage is a matter of ingestion, not re-architecture.
- **Next — the "coverage diamond" [roadmap]:** CH federal → +1 canton → +1 municipality → +1 second country (AT or DE) federal. This proves the ingestion engine generalizes on both the *deep* (structure degradation) and *wide* (new authority/language) axes. See [canvas §4c](./value-proposition-canvas.md).
- **Then:** breadth becomes a crank — coverage packs by jurisdiction, deepening from federal toward cantonal/municipal where demand pulls.

## Commercial shape (sketch, not final)

- **Model:** usage-metered API + **coverage packs** (per jurisdiction/depth) + **freshness SLA** tiers. **[hypothesis — no pricing validated yet.]**
- **Why you'd pay vs. build:** you get citable-quality data across jurisdictions you'd never maintain yourself, kept fresh, under one contract — and you stop owning the worst part (municipal + continuous updates).

## What we want from a design partner

1. **Tell us the real build cost** you're carrying today (which sources, how much effort, what breaks).
2. **One integration** against the live document API on the current CH-federal corpus.
3. **Name the coverage** that would make this a "yes, we'd pay" — which jurisdictions, what depth, what freshness.

## Honest caveats

- Freshness SLA and the discovery/changes/citation-traversal endpoints are **[roadmap]**, not live.
- Coverage today is **narrow** (CH federal). The pitch is the *engine + roadmap*, validated by the diamond — not present-day breadth.
- Pricing is unvalidated. The first design-partner conversation is discovery, not a sale.
