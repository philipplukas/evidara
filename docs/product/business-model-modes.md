# Business Model Canvas — three modes (money / career / open source)

Owner: Founder
Last reviewed: 2026-07-12
Status: **Draft v0** — a companion to [`business-model-canvas.md`](./business-model-canvas.md). Where that page draws Evidara's canvas as a *commercial* business, this page explains the underlying theory and shows how the *same canvas* describes three different goals: revenue, career evidence, and open-source contribution. Same house convention: **[grounded]** (traceable to the repo today) / **[hypothesis]** (a bet not yet validated).

> Why this page exists: Evidara can serve more than one purpose, and the purposes pull in different directions. The canvas is the tool that makes that trade-off honest instead of implicit. Read [`business-model-canvas.md`](./business-model-canvas.md) first for the commercial canvas; this page generalizes it.

---

## 1. The theory in one screen

The Business Model Canvas (Osterwalder & Pigneur, *Business Model Generation*, 2010) is one page of **9 blocks** describing how an organization creates and captures value. The value isn't the boxes — it's that they force you to see the *whole system at once* and how the boxes depend on each other.

**Right half — the market ("desirability"): does anyone want this?**

- **① Customer Segments** — who you serve
- **② Value Propositions** — the value you offer *(the spine — bridges both halves)*
- **③ Channels** — how you reach them
- **④ Customer Relationships** — how you get, keep, and grow them
- **⑤ Revenue Streams** — what you capture back

**Left half — the machine ("feasibility"): can you deliver it?**

- **⑥ Key Resources** — the assets you need
- **⑦ Key Activities** — what you must do excellently
- **⑧ Key Partnerships** — what you don't build yourself
- **⑨ Cost Structure** — what it costs to run

**Bottom — the economics ("viability"): do the numbers work?** Cost (⑨) vs. what you capture (⑤).

**How to read it:** start on the right (customer + value — is it *wanted*?), confirm you can reach and keep them, flip to the left (can you *build and deliver* it?), then check the bottom (does what you capture exceed what it costs, sustainably?). A model is sound only when all three lenses pass **and** the boxes are internally consistent — a "premium, high-touch" value prop wired to a "cheap, self-serve" channel is a contradiction the canvas exposes at a glance.

**Why it's powerful:** one shared page, dependencies made visible, and every box a **hypothesis you can rank by fragility and test** (see [`business-model-canvas.md` "How to use this canvas"](./business-model-canvas.md#how-to-use-this-canvas)).

## 2. The generalizing insight — swap the currency

Stripped to its logic, the canvas says:

> *For **someone** (①), I create **value** (②), deliver it through **channels/relationships** (③④), using **resources/activities/partners** (⑥⑦⑧) that **cost** something (⑨) — and in return I capture **something back** (⑤).*

Nothing there requires "something back" to be **money.** Change the **currency of ⑤** and *who ① is*, and the same machine describes three different goals — everything else adjusts to fit.

| Block | 💰 Monetary gain | 🎯 Skills evidence (jobs) | 🌍 Open-source contribution |
|---|---|---|---|
| **① Customer** | Buyers who'll pay | Hiring managers, recruiters, future teammates | Developers/users who need the thing; contributors |
| **② Value Prop** | Solves their problem better/cheaper | Proof you design & ship senior-level work | A useful tool they get for free |
| **⑤ Captured ("revenue")** | CHF — willingness to pay | Job offers, comp level, credibility, network | Adoption, stars, contributors, reputation, sponsorship |
| **③ Channels** | Sales, self-serve, SEO | GitHub, a writeup/blog, a demo, your CV, talks | README, package registry, docs, community |
| **④ Relationships** | Support, SLAs, success | Recruiter convos, referrals, "come look at my repo" | Issue responsiveness, contributor onboarding |
| **⑦ Key Activities** | Coverage, freshness, sales | **Making the work legible & impressive** | **Lowering contribution friction** (docs, good-first-issues) |
| **⑥ Key Resources** | Proprietary corpus/data/model | The artifact + your ability to explain it | The codebase + a welcoming community |
| **⑨ Cost** | Infra, salaries, burn | Your time + opportunity cost | Your time + maintainer burden |

**The punchline:** the *product* can be identical while the *business model* is completely different, because the goal changes what you optimize. A paying customer wants coverage and uptime. A hiring manager wants judgment, architecture, and communication. An OSS user wants easy adoption and good docs. **Same repo — three different Key Activities.**

## 3. Evidara's read on each mode

- **🎯 Career evidence — strong *today*, near-zero extra cost.** Clean-room architecture, contracts-first design, numbered ADRs, honest `[grounded]`/`[hypothesis]` strategy docs, and this canvas set are exactly the senior/staff signal that hiring managers hunt for and rarely see. The "customer" (a hiring manager) does not care about 12 docs vs. 2,169 jurisdictions — they care that you *reason* like someone who ships real systems. **[grounded — the ADRs, contracts, and product docs exist in-repo.]**
- **🌍 Open source — a legitimate contribution.** Free, structured, provenanced *primary-law-as-data* fills a real gap (Fedlex is famously hard to consume — a community MCP connector exists just for that). "Revenue" here is adoption + reputation, and it doubles as career proof. **[grounded gap; adoption is a [hypothesis].]**
- **💰 Money — the *unvalidated* one.** No proven buyer, pricing, or willingness-to-pay. A real bet, but the riskiest of the three. **[hypothesis — Lane 10 gap; see [`business-model-canvas.md` ⑤](./business-model-canvas.md).]**

