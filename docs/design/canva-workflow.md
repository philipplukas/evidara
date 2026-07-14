# Canva and AI tooling — how to actually run the brand work

Owner: Philipp Guldimann
Last reviewed: 2026-07-14
Applies to: brand mark, palette, asset export

Companion to [the brand brief](brand-brief.md). The brief is *what* to make; this is *how*, and
which tool to reach for at each step.

## Read this first: what Canva is and is not good for here

Be honest about the tool. Canva is excellent at **brand kits, collateral, and asset export**, and
weak at exactly the thing Evidara needs most — **an original vector mark**.

| Task | Canva | Verdict |
|---|---|---|
| Store the palette + fonts as a reusable Brand Kit | Very good | **Use it** |
| Produce social / OG images, slides, one-pagers | Very good | **Use it** |
| Resize one mark into the full favicon / touch-icon / OG set | Good | **Use it** |
| Explore an original logo concept | Template-driven, generic | Use with suspicion |
| Emit a clean, editable **SVG** to ship in React | Weak — raster-first; SVG export is Pro-only and often traced, not true paths | **Do not rely on it** |

Constraint 4 in the brief is the blocker: the mark ships as **inline SVG with `currentColor`** in a
React component. Canva will not reliably give you that. So:

**Use Canva for the brand system and the assets. Use a vector-native tool for the mark itself.**

## Step 0 — the conflicting brand is already gone

The dead cream/gold token file (`contracts/design-tokens/evidara-tokens.css`) was deleted alongside
this doc. It claimed to be the "single source of truth" while nothing imported it, and briefing a
tool against it would have returned work in a palette Evidara abandoned.

**`styles/tokens/tokens.css` is now the only palette in the repo.** Nothing to do here — it is
recorded so the question does not get re-opened.

## Step 1 — set up the Canva Brand Kit

This makes every later asset consistent for free. In Canva: **Brand → Brand Kit → add**.

**Colours** (from the brief; exactly these, no extras):

```text
#0f4c81   Brand navy       identity
#0b3d68   Navy deep        gradient partner
#1d293d   Ink              wordmark, headings
#6246D9   Accent violet    THE action colour — the only one
#e4e9ef   Page surface
#f8fafc   Panel surface
```

**Fonts:** Inter (body/UI) and Source Serif 4 (display + wordmark). Both are on Google Fonts and
available in Canva. Do not substitute — these are the faces the product actually renders.

**Logo:** upload [`assets/evidara-lattice.svg`](assets/evidara-lattice.svg) so it is available in
every design.

Once this exists, Canva applies the right colours and faces automatically to anything you make.

## Step 2 — the mark itself (not Canva)

Two honest paths.

### Path A — look at the lattice before generating anything

There is a considered candidate on `feat/shared-brandmark` that already satisfies all five
constraints. Rendering it costs an hour, not a project. Judge it at **16px** first — that is where
a 12-node lattice with 0.9px strokes will fail if it is going to.

If it survives, the work is refinement (node count, stroke weight, a simplified small-size
variant), not invention.

### Path B — generate alternatives, in the right tool

| Tool | Use it for | Why |
|---|---|---|
| **Recraft** | **The symbol** | The only mainstream model that emits **true editable SVG paths** — real curves and nodes, not a raster traced into an SVG wrapper. This is the one that matters, because of constraint 4. |
| **Ideogram** | **The wordmark** | Best-in-class text rendering (~90–95% accuracy on specific words vs 30–50% elsewhere). Raster output, so it is for exploration, not delivery. |
| **Figma** | Refinement + lockup | Where you fix geometry, set clear-space, and build the final component. |
| **Looka** | — | Skip. Assembles from shared template libraries; outputs across different briefs share recognisable elements. The opposite of an original mark. |

Paste the **copy-paste creative brief** (brief §9) into Recraft. Generate, then bring the SVG into
Figma and clean the paths by hand — no generator gives you production geometry first time.

## Step 3 — validate against the five constraints

Before committing to anything, check it honestly. This is the gate:

1. Does it work in **one flat colour** with **one** violet element? (Fill it entirely with navy —
   is it still the mark?)
2. Paste it on `#e4e9ef` **and** on the navy gradient. Recolour the line-work white for the second.
   Does it read on **both**?
3. Render at **16×16**. Squint. Is it a shape, or grey mush?
4. Open the SVG. Are they **real paths**, or a traced blob / embedded raster?
5. Count the colours. More than navy + one violet? Reject.

Any failure is disqualifying, no matter how good it looks at 256px.

## Step 4 — back to Canva for the asset set

Once the mark is locked, Canva earns its place. Upload the final SVG and use **Resize** to produce
the set the product is missing entirely:

- `favicon.ico` — 16, 32, 48
- `apple-touch-icon.png` — 180×180
- `icon-192.png`, `icon-512.png` for `manifest.json`
- OG / social image — 1200×630, mark plus wordmark on the navy gradient
- Admin favicon (the control plane currently has **none**)

Then wire them in: `legal-search/frontend/src/app/` (replacing the default Next.js favicon) and
`platform-control/admin/` (which has no `public/` directory at all).

## Step 5 — ship the mark into code

The mark lands as a React component, not an image file:

- `styles/shell/BrandMark.tsx`, exported from `@evidara/shell` per
  [ADR-0028](../adr/0028-shared-shell-module.md).
- Strokes in `currentColor`; the accent node reads `--brand-mark-accent` from
  `styles/tokens/tokens.css`.
- Both surfaces consume the one component — the workspace sets navy on the wrapper, admin sets
  near-white. Brand-mark parity tests on both sides catch drift.

Retire `--brand-mark-gradient` and `--font-brand-mark` when the placeholder tile goes.

## Driving Canva from Claude Code

This repo's Claude Code session has a **Canva connector**. Authenticate once and Canva can be
driven directly from a conversation instead of by hand — useful for the repetitive Step 4 export
pass. Ask Claude to connect to Canva; it will walk through authentication.

## Related

- [Brand brief](brand-brief.md) — the context file to paste into any tool
- [ADR-0027 — workspace/admin visual language](../adr/0027-workspace-admin-visual-language.md)
