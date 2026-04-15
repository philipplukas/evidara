# Milestone Planning Rubric

Owner: Product / release
Last reviewed: 2026-04-15
Last verified: 2026-04-15
Applies to: milestone updates, `TAR-69` / `TAR-160` synthesis, leadership status notes, and product-quality planning

## Purpose

Use this rubric when a milestone update needs to reflect both:

- what users and stakeholders experience
- how safe and repeatable the team feels when making the next change

This keeps planning from collapsing into only one lens:

- not just implementation progress
- not just demo polish
- not just release evidence

The goal is to make milestone language clearer, more honest, and easier to reuse across
Linear, release notes, and leadership updates.

## When to use it

Use this rubric when you are:

- writing a milestone or release update
- updating `TAR-69`, `TAR-160`, `TAR-241`, or `TAR-242`
- deciding whether the next milestone is product-facing or infrastructure-facing
- translating technical findings into stakeholder language

## The six planning dimensions

Evaluate each milestone on these six dimensions.

### 1. Customer value

Question:

- does this milestone improve something a customer or reviewer would notice?

Look for:

- better search outcomes
- more credible document detail views
- lower confusion in core flows
- fewer obvious broken-path moments

Good update wording:

- "The product now returns visible results for the core path again."
- "Users can open the proof documents and understand what they are looking at."

### 2. UI / UX quality

Question:

- does the experience feel understandable, trustworthy, and demo-safe?
- does the interface feel visually polished enough to support trust?

Look for:

- titles, labels, and types that make sense to a human reader
- search results that feel plausible on first glance
- pages that do not require apology or explanation
- states that communicate clearly when data is incomplete
- visual hierarchy that feels intentional rather than accidental
- typography, spacing, and density that support comprehension
- screens that do not feel cluttered, generic, or placeholder-like
- an overall aesthetic tone that feels calm, serious, and appropriate for legal research

Use UI / UX as its own planning dimension when:

- the backend technically works but the experience still looks broken
- placeholder labels, weak hierarchy, or confusing copy reduce trust
- the product is functionally correct but still looks immature or low-care
- the team is debating whether an issue is "just polish" even though it affects confidence

Good update wording:

- "The path works, but the current AT detail view still looks placeholder-like."
- "The product is operationally healthier, but first-use search trust is still weak."
- "The experience is more functional than before, but still not visually credible enough for a strong review."

### 3. Product trust and credibility

Question:

- if a stakeholder saw this flow cold, would they believe the product is working?

Look for:

- representative proof docs with credible titles and types
- seed queries with clearly plausible top hits
- evidence that the product behavior matches the story being told

Good update wording:

- "The system is no longer blocked by replay, but product trust is still limited by title quality and generic search hits."

### 4. Execution reliability

Question:

- can the team rerun or demonstrate this path consistently enough to rely on it?

Look for:

- worker/replay stability
- repeatable operator flows
- reduced dependence on lucky timing or hidden environment state

Good update wording:

- "The runtime path is healthy again and no longer the main blocker."

### 5. Engineering confidence

Question:

- can we keep changing this area safely?

Look for:

- focused tests around the changed behavior
- code that is understandable enough for the next contributor
- smaller, reviewable change slices rather than tangled branches
- clear ownership of follow-up work

This is where code quality and testing belong.

Track explicitly:

- whether the current area has enough narrow tests
- whether fixes are isolated or still leaking across systems
- whether code quality is helping or slowing the next milestone

Good update wording:

- "The remaining issue is narrower now, but the title path still spans multiple services."
- "The latest fix is covered by focused regression tests, which lowers follow-up risk."

### 6. Documentation and operator readiness

Question:

- can someone else verify, explain, and repeat the current state without tribal knowledge?

Look for:

- current runbooks
- current evidence notes
- current Linear comments
- clear operator commands and expected outcomes

This is where documentation capability should be tracked, not as housekeeping but as
delivery capacity.

Good update wording:

- "The repo and Linear now tell the same story."
- "The path is easier to hand off because rerun steps and evidence notes are current."

## How to combine technical and nontechnical feedback

For each milestone, capture feedback in two sections:

### A. Experience feedback

Questions:

- what does a user, operator, or reviewer actually see?
- what feels trustworthy?
- what still feels confusing, generic, or unfinished?
- what visually reduces confidence even when the behavior is technically correct?

