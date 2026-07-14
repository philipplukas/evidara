# Evidara brand brief

Owner: Philipp Guldimann
Last reviewed: 2026-07-14
Applies to: legal-search (workspace), platform-control/admin (control plane)

This is the **single context file** to paste into any design tool — Canva, Recraft, Ideogram,
Figma, or a designer's inbox. It is written to be self-contained: someone who has never seen
Evidara should be able to work from it alone.

Everything below is copied from the live code, not from memory. Sources are named so a future
reader can check the values have not drifted.

## 1. What Evidara is

A **document intelligence platform for legal and regulatory research**. It ingests primary legal
sources (Swiss Fedlex, Austrian RIS, EUR-Lex, Légifrance), turns them into structured canonical
documents, and serves them through a search workspace.

**Two products, one brand** (see [ADR-0027](../adr/0027-workspace-admin-visual-language.md)):

| Surface | Audience | Job |
|---|---|---|
| **Workspace** (`legal-search`) | Lawyers, legal researchers | Read carefully. Search, compare, cite. |
| **Control plane** (`platform-control/admin`) | Internal operators | Scan and act. Approve sources, run acquisitions, triage failures. |

ADR-0027 decided these two **should not share a look beyond the brand marks**. The mark is
therefore the *only* thing that must work in both worlds.

## 2. Tone

The product deliberately reads as **editorial, not dashboard**. From the internal design critique:

> "A mature, publishing-adjacent pairing that signals *read carefully, not dashboard-scan*."

Words that apply: precise, sober, Swiss, archival, considered, trustworthy.
Words that do not: playful, disruptive, bubbly, neon, startup-y, AI-futuristic.

The audience is lawyers. A mark that looks like a crypto logo or a generic SaaS swoosh actively
costs credibility.

## 3. Palette — settled, do not invent new colours

Source of truth: `styles/tokens/tokens.css`.

### Core

| Role | Hex | Notes |
|---|---|---|
| Brand navy | `#0f4c81` | Identity. The mark, the admin bar. |
| Navy (hover/deep) | `#0b3d68` | Gradient partner to the above. |
| Ink | `#1d293d` | Wordmark, headings. |
| **Accent violet** | `#6246D9` | **THE action colour. The only one.** |

The single-accent rule is load-bearing: violet means *interactive*, everywhere, and nothing else
is allowed to compete with it. A logo that introduces a second accent breaks the system.

### Surfaces (light)

| Role | Hex |
|---|---|
| Page | `#e4e9ef` |
| Panel | `#f8fafc` |
| Input | `#f1f5f9` |

These are **cool grey-blue**, not cream. See the warning in §7.

### Semantic status (never use as brand colours)

`#166534` healthy · `#92400e` degraded · `#991b1b` critical · `#1e40af` info

## 4. Typography

Both from Google Fonts, loaded via `next/font`:

- **Inter** — body, UI, data.
- **Source Serif 4** — display, headings, and the wordmark.

There is **no custom or licensed typeface**. The "Evidara" wordmark today is simply Source Serif 4
text — it has never been drawn as a lockup. That is an open opportunity, not a constraint.

## 5. The mark

### What ships today: a placeholder

A navy gradient rounded tile containing a serif letter **E**. Inlined in three places. The internal
critique is blunt about it:

> "Current lockup is a plain 'E' avatar tile… Until the mark lands, the app header reads
> **'placeholder' rather than 'brand'**."

So there is **no incumbent design to respect**. Anything chosen replaces a stopgap.

### The unmerged candidate: the lattice

Lives on branch `feat/shared-brandmark` as `styles/shell/BrandMark.tsx`; exported here as
[`assets/evidara-lattice.svg`](assets/evidara-lattice.svg).

A diamond drawn as a **crystal lattice**: a rotated square frame, two axes, two diagonals, two
rungs, with 12 filled nodes at the intersections — and **one larger accent node, off-centre**.

Its argument, from the component's own docstring:

