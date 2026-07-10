# Value proposition & business canvas (working draft)

Owner: Founder / Product
Last reviewed: 2026-07-08
Status: **Draft v0** — a shared "what/why/how/for-whom" artifact to align the team. Follows the house convention from [`personas.md`](./personas.md) and [`ga-criteria.md`](./ga-criteria.md): every claim is tagged **[grounded]** (traceable to the repo/docs today) or **[hypothesis]** (a bet not yet validated by research, revenue, or a design partner). Do not treat hypotheses as commitments.

> How to use this page: read the Golden Circle first for the one-paragraph "why", then the Value Proposition Canvas for the wedge customer, then the Lean Canvas for the business shape. Everything in the **Open decisions** and **Assumptions ledger** at the bottom is what we still have to answer *together* — those are the gaps, stated honestly.

## Working thesis (locked 2026-07-10 — revisit if a design partner says otherwise)

- **What:** Trustworthy **primary law as an API** — canonical text + provenance + in-force status + citation graph. *(Platform fork, §4b.)*
- **Positioning:** **Specialized to law** (not general document intelligence). Specialized product, general-enough engine. *(High confidence, §4b Axis 1.)*
- **Ambition:** **deep** (federal → cantonal → municipal) × **wide** (≥4 countries) — as the compounding **moat and vision**, sequenced via the coverage diamond, *not* the launch scope. *(§4c.)*
- **Buyer:** legal-AI builders / in-house legal-eng / RegTech-govtech who currently rebuild ingestion themselves. *(hypothesis — validate with Appendix A Q11–12.)*
- **Riskiest unknown:** will a builder *pay* for coverage they could scrape themselves? Proving we *can* build it (diamond) ≠ proving they'll *buy* it (interviews). Do both.
- **Execution:** see [`work-packages-milestones.md`](./work-packages-milestones.md). Design-partner pitch: [`platform-api-one-pager.md`](./platform-api-one-pager.md).

---

## 1. Golden Circle — the one-screen answer