## 4. The 🎯 portfolio canvas (career evidence, drawn in full)

Because the career angle is the cheapest, most-certain return, here's Evidara's canvas drawn **entirely for "skills evidence."** Note how different the *back half* (⑥–⑨) is from the commercial canvas — this is the whole point.

- **① Customer Segments** — engineering leaders and hiring managers for **senior / staff / platform / backend / data-engineering** roles; recruiters who screen for them; the interview panel who'll review the work; secondarily your network (who can refer you). **[the "buyer" you're actually optimizing for.]**
- **② Value Proposition** — *"Concrete proof I operate at senior/staff level: I take an ambiguous domain, define boundaries and contracts, make honest architectural trade-offs, and communicate them clearly."* The differentiator vs. a typical portfolio (tutorials, todo apps): a **real, bounded, multi-component system with governance, ADRs, and intellectual honesty about what's a bet vs. what's built.** **[grounded — that's literally what the repo demonstrates.]**
- **③ Channels** — the **GitHub repo itself**; a top-level README that hooks a reviewer in 60 seconds; a written **case study / blog post** ("how I designed a clean-room legal-data platform"); a **5-minute demo** (Loom/video); your CV & LinkedIn linking to specific artifacts; meetup/conference talks. **[repo exists [grounded]; the writeup/demo are the [gap] to close.]**
- **④ Customer Relationships** — "come look at my repo" in applications; walking an interviewer through **ADR-0029** (a real cost/architecture trade-off) or the boundary contracts; answering *"tell me about a system you designed"* with this instead of a generic story; referrals from people who've seen it.
- **⑤ "Revenue" (captured)** — interview callbacks, offers, **comp *level* (senior vs. staff)**, the caliber of teams that engage, and durable network/reputation. **Metric:** does a hiring manager, in under 10 minutes, come away thinking *"this person operates a level above"*?
- **⑥ Key Resources** — the **artifact** (architecture, ADRs, contracts, the canvas docs) **and your ability to narrate it.** The honest strategy docs are a rare, high-signal differentiator — most portfolios have no `[hypothesis]` ledger. **[grounded.]**
- **⑦ Key Activities** — **legibility work:** a killer README, a case-study writeup, a short demo, curating the "greatest hits" (ADR-0029, boundary contracts, the canvases), a clean architecture diagram. **Explicitly *not*:** more coverage, a freshness SLA, multi-tenancy, or chasing users. Keep the repo tidy and the story tight.
- **⑧ Key Partnerships** — mentors / network who'll review and **refer**; the OSS reception (stars/users = third-party validation you can cite in interviews).
- **⑨ Cost Structure** — mostly **your time (opportunity cost)** — every hour on legibility is an hour not spent on job applications or a paying customer. Note what this mode **does *not* need:** it does **not** require a live production Hetzner cluster, coverage breadth, or an SLA — a local/demo environment is enough. That makes it dramatically cheaper than the commercial mode. **[a deliberate scope cut — the money-canvas's biggest costs are irrelevant here.]**

## 5. The trade-off, made honest

You can't maximize all three currencies at once:

- Chasing **money** means grinding coverage + freshness — invisible on a CV, expensive for a solo dev.
- Chasing **portfolio** means polishing legibility a paying customer wouldn't value.
- Chasing **OSS adoption** means giving away the very thing you'd otherwise charge for.

You can **sequence** them, but not simultaneously max them. And the sequence matters because two of the three currencies are **available today** while the third must be *earned* through validation.

**Recommended sequence:**

1. **Capture the cheap, certain returns now** — ship it **open source** + package it as **portfolio evidence** (the ⑦ legibility work above). Immediate payoff, low cost, and they reinforce each other (OSS traction *is* career proof).
2. **Pursue money only if validated** — run the discovery interviews ([`business-model-canvas.md` fragility ranking](./business-model-canvas.md#how-to-use-this-canvas)); commit to the commercial back-half (coverage, freshness, sales) **only** once a real buyer and willingness-to-pay show up. Until then, that back-half is expensive work against an unproven `[hypothesis]`.

This is the same conclusion the [next-steps fork](./business-model-canvas.md) reaches — now with the *why* underneath it: two of your three "revenue" currencies are cheap and available; the third has to be earned.

## Related

- [`business-model-canvas.md`](./business-model-canvas.md) — the commercial 9-block canvas + fragility ranking + competitor canvas.
- [`value-proposition-canvas.md`](./value-proposition-canvas.md) — customer/value fit, competitive landscape, strategic fork, interview script.
- [`personas.md`](./personas.md) · [`platform-api-one-pager.md`](./platform-api-one-pager.md) · [`ga-criteria.md`](./ga-criteria.md)