Sources:

- demo review notes
- seed-query walkthroughs
- proof-doc inspection
- operator feedback
- UI / UX review observations
- visual design and aesthetic review observations

### B. Delivery feedback

Questions:

- how hard was it to make the change safely?
- where did code quality help or hurt?
- did tests give enough confidence?
- did docs and runbooks reduce coordination cost?

Sources:

- PR review notes
- test results
- branch / commit hygiene
- runbook drift
- manual deployment or verification friction

Use both sections in milestone planning. A milestone is only truly healthy when:

- the experience improved
- the team also became more capable of improving it again

## Simple milestone template

Use this template for Linear or stakeholder updates:

```markdown
## Milestone update

### What improved
- <customer-visible improvement>
- <reliability or execution improvement>

### What still blocks confidence
- <UI / UX or trust issue>
- <quality or evidence gap>

### Current planning read
- customer value: <strong / improving / weak>
- UI / UX quality: <strong / improving / weak>
- product trust: <strong / improving / weak>
- execution reliability: <strong / improving / weak>
- engineering confidence: <strong / improving / weak>
- docs / operator readiness: <strong / improving / weak>

### Next milestone
- <one milestone sentence in product language>

### Acceptance bar
- <what success looks like to a reviewer>
- <what success looks like to the team delivering it>
```

## Suggested acceptance bars

### Milestone A — trustworthy proof experience

Success means:

- representative proof docs show real, human-credible titles and types
- reviewers do not encounter obvious placeholder labels on the proof set
- detail pages feel safe to show in a demo or release review without explanation
- the overall presentation feels polished and intentional enough to support trust

### Milestone B — search confidence baseline

Success means:

- a small agreed seed-query set returns clearly plausible top results
- reviewers can explain why the top hits make sense without tribal context
- the search experience no longer feels broken or random on first use
- the results view looks visually credible rather than generic or placeholder-heavy

## Current planning application (2026-04-15)

Use the rubric above to frame the current milestone sequence like this:

### Milestone 1 — trustworthy proof experience

Planning read:

- customer value: improving
- UI / UX quality: improving, but still weakened by placeholder presentation
- product trust: improving, but still blocked by the AT proof-doc title
- execution reliability: improving after the worker/runtime fix
- engineering confidence: improving because the title issue is narrower than before
- docs / operator readiness: improving because repo docs and Linear are now aligned

What this means:

- the system is healthy enough to evaluate
- the product is not yet healthy enough to impress
- the next visible win is to make the proof-doc experience credible

### Milestone 2 — search confidence baseline

Planning read:

- customer value: important and highly visible
- UI / UX quality: still weak if seed queries look generic
- product trust: still weak until first-use search feels plausible
- execution reliability: no longer the main blocker
- engineering confidence: moderate, because search quality still spans metadata and ranking
- docs / operator readiness: good enough to support another evaluation pass

What this means:

- the main product risk is now "does search feel believable?"
- this should be framed as a confidence milestone, not just a ranking milestone

### Milestone 3 — GA narrative and evidence assembly

Planning read:

- customer value: indirect but necessary for release confidence
- UI / UX quality: should be summarized explicitly, not assumed
- product trust: depends on milestones 1 and 2 being credible
- execution reliability: should be stated as recovered, not still ambiguous
- engineering confidence: should include code quality, tests, and branch hygiene
- docs / operator readiness: should be strong enough for handoff without tribal knowledge

What this means:

- the final recommendation should evaluate both experience quality and delivery confidence
- do not publish a strong go / no-go story that only talks about infrastructure health

## Recommended status language

Prefer language like:

- "The system is operationally healthier, but user trust is still gated by visible quality."
- "The path works reliably enough to evaluate; the next milestone is experience credibility."
- "The product risk is now narrower: less about liveness, more about trust and presentation."

Avoid language like:

- "Only polish remains" when the issue is clearly visible to users
- "Infra is fixed, so we are basically done" when search trust is still weak
- "Tests passed, so the milestone is complete" without experience validation

## Related docs

- [GA operator board](ga-operator-board.md)
- [GA status rollup](ga-status-rollup.md)
- [Phase 5 go / no-go memo](phase-5-go-no-go-memo.md)
- [Linear M5 / Phase 5 handoff pack](linear-milestone5-handoff-pack.md)