**WHY (purpose).** Legal professionals in German-speaking Europe cannot fully trust general search or generic AI for primary law: results are unsourced, stale, or hallucinated, and nothing tells them *where a statement came from or whether it is still in force*. Evidara exists to make **primary legal and regulatory content trustworthy enough to cite** — every answer traceable to an authoritative source. **[grounded — the repo's whole design separates "canonical truth" from "serving projections" and centres a "trust loop"; see README, [`ga-criteria.md` Lane 6](./ga-criteria.md).]**

**HOW (the approach that's different).**
- **Provenance-first, not scrape-and-guess.** Sources are modelled with authority, jurisdiction, trust tier, and official/primary flags; runs are approved by an operator before content is published. **[grounded — `platform-control` source lifecycle, `trust_tier: authoritative`, `source_origin_kind: official_primary`.]**
- **Canonical truth vs. serving projection.** A document is processed once into a canonical form (sections, citations, metadata) and *projected* into search — so search is a rebuildable view, not the system of record. **[grounded — `document-intelligence` → `legal-search` projection architecture.]**
- **Citation-aware.** Documents are parsed into a citation graph (`sections`, `citations`, `citation-targets`), not just full-text blobs. **[grounded — legal-search OpenSearch indices.]**
- **Human-in-the-loop quality.** Extraction corrections route through a review/rescore loop. **[grounded, but internal-staging only today — persona P3, HITL loop.]**

**WHAT (the product today).** A **legal search + document-detail experience** over a curated corpus of DACH primary law, backed by an **operator control plane** for onboarding and approving sources. Today: **~12 Swiss federal laws, German UI, CH-first, internal beta.** **[grounded — [`ga-criteria.md` Lane 1](./ga-criteria.md), [`personas.md` P1](./personas.md).]**

**FOR WHOM (the wedge).** The audience the product is *for* is the **legal end user (P1)**. Which of the three sub-personas — practising lawyer, legal researcher, or paralegal — is *the wedge* is **still undecided** and is the single most important open question below. **[hypothesis — sub-segmentation not interview-validated; personas.md is explicit about this.]**

---

## 2. Value Proposition Canvas (Osterwalder)

Scoped to the **wedge persona candidate: the practising lawyer / in-house counsel** — chosen as the default wedge here *for the sake of a concrete canvas*, not because it's decided. Swap this panel per the wedge decision (Open decision #1).

### Customer profile

**Customer jobs**
- Find the *controlling* provision, article, or precedent for a specific matter — fast. **[grounded — personas P1 "practising lawyer".]**
- Confirm a provision is *currently in force* (not superseded/repealed) before relying on it. **[grounded — lifecycle_status active/superseded/repealed/withdrawn is modelled.]**
- Drop a citation into a brief/memo with a source pointer a partner or court will accept. **[hypothesis — export/copy-citation is on the "Later expansion" list, not shipped.]**
- Do all of the above in the working language (DE now; FR/IT matter for a Swiss practice). **[grounded — DE today, FR/IT planned, ADR-0013.]**

**Pains**
- General web/AI search gives **unsourced or hallucinated** legal statements — unusable for anything citable. **[hypothesis — the founding pain thesis; needs design-partner confirmation.]**
- Incumbent legal databases are **expensive, dated in UX, and slow to navigate** to the exact section. **[hypothesis — competitive claim, not yet substantiated in repo.]**
- Hard to tell **provenance and currency** at a glance — is this the official text, and is it the version in force?
- Cross-referencing between statutes/citations is manual.

**Gains**
- Top-3 result is the right citation; trust the detail view enough to cite it.
- Section-level navigation and citation-aware jumps.
- A visible **provenance chain** on every document (authority, source, version, run).
- Stable canonical citation that survives reprocessing.

### Value map

**Products & services**
- Faceted legal search (jurisdiction / document type / language) with highlighted snippets. **[grounded.]**
- Document detail with `content` / `sections` / `citations` / `details` tabs. **[grounded.]**
- Operator-curated, approval-gated corpus (quality is a feature, not an accident). **[grounded — control plane.]**

**Pain relievers**
- Provenance + trust-tier model → answers a lawyer can *source*. **[grounded — the differentiator.]**
- `lifecycle_status` → currency signal (in force vs. superseded/repealed). **[grounded in data model; surfacing in UI = verify.]**
- Canonical-truth/projection split → citations stay stable and search is rebuildable. **[grounded.]**

**Gain creators**
- Citation graph enables "what does this article point to / who cites it". **[grounded in indices; UX depth = GA decision, Lane 2.]**
- Clean, fast, modern UI vs. legacy incumbents. **[hypothesis — a positioning bet.]**

**Fit statement (draft):** *Evidara turns primary DACH law into search a lawyer can cite, by making every result traceable to an authoritative, in-force source.* — Validate this sentence with 5–8 P1 interviews before it becomes marketing copy.

---

## 3. Lean Canvas (Maurya)

| Block | Working content | Tag |
|---|---|---|
| **Problem** | (1) Primary law is hard to search *and trust* — unsourced results, unclear currency. (2) Incumbents costly/dated. (3) Generic AI hallucinates law. | [hypothesis] core theses |
| **Customer segments** | Wedge: **P1 legal end user** (lawyer / researcher / paralegal, DACH, DE-first). Early adopter: **[decide]**. Also internal: content operators, reviewers, SRE (personas P2–P5). | [grounded] personas; wedge [hypothesis] |
| **Unique value proposition** | "Primary DACH law you can cite — every result traceable to an authoritative, in-force source." | [hypothesis] |
| **Solution** | Provenance-first ingestion + approval; canonical processing (sections/citations); citation-aware search; HITL quality loop. | [grounded] |
| **Unfair advantage** | Rigorous provenance/trust data model + clean-room canonical architecture + operator curation discipline. (Not yet: proprietary corpus rights, brand, or a design-partner moat.) | [grounded arch]; moat [hypothesis] |
| **Channels** | **[gap — no documentation in repo]** Candidates: direct design-partner outreach to CH firms, bar-association/legal-tech communities, content SEO on statute pages. | [hypothesis] |
| **Revenue streams** | **[gap — Lane 10 says no pricing/SLA/packaging exists]** Candidates: per-seat SaaS, firm licence, API/agent access tier. | [hypothesis] |
| **Cost structure** | Content acquisition & processing (compute), self-hosted runtime (Hetzner k3s: NATS/MinIO/OpenSearch/Trino/Postgres), infra ops, legal/compliance review per jurisdiction. | [grounded — infra] |
| **Key metrics** | **[decide]** Candidates: top-3 hit rate for wedge queries; % results with visible provenance; corpus coverage per jurisdiction; time-to-citation; design-partner weekly active use. | [hypothesis] |

---

## 4. Positioning statement (Moore template — draft)

> For **practising lawyers and legal researchers in German-speaking Europe** who **need primary law they can trust and cite**, **Evidara** is a **legal search platform** that **makes every result traceable to an authoritative, in-force source** — unlike **generic search/AI (unsourced) and legacy legal databases (costly, dated)**. **[hypothesis — every bracketed claim is a bet to validate.]**

---

## 4a. Competitive landscape (desk research, 2026-07-08)

The DACH legal-research market is **not greenfield** — it's crowded and moving fast. Three tiers:

**Tier 1 — Content incumbents (moat = exclusive commentary + case law).**
- **Swisslex** — Switzerland's comprehensive DB since 1986: ~760k judgments, ~570 commentary volumes, 85 journals, 80+ publishing partners; now adding a Swiss-hosted local AI model. [swisslex.ch]
- **Weblaw / Lawsearch** — owns *Jusletter* (Switzerland's largest legal journal), Federal Court push, AI search. [lawsearch.weblaw.ch]
- **C.H.BECK / beck-online** (DE market leader, 60M+ docs), **MANZ** (AT), **Helbing Lichtenhahn** (CH — *Basler Kommentar*).
- **Their moat is content Evidara does not have and cannot easily get:** exclusive rights to commentaries, journals, and analysed case law. That's what lawyers actually pay for.

**Tier 2 — Publisher-backed AI (incumbent content + AI, the strongest threat).**
- **Noxtua** — exclusive Legal-AI-Workspace partnerships as **Beck-Noxtua / MANZ-Noxtua / Swiss-Noxtua**, plus a cross-border **"Europe License"** for DACH. This is *incumbent premium content + AI + cross-jurisdiction* in one product. [noxtua.com]

**Tier 3 — AI-native startups (crowded; closest to Evidara's surface).**
- **CASUS** (CH) — Word plug-in + web, 660k CH rulings, contract review + research + agent chat, CH/EU hosting, **CHF 100–145/seat/mo**. [getcasus.com]
- **DeepLegal / DeepLaw** (DeepCloud) — official CH sources back to 1954, "exclusively official, verifiable, citable." [deepcloud.swiss]
- **Legislator** — synthesises ~21M CH court decisions + legislation + live web. [legislator.ch]
- Also: Jurizzi, Omnilex, Legalfly, and global entrants (Harvey).

**Tier 0 — Free official.** **Fedlex** — the official federal law source (SR/AS/BBl, DE/FR/IT, SPARQL endpoint). **Free.** No commentary or case-law analysis, and hard to consume programmatically (JS-heavy — note a "Fedlex Connector MCP for Claude" exists precisely because of this).

**The uncomfortable read:** Evidara today indexes **free primary law (Fedlex)** — which is (a) free at the source, (b) already indexed by every Tier-2/3 player, and (c) *without* the paid commentary that is the incumbents' moat. **"Yet another Swiss legal search app over Fedlex" is the most contested square on the board.** The differentiation has to come from somewhere other than "we also have the primary law." See §4b.

## 4b. Strategic identity — product vs platform, law vs general

Two axes the founder asked to settle. Honest, opinionated read (still bets, but evidence-backed):

**Axis 1 — Specialized to law, or general document intelligence?**
> **Recommendation: stay specialized to law. High confidence.**
Evidara's entire differentiated asset — authorities, jurisdictions, `lifecycle_status` (in-force), the citation graph, provenance/trust tiers — is *law-specific*. A general "document intelligence for any document" drops you into a commoditized fight with Azure/Google Document AI, Unstructured, LlamaParse — capital-heavy, undifferentiated. **Generalizing throws away the only moat.** Keep the *architecture* reusable (it already is) but keep the *positioning* narrow: "specialized product, general-enough engine."

**Axis 2 — End product, or platform/infrastructure?** *(This is the real fork — and the competition tilts it.)*
- **As an end product**, you walk into Tier 1–3 (well-funded AI-natives + publisher-backed AI with exclusive content) **without a content moat.** Free primary law alone won't win. An end-product path is only viable with a *sharp wedge the field underserves* — a specific workflow, jurisdiction niche, or trust/provenance experience nobody else nails.
- **As a platform/infrastructure play** — *"trustworthy primary-law-as-an-API: canonical text + provenance + in-force status + citation graph"* — you'd sell to the very Tier-3 apps and in-house legal-eng teams who **currently rebuild ingestion themselves** (the Fedlex-is-hard-to-consume signal is real and repeated). This aligns with what Evidara has *actually built* (contracts-first, canonical/projection split, the P5 agent/CLI persona, clean component boundaries). More defensible for a technical solo founder; **but** fewer buyers, longer sales, and you must be genuinely better/cheaper than "they build it once themselves."

> **Recommendation: decide by who your *reachable* first customer is.**
> - If you can get **lawyers/firms** to talk and pay → **end product**, but you must name a wedge that isn't "Fedlex search" (see interviews).
> - If your reachable early adopters are **legal-AI builders / in-house legal engineering** → **platform/API**, leaning into provenance + citation graph as the thing nobody wants to rebuild.
> A common path: **come for the app, stay for the API** — start as a narrow end product to learn the domain and win design partners, architect the platform underneath (you already have), expose it once the app has pulled real usage. But if you have *no* sales motion and are infra-minded, platform-first is legitimate.

**What this rules out:** "general document intelligence platform for everyone" — that's the widest, least-defensible box and the current README tagline drifts toward it. Narrow the story.

**Founder lean (2026-07-10):** toward the **platform/infrastructure** fork — *"trustworthy primary-law-as-an-API"* — combined with an explicit ambition to go **deep (down to municipalities) and wide (≥4 countries).** This is a legitimate direction that matches what's built; the coverage strategy and its risks are captured in §4c. **[direction — a founder bet, not yet validated by a paying builder.]**

## 4c. Coverage strategy — deep × wide (the platform moat)

The founder's ambition: go **deep** (federal → cantonal → **municipal**) and **wide** (**≥4 countries**). Honest read below.

**The model already supports this — coverage doesn't exist yet.** The reference seeds already address deep × wide:
- **Wide:** 6 top-level jurisdictions seeded — **CH, AT, DE, FR, IT, EU** — each with real authorities (`auth_at_ris`, `auth_de_bundesrecht`, `auth_fr_legifrance`, `auth_it_normattiva`/`auth_it_gazzetta`, `auth_eu_eurlex`, plus apex courts per country). **[grounded — `seeds/reference/{jurisdictions,authorities}.yaml`.]**
- **Deep:** the jurisdiction tree is recursive (`parent_id`) and **already reaches municipal level** — Swiss municipalities are generated BFS-keyed (`jur_ch_gemeinde_N`, `scripts/generate_ch_municipality_seeds.py`). **[grounded — 2,169 jurisdictions in seed.]**
- **The gap:** ~2,169 addressable jurisdictions vs. **~12 real documents.** The taxonomy is *addressability, not coverage.* Filling that gap **is the business.** **[grounded — corpus is CH-federal only today.]**

**Why deep × wide is the right *moat*, wrong *launch scope*.** The reason a legal-AI builder pays the API rather than scraping is that Evidara did the boring, heterogeneous, **continuously-maintained** ingestion they'd never cover themselves. That compounds — each source made citable is one a competitor must also do. But breadth you can't *vouch for* hurts the "trust enough to cite" promise, and shipping it all at once is how a solo founder drowns. So: deep × wide is the **vision**, not the v1.

**What deep × wide actually commits you to (the hard parts):**
1. **One ingestion adapter per authority.** Fedlex SPARQL is the *easy* one; AT RIS, DE Bundesrecht, FR Légifrance, IT Normattiva each differ; **municipal law is the worst** — PDFs on ad-hoc CMSs, no API, no structure. **[hypothesis on effort; grounded that adapters are per-authority.]**
2. **Freshness as a standing operational commitment.** A stale legal API is worthless → continuous re-crawl + change detection + in-force tracking across *every* source, forever. This is the real cost, not the first scrape.
3. **Trust at scale.** The HITL loop (P3) can't scale to thousands of municipal docs solo — extraction must be good enough that human review is *exception-only*.
4. **Multilingual + multi-legal-system.** DE/FR/IT/EN, with citation parsing and in-force logic differing per country.

**Recommended sequencing — prove the machine on a "diamond," then crank coverage:**
> Prove the ingestion engine *generalizes* on the two hardest axes with ~4 sources before pouring in breadth:
> - **CH federal** (have) → **+1 canton** (e.g. Zürich) → **+1 municipality** (e.g. city of Zürich) — the **deep** proof: does trust/provenance survive as structure degrades from Fedlex-clean to municipal-messy?
> - **+1 second country at federal level** (AT RIS or DE Bundesrecht) — the **wide** proof: does the authority/jurisdiction/language abstraction really plug in?
> If provenance + in-force + citation graph hold across that diamond, deep × wide is de-risked *and* you have a live API demo no Tier-3 builder can wave away. Coverage then becomes a crank you turn.

**Consequences to accept consciously:**
- **Re-scopes GA.** This reverses two [`ga-criteria.md`](./ga-criteria.md) anti-scope decisions — *cantonal coverage* and *public API* were both deferred. Reopening them is a real GA redefinition, not a tweak.
- **Shifts buyer & pricing.** Buyer → legal-AI builders / in-house legal-eng / RegTech-govtech. Pricing → usage + **coverage packs** + freshness SLA; coverage is both the upsell lever and the compounding moat.

## 5. Open decisions (we close these together)

These extend the six in [`ga-criteria.md`](./ga-criteria.md) with the commercial/value ones that page deliberately left out:

1. **Wedge persona** — lawyer, researcher, or paralegal as the *first* target? (Drives everything below.)
2. **Beachhead jurisdiction** — CH-only, or CH + one peer (AT/DE) at first external launch? (Lane 1.)
3. **The core pain thesis** — is "can't trust/cite general search+AI" the real, ranked #1 pain for the wedge? (Needs interviews.)
4. **Willingness to pay & model** — per-seat SaaS vs. firm licence vs. API tier; anchor price? (Lane 10 gap.)
5. **Competitive frame** — who do we actually displace (Swisslex/Weblaw/Fedlex-direct/ChatGPT), and on what axis do we win? (Not in repo.)
6. **Moat** — what compounds over time (corpus rights, citation graph quality, operator tooling, brand)?
7. **Channel** — how does the first design partner hear about us and say yes?
8. **Key metric** — the single number that tells us the wedge is getting value.

---

## 6. Assumptions ledger (what's real vs. what's a bet)

**Grounded (traceable to repo/docs today)**
- Product shape: legal search + document detail + operator control plane. [README, personas, ga-criteria]
- Corpus today: ~12 Swiss federal laws, CH-first, German UI, internal beta. [ga-criteria Lane 1]
- Differentiator *capability*: provenance/trust model, canonical/projection split, citation graph, HITL loop. [architecture]
- Personas P1–P5 named and grounded in engineering surfaces. [personas.md]

**Hypotheses (not yet validated — the risky bets)**
- That the wedge pain is trust/citability specifically (vs. cost, speed, or coverage).
- That the practising lawyer (vs. researcher/paralegal) is the right first target.
- Any competitive, pricing, channel, or market-size claim — **none exist in the repo yet.**
- That a small (12-doc) corpus is tolerable to an early-access wedge user. [personas open question]

**Explicit non-goals for first GA** (from [`ga-criteria.md` Anti-scope](./ga-criteria.md)): semantic/vector search, per-language analyzers, cantonal coverage, design-system consolidation, public agent/MCP API (unless flipped in).

---

## 7. Next steps (proposed)

1. **Name the wedge** (Open decision #1) — unblocks the rest of the canvas.
2. **5–8 discovery interviews** with the candidate wedge to confirm/kill the pain thesis (#3) and pricing appetite (#4). [personas.md already asks for this.]
3. Fill the three repo gaps this canvas exposes: **competition**, **pricing/packaging** (Lane 10), **channel**.
4. **If pursuing the platform fork (§4b founder lean):** build the **coverage diamond** (§4c) — CH federal + 1 canton + 1 municipality + 1 second-country federal — as the API's proof-of-generalization, and validate it with the builder/legal-eng interview probes (Appendix A, Q11–12).
5. Promote this doc from **Draft v0 → shared canonical** once the wedge is named and the pain thesis has at least one design partner behind it.

---

## Appendix A — Customer-discovery interview script

Purpose: **kill or confirm the pain thesis (#3) and the wedge (#1)** before building more. Method follows *The Mom Test* (Rob Fitzgerald): ask about their **past and present behaviour**, never pitch, never ask "would you use X." Every question below is designed so a polite person *can't* flatter you into a false positive.

**Who to talk to (5–8 people, mixed):** 2–3 practising lawyers (in-house counsel or firm associate/partner), 2 legal researchers (academic / librarian / knowledge manager), 1–2 paralegals/junior associates, and — if pursuing the platform fork — 1–2 legal-AI builders or in-house legal-engineering people.

**Rules of the room**
- Talk about *their* life, not your idea. Do not describe Evidara until the very end (and only if they ask).
- Dig into specifics and **money/time already spent** — that's the only signal that separates a real pain from a nice-to-have.
- Shut up and listen. Aim for them talking 80% of the time.
- No feature requests taken at face value — ask *why* they want it.

**Warm-up (context, 5 min)**
1. Walk me through your role — what kind of legal questions land on your desk in a normal week?
2. Last time you had to find *the exact provision or precedent* that controls a matter — tell me about that. What were you actually working on?

**Behaviour & current workflow (the core, 15 min)**
3. Where did you look first? Then where? (Let them enumerate: Fedlex, Swisslex, Google, a colleague, ChatGPT, a physical commentary…)
4. Which tools do you *pay* for today, and who signs off on that spend? (Reveals budget + buyer.)
5. Walk me through the last time that search went *badly*. What broke — coverage, trust, speed, language, something else?
6. When you used ChatGPT / general AI for a legal question, what happened? Did you use the output, or did you have to go verify it? How? (Probes the trust/citability thesis without leading.)
7. Before you put a citation into a brief or memo, what do you do to be sure it's *still in force*? How long does that take?
8. How much time in a week goes to this "find it and trust it" loop? Roughly what would you say that costs?

**Magnitude & priority (5 min)**
9. Of everything we've talked about, what's the single most frustrating part? (Let them rank — don't rank for them.)
10. Have you ever tried to fix this — bought a tool, built a workaround, asked someone? What happened to that attempt? (No prior attempt = probably not a top-3 pain.)

**Platform-fork probes (only for builders / legal-eng)**
11. Have you ever needed primary law *as data* — ingested Fedlex/an official source into your own system? Tell me about that build.
12. What did you have to handle yourself — parsing, in-force status, citation links, updates? How much effort was that, and would you rather not have owned it?

**Close (2 min)**
13. Who else should I talk to about this? (Referral = the interview went well.)
14. Is it OK if I come back to you when I have something to show? (Soft commitment test.)

**Scoring afterward (per interview, write it down immediately)**
- Did they describe a **specific, recent, painful** episode — or speak in generalities? (Specific = signal.)
- Is there **money or real time** already being spent on this? (Yes = real market.)
- Did *they* rank trust/citability #1, or did I have to lead them there? (Unled = the thesis holds.)
- Which sub-persona was this, and did their #1 pain match the others in that group? (Convergence = wedge candidate.)
- **Kill criterion:** if 5+ interviews surface no recent painful episode and no existing spend around trust/citability, the founding pain thesis is wrong — pivot the wedge before building.
