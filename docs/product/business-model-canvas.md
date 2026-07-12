# Business Model Canvas (Osterwalder) — working draft

Owner: Founder / Product
Last reviewed: 2026-07-12
Status: **Draft v0** — the classic 9-block Business Model Canvas, complementing the [Value Proposition Canvas](./value-proposition-canvas.md) (customer/value fit) and the Lean Canvas embedded there (business shape). Same house convention: every claim is tagged **[grounded]** (traceable to the repo/docs today) or **[hypothesis]** (a bet not yet validated by research, revenue, or a design partner). Do not treat hypotheses as commitments.

> **Why a third canvas?** The Value Proposition Canvas answers *does the value fit the customer*; the Lean Canvas is a founder's risk-first sketch. This one — Osterwalder's original — is the *operating* view: the nine things that have to hold together for the business to run, with the back half (Steps 5–9: revenue, resources, activities, partners, cost) made explicit. It exists so we can rank the boxes by fragility and test the load-bearing ones first (see [How to use this](#how-to-use-this-canvas)).

**Which fork is this canvas drawn for?** The founder lean (2026-07-10) is the **platform / "primary-law-as-an-API" fork** ([value-proposition-canvas §4b](./value-proposition-canvas.md), [platform-api-one-pager](./platform-api-one-pager.md)). This canvas is drawn **primarily for that fork**, with the end-product (app) fork sketched as a contrast in [The app-fork canvas](#appendix--the-app-fork-canvas-for-contrast). The two canvases disagree in almost every box — which is itself the strategic content.

---

## The canvas at a glance

| | | |
|---|---|---|
| **⑧ Key Partners**<br>Official data sources (Fedlex, RIS, Légifrance, Normattiva, EUR-Lex, apex courts); runtime (migrating GCP → **fixed-cost Hetzner k8s**; Databricks now opt-in); scraping (Firecrawl); orchestration/HITL (Temporal, Argilla); design partners | **⑦ Key Activities**<br>Per-authority ingestion adapters; **continuous freshness** (re-crawl + change detection + in-force tracking); extraction quality + HITL eval loop; operator approval/curation; **customer discovery now** | **② Value Propositions**<br>Trustworthy **primary law as an API** — canonical text + provenance + in-force status + citation graph, so you don't rebuild ingestion. *App view:* legal search you can cite. | **④ Customer Relationships**<br>Hands-on design-partner co-dev → self-serve API (keys/metering/docs); **freshness SLA = standing contract**; operator curation as trust glue | **① Customer Segments**<br>**Wedge (platform):** legal-AI builders / RegTech-govtech / in-house legal-eng who rebuild ingestion today. **"Come for the app":** P1 legal end users (DACH, DE-first). Internal: operators, reviewers, SRE, agents |
| | **⑥ Key Resources**<br>Provenance/trust data model + canonical/projection architecture; the 2,169-jurisdiction taxonomy (addressability); the **maintained citable corpus** (thin today); per-authority adapters; founder domain+eng | | **③ Channels**<br>*(repo gap)* Direct design-partner outreach (one-pager); developer/API docs + self-serve; legal-tech/RegTech communities; statute-page SEO (app); bar associations | |
| **⑨ Cost Structure** | Fixed: self-hosted Hetzner k8s runtime, founder time, per-jurisdiction legal review. Variable (shrinking by design): ingestion compute, scraping, storage, API serving, HITL labor. **Deliberate move off usage-billed GCP → fixed monthly cost (ADR-0029).** **Dominant cost = continuous freshness.** | | **⑤ Revenue Streams** — *(repo gap)* Usage-metered API + **coverage packs** (jurisdiction × depth) + **freshness-SLA tiers**. App alt: per-seat SaaS / firm licence. Anchor: what they pay *today to do it badly* (below). | |

The rest of the page expands each block. The numbering follows your working order (front half ①–④, then the back half ⑤–⑨ you asked about).

---

## ① Customer Segments

- **Wedge (platform fork):** teams building **legal-AI, research, or compliance products** — plus **in-house legal engineering** and **RegTech/govtech** — who need primary law *as clean data* and currently either scrape it themselves or license a UI-only black box. **[hypothesis — the buyer is not interview-validated; this is the §4b founder bet. Riskiest unknown: will they *pay* for coverage they could scrape? See [one-pager "Who this is for"](./platform-api-one-pager.md).]**
- **"Come for the app" segment:** the **P1 legal end user** — practising lawyer / legal researcher / paralegal, DACH, German-first. The app is the domain-learning and design-partner surface that pulls the platform. **[grounded that P1 exists and is the product's stated audience; the *wedge sub-persona* is undecided — Open decision #1.]**
- **Internal (served by the model, not buyers):** content operators (P2), HITL reviewers (P3), platform/SRE operators (P4), agent/CLI operators (P5). **[grounded — [personas.md](./personas.md).]**

> The single most important unresolved question in this whole canvas: **is the reachable first customer a builder (→ platform) or a firm (→ app)?** Everything downstream forks on it.

## ② Value Propositions

- **Platform:** *"Trustworthy primary law as an API — canonical text, provenance, in-force status, and a citation graph, so you don't build and maintain ingestion yourself."* Concretely: `authority` / `jurisdiction` / `trust_tier` / `source_origin_kind` on every doc, `lifecycle_status` (active/superseded/repealed/withdrawn), a `sections`/`citations`/`citation-targets` graph, operator-approved ingestion. **[live for CH-federal; freshness SLA is roadmap — [one-pager "What trustworthy means"](./platform-api-one-pager.md).]**
- **The compounding promise:** **deep** (federal → cantonal → municipal) × **wide** (≥4 countries) coverage that a builder would never maintain themselves — the moat, not the launch scope. **[roadmap — value-proposition-canvas §4c.]**
- **App:** *"Primary DACH law you can cite — every result traceable to an authoritative, in-force source."* **[grounded capability; the pain thesis behind it is a hypothesis.]**

## ③ Channels

**This is a repo gap — no channel is documented or tested.** Candidates, ranked by fit to the platform fork:

- **Direct design-partner outreach** using the [platform-api-one-pager](./platform-api-one-pager.md) — pitch the engine + roadmap, ask for one integration against the live CH-federal API. **[hypothesis — the intended first motion.]**
- **Developer-led / self-serve** — API docs, keys, usage metering, contract-first OpenAPI as the funnel (matches the P5 agent persona). **[roadmap.]**
- **Legal-tech / RegTech communities**, plus **statute-page content SEO** (an app-fork channel) and **bar-association** reach for the firm segment. **[hypothesis.]**

## ④ Customer Relationships

- **Early:** high-touch **design-partner co-development** — the one-pager explicitly asks partners to name the coverage that turns a "yes we'd pay." **[roadmap — no partner yet.]**
- **At scale:** **self-serve API** (keys, usage metering, per-plan rate limits) — low-touch, developer-owned. **[roadmap — proposed endpoints, not live.]**
- **The relationship's spine is the freshness SLA:** a legal API is a *standing* commitment, not a one-time sale — the ongoing "we keep it current and citable" promise *is* the relationship. **[roadmap — the core operational commitment.]**
- **Trust as glue:** operator-approved, provenance-visible curation is what makes the relationship sticky vs. a raw scrape. **[grounded — control plane.]**

---

## ⑤ Revenue Streams — *how you charge & what they're really paying for*

> Your Step 5 prompt: *what are they paying to solve this badly today?* That's the willingness-to-pay anchor, and we can name it concretely.

**What they pay today (the "badly" baseline):**

- **Builders** pay in **engineering time** — owning parsing, in-force tracking, citation linking, and *continuous freshness* per source, forever. The "Fedlex is JS-heavy / hard to consume" signal (a community MCP connector exists just for this) is repeated evidence this cost is real. **[grounded signal; magnitude unquantified — Appendix A Q11–12 is designed to measure it.]**
- **Firms** already pay for tools: **CASUS CHF 100–145/seat/mo**, or expensive legacy licences (Swisslex, Weblaw/Jusletter, beck-online). That's the seat-price anchor for the app fork. **[grounded — desk research, value-proposition-canvas §4a.]**

**How we'd charge (platform fork, unvalidated):**

| Stream | Shape | Note |
|---|---|---|
| **Usage-metered API** | Per-call / per-volume | The base meter for programmatic consumers |
| **Coverage packs** | Per jurisdiction × depth (federal / cantonal / municipal) | Both the upsell lever *and* the compounding moat — you sell the boring ingestion you did that they didn't |
| **Freshness-SLA tiers** | Staleness bound as a paid guarantee | Turns "trust" into a priced, contractual line |

**App-fork alternative:** per-seat SaaS or firm site-licence. **[all revenue is [hypothesis] — Lane 10 says no pricing/SLA/packaging exists yet; Open decision #4.]**

**Cost- or value-driven?** **Value-driven** — you charge for citable-quality, kept-fresh coverage across jurisdictions the customer would never maintain, not for cheap bytes. The price ceiling is *their* build-and-maintain cost, not our COGS.

## ⑥ Key Resources — *the non-negotiable assets*

- **The provenance/trust data model + canonical-truth/projection architecture.** Clean-room, contract-first, citation-aware. This is the differentiated asset and it's built. **[grounded — architecture.]**
- **The reference taxonomy** — 6 top-level jurisdictions (CH/AT/DE/FR/IT/EU) × real authorities, a recursive `parent_id` tree reaching **2,169 seeded jurisdictions** down to municipal level. This is *addressability* — the map the corpus fills in. **[grounded — `seeds/reference/*.yaml`.]**
- **The maintained, citable corpus itself** — the compounding proprietary asset. **Thin today (~12 CH-federal docs); the gap between 2,169 addressable and ~12 real is the business.** **[grounded — this is the honest weak point.]**
- **Per-authority ingestion adapters** (Fedlex live; RIS/Bundesrecht/Légifrance/Normattiva/EUR-Lex roadmap). **[grounded/roadmap.]**
- **Founder domain + engineering capability** (solo). **[grounded by implication — a real constraint, see Cost & Activities.]**
- **What we do *not* own (and can't cheaply get):** exclusive commentary / analysed case-law rights (the incumbents' actual moat), brand, or capital. **[grounded — §4a "uncomfortable read".]**

## ⑦ Key Activities — *the handful we must do excellently*

> Your Step 5→7 prompt: for a retrieval product it's *ingestion quality + eval loops, not "coding."* This repo agrees.

1. **Per-authority ingestion adapters** — one per source; Fedlex SPARQL is the easy one, municipal (ad-hoc PDF CMSs, no API) is the worst. **[grounded that adapters are per-authority; effort a hypothesis.]**
2. **Continuous freshness** — re-crawl + change detection + in-force tracking across *every* source, forever. **This is the real product, not the first scrape.** **[roadmap — the core operational commitment.]**
3. **Extraction quality + HITL eval/rescore loop** — good enough that human review is *exception-only*, or it can't scale past a solo founder. **[grounded — Temporal + Argilla loop, internal-staging.]**
4. **Operator approval / curation** — quality as a gated feature, not an accident. **[grounded — platform-control lifecycle.]**
5. **Coverage expansion** — prove the "diamond" (CH-federal → +1 canton → +1 municipality → +1 second country) generalizes, *then* crank breadth. **[roadmap — §4c sequencing.]**
6. **Customer discovery — right now.** Until the buyer/willingness-to-pay is validated (Appendix A interviews), *this* is the #1 activity. **[grounded need.]**

## ⑧ Key Partners — *who we don't want to build ourselves*

- **Official data sources** (dependencies more than partners): **Fedlex** (CH), **AT RIS**, **DE Bundesrecht**, **FR Légifrance**, **IT Normattiva/Gazzetta**, **EU EUR-Lex**, plus apex courts per country. Free at source; the value is making them citable. **[grounded — seeded authorities.]**
- **Cloud & runtime — mid-migration:** **GCP** (Cloud Run/Cloud SQL/GCS today) is being **migrated onto a self-hosted Hetzner k8s stack** (NATS JetStream, MinIO/S3, self-hosted Postgres, OpenSearch StatefulSet) via the vendored **MacConfig** platform contract + Argo CD. **Databricks** is reduced to **opt-in** (document-intelligence now runs as a plain pure-Python container). **[grounded — ADR-0029, "self-hosted Hetzner runtime".]**
- **Scraping / ingestion tooling:** **Firecrawl** (one of several acquisition providers, alongside `deterministic_http`, `ris_ogd`, and a proposed `fedlex_sparql`). **[grounded — architecture doc.]**
- **Orchestration & HITL:** **Temporal** (scaled scraping fan-out, retries, approval gates), **Argilla** (review). **GitHub Actions** (some self-hosted ARC runners on Hetzner). **[grounded — personas P3/P5, infra.]**
- **Go-to-market partners (none yet):** **design partners**; potentially the Tier-3 legal-AI apps themselves (as customers, not partners); referral via legal-tech communities. **[hypothesis.]**

## ⑨ Cost Structure — *falls out of ⑥–⑧*

| Type | Items |
|---|---|
| **Fixed** | Self-hosted **Hetzner k8s** cluster runtime; **founder time** (the scarcest input); per-jurisdiction legal/compliance review |
| **Variable** (shrinking by design) | Ingestion compute; scraping (Firecrawl); storage (MinIO / OpenSearch / Delta); API serving; **HITL review labor per document** |

- **A deliberate infra decision reshaped this box:** ADR-0029 migrates Evidara **off usage-billed GCP onto fixed-cost Hetzner** precisely because the project paused (~2026-04-29) while managed services potentially kept billing — the goal is a **predictable monthly cost a solo operator can carry**, converting variable cloud spend into fixed capacity (and self-managed ops burden). **[grounded — ADR-0029.]**
- **The dominant ongoing cost is continuous freshness** — re-crawl/change-detection/in-force maintenance that **scales with coverage**, not the one-off first scrape. Municipal + multilingual + per-source compliance politeness tiers (attribution, rate corridors, retention windows — `compliance_policies.yaml`) are where it gets expensive. **[grounded — §4c hard parts, compliance seeds.]**
- **Cost- or value-driven — the honest split:** the **pricing strategy is value-driven** (charge for citable, kept-fresh coverage, not cheap bytes — resist competing on price). But the **infra strategy is deliberately cost-driven** (fixed-cost Hetzner to survive as a solo operator). Those aren't in tension: keep burn flat *and* price on value — the low fixed cost is what buys the runway to find the value-based buyer. **[grounded stance + ADR-0029.]**

---

## How to use this canvas

Per your method: fill fast, then **treat every box as a hypothesis and rank by "if this is wrong, everything collapses."** Ranked, most-fragile first:

1. **Revenue × Segments — will a builder *pay* for coverage they could scrape themselves?** If no, the platform fork's whole load-bearing wall is gone. **Test first:** Appendix A Q11–12 interviews with builders / legal-eng. *(This is the founder's own stated "riskiest unknown.")*
2. **Segments — is the reachable first customer a builder or a firm?** Picks the fork, and every other box flips with it (see the two canvases). **Test:** who actually takes the call and says yes.
3. **Key Activities/Resources — does the ingestion engine generalize across authorities and down to municipal?** If it doesn't, "deep × wide" is marketing, not a moat. **Test:** build the coverage diamond (§4c) — CH-federal + 1 canton + 1 municipality + 1 second country.
4. **Value Prop — is "trust/citability" the *#1 ranked* pain (vs. cost/speed/coverage)?** **Test:** Appendix A Q6/Q9, unled.
5. **Channels — how does the first design partner even hear about us?** Whole box is a repo gap. **Test:** run the one-pager at 5 real prospects.

Boxes 1–3 are load-bearing; boxes 4–5 are important but recoverable. **Spend the next cycle on 1–3.**

### Then draw a competitor's canvas — the gaps are the strategy

Below is the strongest threat, **Noxtua** (publisher-backed AI: Beck-/MANZ-/Swiss-Noxtua + a cross-border "Europe License" — incumbent premium content + AI + cross-jurisdiction in one product, §4a Tier 2). The point isn't precision; it's **where the two canvases *don't* overlap.**

| Block | Noxtua (inferred) | Evidara (platform fork) | The gap = our opening |
|---|---|---|---|
| **Segments** | Lawyers/firms buying a workspace | *Builders* who assemble their own product | Noxtua sells to the desk; we sell to the people *building for* the desk — a segment it doesn't serve |
| **Value Prop** | AI answers over **exclusive commentary + case law** | **Structured primary-law data + provenance** you build on | It sells conclusions; we sell **citable inputs**. Different layer of the stack |
| **Key Resources** | **Exclusive content rights** (Beck/MANZ) — the real moat | Provenance model + maintained coverage; **no exclusive content** | Their moat is content we can't get; our moat must be **the data layer + coverage they don't expose** |
| **Revenue** | Premium per-seat workspace licence | Usage + coverage packs + freshness SLA | We monetize the **plumbing** they'd have to buy or rebuild |
| **Channels** | Publisher brand + sales force | Developer/API + design partners | We can move **developer-led** where they move enterprise-sales-led |

**Reading the gaps:** Evidara does **not** win by out-Noxtua-ing Noxtua at the lawyer's desk — it has no content moat there (§4a). It wins, *if it wins*, by being the **structured, provenanced primary-law data layer** that the whole Tier-2/Tier-3 field (Noxtua included) either rebuilds badly or licenses as a black box. The strategy lives in the columns that don't line up: **buyer (builder not lawyer), layer (data not workspace), and channel (developer not sales).** That is the platform fork stated as a wedge against the incumbent — and it's exactly the set of bets Ranking §1–3 above tells us to test before committing.

---

## Related

- [Value Proposition Canvas & Lean Canvas](./value-proposition-canvas.md) — customer/value fit, competitive landscape (§4a), strategic fork (§4b), coverage strategy (§4c), and the customer-discovery interview script (Appendix A).
- [Personas](./personas.md) — P1–P5, the wedge question.
- [Platform API one-pager](./platform-api-one-pager.md) — the design-partner pitch this canvas is drawn for.
- [GA criteria](./ga-criteria.md) — scope lanes and anti-scope.

## Appendix — the app-fork canvas (for contrast)

If discovery says the reachable customer is a **firm, not a builder**, the canvas flips. The deltas that matter:

- **① Segments:** P1 practising lawyer / researcher / paralegal (pick the wedge), DACH DE-first — *not* builders.
- **② Value Prop:** "legal search you can cite," a finished UI — *not* an API.
- **③ Channels:** statute-page SEO, bar associations, legal-tech press — *not* developer docs.
- **④ Relationships:** self-serve SaaS + community — *not* design-partner co-dev + SLA.
- **⑤ Revenue:** per-seat (anchor CHF ~100–145, CASUS) or firm licence — *not* usage/coverage packs.
- **⑥–⑨ (back half) barely change:** you still need the same ingestion, freshness, corpus, and infra — which is *why* "come for the app, stay for the API" is coherent: the expensive back half is shared, only the front half re-skins. **[hypothesis — the sequencing bet in §4b.]**