> A diamond's hardness comes from its lattice: carbon is worthless until its atoms bond, and then
> it is the hardest thing there is. Precedent works the same way — a ruling alone is an opinion, a
> ruling bonded to the authorities it cites is not. So: **nodes are authorities, bonds are
> citations, and the one accent node is the authority you were looking for.** It is deliberately
> off-centre; the asymmetry is what stops the mark settling into a snowflake.

Whether or not this exact geometry survives, **that idea is the brief**: a citation graph, with one
resolved hit.

## 6. Hard constraints — any mark must satisfy all five

These are not preferences. A mark that fails any of them cannot ship.

1. **Monochrome + one accent.** The mark must be drawn in a single inherited colour, with at most
   one element in violet. In code this is `currentColor`; the accent node is the only exception.
2. **Legible on light *and* dark navy.** The workspace header is near-white (`#e4e9ef`); the admin
   bar is a navy gradient (`#0f4c81` → `#0b3d68`). The *same* mark, no variants, must read on both.
   This is why a navy-only mark is disqualified — it vanishes on the admin bar.
3. **Survives 16px.** There is no favicon today, so 16×16 is a day-one size. Fine strokes and many
   nodes are exactly what dies here. Test at 16 before falling in love at 256.
4. **True vector.** It ships as inline SVG in a React component. A raster PNG, or a raster traced
   into an SVG wrapper, is not usable. Real paths only.
5. **No second accent, no gradient in the mark itself.** The gradient currently in the placeholder
   tile is going away.

## 7. Known conflicts

**A second, dead brand used to live in the repo — it has been deleted.**
`contracts/design-tokens/evidara-tokens.css` encoded a *different* identity — cream paper
(`#f4efe7`), muted gold (`#9a7a4a`), and **no violet at all** — while its own docstring declared
itself the "single source of truth" and told both apps to import it. Nothing did. Its badge and
chart ramps were duplicated (and superseded) in the live file, and its gold `--highlight` existed
nowhere else.

It was removed in the same change that added this brief, precisely so nobody briefs a designer or a
model against it by accident. **`styles/tokens/tokens.css` is the only palette.**

Note that the older design critique still describes a cream canvas (`#FBF6EC`) the live tokens no
longer have. Treat that document as a record of a direction that was walked back, not as current.

**The previous brand exploration is lost.** The critique cites
`screenshot-pack/design/brand-decision-playbook.md` with "27 design artifacts, 5 exploration SVGs,
and no locked decision." That path is gitignored and does not exist on disk.

## 8. Asset gap — currently zero

Whatever is chosen needs all of this, none of which exists:

- Favicon (workspace still ships the **default Next.js icon**; admin has **none at all**)
- `apple-touch-icon`, `manifest.json` / `site.webmanifest`
- OG / social share image
- A drawn wordmark lockup, with clear-space and minimum-size rules
- Monochrome and reversed variants

## 9. Copy-paste creative brief

Everything above, compressed for a prompt box:

> Design a logo mark for **Evidara**, a legal document intelligence platform for lawyers
> researching Swiss, Austrian and EU primary law. Tone: precise, sober, Swiss, archival — the
> opposite of playful startup branding. The concept: a **citation graph** — nodes are legal
> authorities, the lines between them are citations, and **one single highlighted node is the
> authority you were searching for**. Draw it as a geometric lattice or crystal structure, ideally
> reading as a diamond. Constraints: flat vector, monochrome line-work in navy `#0f4c81`, with
> exactly **one** node in violet `#6246D9` as the only other colour. No gradients, no 3D, no
> shadows, no text in the mark. It must stay legible at 16×16 pixels and must read equally well
> when the line-work is white on a dark navy background. Square, centred, generous clear space.

## Related

- [ADR-0027 — workspace/admin visual language](../adr/0027-workspace-admin-visual-language.md)
- [Canva and AI tooling workflow](canva-workflow.md)
- `styles/tokens/tokens.css` — the live token source of truth
