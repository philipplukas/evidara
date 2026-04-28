# Demo script (skeleton)

Owner: TBD (presenter)
Last reviewed: 2026-04-28
Status: **Skeleton — content TBD by presenter.** Engineering scaffolding is in place; the actual narrative copy, query selection, and deep-dive document choices belong to the demo presenter, not Claude.

This file exists so the [demo-queries smoke spec](https://github.com/philipplukas/evidara/blob/main/legal-search/frontend/e2e/demo-queries.spec.ts) and the [detail-view audit](detail-view-audit.md) have a single source of truth to bind to. Fill in `TBD` blocks before T-7.

## Demo target

| Property | Value |
|---|---|
| Target state | Investor / strategic / prospect demo |
| Earliest date | TBD (≤ 2 weeks from 2026-04-28) |
| Audience | Mixed — see [Mixed-audience framing](#mixed-audience-framing) |
| Environment | Prod (https://… — fill in) |
| Backup | Recorded webm — see [Failover plan](failover.md) |

## The corpus we are demoing

12 Swiss federal laws ([`internal-beta-user-flow-evidence.md:23`](../runbooks/internal-beta-user-flow-evidence.md)). All in German. No court decisions, no commentary, no other countries. **Do not query for things outside this set during the demo** — every query must be grounded in this corpus.

| Short | Doc ID | SR | Full title |
|---|---|---|---|
| BV | `doc_6vfta1cd5xy642g7eb59j8wkfm` | SR 101 | Federal Constitution of the Swiss Confederation |
| OR | `doc_67b9202dsxm52sa36dsfvcm6bt` | SR 220 | Code of Obligations |
| ZPO | `doc_20djzpnf2yytwg9k74zyzjdeta` | SR 272 | Civil Procedure Code |
| FADP | `doc_2em3ky37mw9tm7hxh5nkw0zkh7` | SR 235.1 | Federal Act on Data Protection |
| ZGB | `doc_2adkyv1qccx2pg3mqa7d233s0y` | SR 210 | Swiss Civil Code |
| StGB | `doc_30hr7xpm9ptmmanpbydwpxdv61` | SR 311.0 | Swiss Criminal Code |
| StPO | `doc_4n4nh4khmzfxh3hdshpvw6x4mp` | SR 312.0 | Criminal Procedure Code |
| SchKG | `doc_6mej0nyg3qfenw0zbdmhtq6cmn` | SR 281.1 | Debt Enforcement and Bankruptcy Act |
| VwVG | `doc_4pqxtsmegg44t5zg3es8d27b4v` | SR 172.021 | Federal Act on Administrative Procedure |
| BGG | `doc_1f0vr4pdkn9havmnws60mb9n6y` | SR 173.110 | Federal Supreme Court Act |
| IPRG | `doc_3vyh663grb4kwyb96x4sd8xb1f` | SR 291 | Federal Act on Private International Law |
| KG | `doc_1jyt8vad5ed2p294t31ctj53dw` | SR 251 | Cartel Act |

## Rehearsed queries

The hero query is **already wired in the frontend** as the default ([`HomeClient.tsx`](../../legal-search/frontend/src/app/HomeClient.tsx)):

```
Art. 754 OR Verantwortlichkeit
```

This hits OR (Code of Obligations) Art. 754 — board-member liability. Strong demo query: it sounds like something a real Swiss commercial lawyer would type, the result is a famous article, and the title is recognizable.

Pick **4–7 backup queries**. Constraints:

- Must return at least one of the 12 corpus docs in top 3.
- Should look natural to a German-speaking Swiss lawyer (use SR numbers, German terms, article numbers).
- Avoid queries that exercise unfinished features (no semantic queries, no citation-pivot pivots, no cross-jurisdiction comparison).

Suggested seed list (TBD: the presenter picks 4–7):

| Query | Likely top-1 | Why it's a good demo query |
|---|---|---|
| `SR 220` | OR | Direct citation lookup; demonstrates SR-number recognition |
| `Datenschutzgesetz` | FADP | Topical query; shows facet population |
| `Art. 28 ZGB Persönlichkeitsverletzung` | ZGB | Specific article; rich contentHtml in the body |
| `Bundesgerichtsgesetz` | BGG | Long German compound; shows tokenizer handles it |
| `Art. 1 BV` | BV | Constitutional opener; works as a clean opener |
| `Cartel Act` | KG | English query against German corpus — shows multilingual matching (or fails honestly) |
| `IPRG` | IPRG | Acronym lookup; demonstrates abbreviation handling |

Pin the final list in this table:

| # | Query | Expected top-1 doc id | Expected snippet contains | Notes |
|---|---|---|---|---|
| 1 | `Art. 754 OR Verantwortlichkeit` | `doc_67b9202dsxm52sa36dsfvcm6bt` | `Verantwortlichkeit` | Hero — already the default in `HomeClient.tsx` |
| 2 | _TBD_ | _TBD_ | _TBD_ |  |
| 3 | _TBD_ | _TBD_ | _TBD_ |  |
| 4 | _TBD_ | _TBD_ | _TBD_ |  |
| 5 | _TBD_ | _TBD_ | _TBD_ |  |

Once filled in, mirror this table into [`demo-queries.spec.ts`](https://github.com/philipplukas/evidara/blob/main/legal-search/frontend/e2e/demo-queries.spec.ts) so the smoke pins the same expectations.

## Deep-dive document

Pick ONE document the demo will open in detail. The audit ([detail-view-audit.md](detail-view-audit.md)) for this document must be 100% green before T-7.

| Audience | Suggested deep-dive | Why |
|---|---|---|
| Investor | OR Art. 754 (board liability) | Recognisable, commercial, story-friendly ("a board director sued for breach…") |
| Strategic partner | FADP (data protection) | Connects to enterprise concerns; lots of structure for the structure tab |
| Prospect / lawyer | Whatever they would actually search for | If the meeting is with a named lawyer, brief them ahead and pick from their topic |

Final pick: **TBD**.

## 3-minute variant

Tight version. Use when the slot collapses or as a sanity opener.

1. **0:00 — Open** (15s): one sentence on what Evidara is. _TBD copy._
2. **0:15 — Search** (30s): type the hero query; let results render; point at one snippet.
3. **0:45 — Detail** (60s): click top result; walk the header (title / metadata strip / language); switch to the `details` tab; scroll one screen of body.
4. **1:45 — Filter** (30s): apply one jurisdiction or type filter; show the result list narrowing.
5. **2:15 — Close** (45s): one sentence on what's next. _TBD copy._

## 10-minute variant

Used when there is room. Same opening; expanded middle.

1. **0:00 — Open** (1 min): mission + corpus context. _TBD copy._
2. **1:00 — Search** (2 min): hero query + 2 backups; point at facets and the `language` chip.
3. **3:00 — Detail deep-dive** (4 min): walk the header → tabs → body. Pause on metadata; explicitly mention "this is sourced from Fedlex" (see audit recommendation 1 — there is no clickable Fedlex URL today; cover with talk track).
4. **7:00 — Cross-surface** (1 min): click the control-panel link in the header; show the admin shell briefly so the audience sees the operational backplane exists. Return via the handoff link.
5. **8:00 — Architecture / contracts moment** (90s): pull up the architecture mermaid in [`docs/architecture/system-context.md:67`](../architecture/system-context.md) on a second tab _or_ slide. One sentence on the pipeline.
6. **9:30 — Close** (30s): "what's next" — _TBD copy._

## Mixed-audience framing

Pre-pend a single intro slide tailored to the room. The product flow underneath is the same.

| Audience | Intro angle | One-line message |
|---|---|---|
| Investor | Pipeline + corpus lever | _TBD: "The product runs end-to-end. Scaling means content acquisition, which is a known process."_ |
| Strategic partner | Contracts + embeddability | _TBD: "OpenAPI-first, event-driven, deterministic; integratable today."_ |
| Prospect / lawyer | Skip the framing | Open with the hero query and let the result speak. |

If the room contains multiple types, lead with the most decision-making seat and treat the others as secondary.

## "If X flakes, switch to Y" branches

| If this fails | Switch to | Talk track |
|---|---|---|
| Hero query returns nothing | Backup query 2 (TBD) | "Let me try a different angle…" — never apologize on stage |
| Detail page hangs > 5s | Recorded webm ([failover.md](failover.md)) | Talk over the recording; do not announce the failover |
| Cross-surface link blank | Skip cross-surface section | Roll directly to architecture moment |
| Filters don't update | Skip the filter step in the 3-min variant | Compress to "and you can narrow these" |

## Pre-demo checklist

- [ ] All TBD blocks filled in
- [ ] [Detail-view audit](detail-view-audit.md) green for the deep-dive document
- [ ] [`demo-queries.spec.ts`](https://github.com/philipplukas/evidara/blob/main/legal-search/frontend/e2e/demo-queries.spec.ts) updated to match the final query table and passing on prod
- [ ] [Failover recording](failover.md) captured and playable on the presentation laptop
- [ ] One full T-7 dry run on prod with stopwatch
- [ ] T-1 hour smoke run

## What this script does NOT cover

- Pricing, packaging, contracts (different conversation)
- Multi-jurisdiction story (not in the corpus — do not promise AT/DE/FR/IT)
- Citation-aware search, semantic search (not shipped)
- HITL review loop (staging only, not productized)
