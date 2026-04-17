# UI Review Checklist

Owner: Product / design / release
Last reviewed: 2026-04-15
Last verified: 2026-04-15
Applies to: milestone reviews, `TAR-69` / `TAR-160` updates, demo-readiness checks, and UI / UX quality feedback

## Purpose

Use this runbook when you need evidence for statements like:

- "this looks credible"
- "this feels polished"
- "this is demo-safe"
- "this still feels generic or placeholder-like"

The goal is to make UI / UX feedback more concrete and less subjective by combining:

- screenshots for visual quality
- video for flow quality
- manual review for human judgment
- optional AI critique as a second reviewer

## Recommended evidence stack

Do not rely on only one source.

Use this order:

1. screenshot pack
2. recorded flow video
3. manual walkthrough
4. optional AI critique

Why:

- screenshots are best for hierarchy, spacing, typography, density, and polish
- video is best for rhythm, motion, and navigation feel
- manual use is best for trust, confusion, and demo confidence
- AI critique is best as a second reader, not as the final judge

## Local review loop

### 1. Start the local cross-surface stack

From repo root:

```bash
bash scripts/dev-cross-surface-live.sh
```

This starts the lean backend stack, legal-search frontend, and control-panel admin together.

### 2. Generate the interaction-flow evidence pack

From repo root:

```bash
bash scripts/run-interaction-flow-local.sh
```

If you also want journey video and richer traces:

```bash
bash scripts/run-interaction-flow-local.sh --record
```

### 3. Review the generated outputs

Primary review surfaces:

- `legal-search/frontend/playwright-report/index.html`
- `legal-search/frontend/screenshot-pack/`
- `legal-search/frontend/test-results/`

Typical assets include:

- canonical screenshots for legal-search and admin
- Playwright HTML report
- recorded journey video when `--record` is used
- traces/videos for debugging if a test fails

## What to review

Start with these screens and flows:

- search / home state
- result list
- detail panel / proof document
- cross-surface handoff into admin
- admin run detail
- admin source detail

If reviewing a new milestone, focus on the exact changed path first before scanning the rest.

## Human review checklist

For each important screen or flow, rate:

- `strong`
- `improving`
- `weak`

Review dimensions:

### 1. Clarity

- do I immediately understand what this screen is for?
- do the main actions and labels make sense?

### 2. Credibility

- do titles, labels, document types, and results feel believable?
- would a stakeholder trust what they are seeing?

### 3. Aesthetics

- does the interface look polished and intentional?
- does the visual hierarchy feel designed rather than accidental?
- do typography, spacing, and density support confidence?

### 4. Seriousness and tone

- does the product feel appropriate for legal research?
- does it feel calm, serious, and reliable rather than generic or playful?

### 5. Flow quality

- does moving through the product feel smooth and unsurprising?
- do transitions between search, detail, and admin feel coherent?

### 6. Demo readiness

- would I show this to someone important without apology?
- would I need to explain away visual roughness or trust gaps?

## What to write down

For each screen or flow, capture:

- what looks strong
- what reduces trust
- what feels confusing
- what looks generic, placeholder-like, or low-care
- whether you would demo it today: `yes`, `almost`, or `no`

## Suggested review notes template

```markdown
## UI review

### Overall
- Overall verdict: <strong / improving / weak>
- Demo-ready today: <yes / almost / no>

### What felt strong
- ...
- ...

### What reduced trust
- ...
- ...

### What looked visually weak
- ...
- ...

### What felt confusing in the flow
- ...
- ...

### Highest-value next changes
1. ...
2. ...
3. ...
```

## Optional AI critique

AI can be useful as a second reviewer, especially for:

- visual hierarchy
- aesthetic polish
- copy clarity
- inconsistency across screens
- identifying places that feel generic or low-trust

Do not use AI as the final judge of whether the experience is good enough. Use it to sharpen the review, not replace it.

### Prompt for Claude cowork

Use this with screenshots and, if available, a short recorded flow video:

```text
I’m reviewing a legal research product and want a product-design critique, not a coding critique.

Please review the attached screenshots and/or short flow video and give structured feedback on these dimensions:

1. Credibility and trust
2. Visual polish / aesthetics
3. Clarity and information hierarchy
4. Tone and seriousness for a legal-research product
5. Demo readiness
6. What looks generic, placeholder-like, or low-confidence
7. Top 5 improvements by impact

Important instructions:
- Judge this as a product experience for humans, not as a technical artifact.
- Be specific about what visually reduces trust.
- Call out anything that feels cluttered, cheap, inconsistent, or underdesigned.
- Separate “functionally okay” from “visually credible.”
- If something is good, say exactly why.
- If something is weak, explain whether the issue is copy, layout, hierarchy, density, styling, or flow.
- End with:
  - overall verdict: strong / improving / weak
  - would you consider this demo-ready: yes / almost / no
  - the 3 highest-value changes to make next
```

## How to turn this into milestone evidence

When updating `TAR-69`, `TAR-160`, or a milestone note, summarize the UI review in this form:

- what already feels credible
- what still reduces trust
- whether the product is demo-safe today
- the top 1-3 visible improvements needed next

Good example:

- "The product is operationally healthier, but the detail experience still looks placeholder-like in a way that reduces trust."
- "The flow is mostly understandable, but the results view still feels visually generic for a legal-research product."

## Related docs

- [Milestone planning rubric](milestone-planning-rubric.md)
- [Interaction flow validation](interaction-flow-validation.md)
- [legal-search testing matrix](../../legal-search/frontend/docs/testing-matrix.md)
