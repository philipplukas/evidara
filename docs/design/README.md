# Design and brand

Brand context for Evidara, kept in the repo so it can be pasted into a design tool — or handed to a
designer — without anyone having to reverse-engineer it from the CSS.

| File | What it is |
|---|---|
| [Brand brief](brand-brief.md) | **Start here.** The single self-contained context file: what Evidara is, the palette, the typography, the mark, and the five hard constraints. Written to be pasted whole into Canva, Recraft, Ideogram, Figma, or an email. |
| [Canva and AI tooling workflow](canva-workflow.md) | How to actually run the work, and which tool to use for which step. Includes an honest account of what Canva is and is not good for here. |
| [`assets/evidara-lattice.svg`](assets/evidara-lattice.svg) | The unmerged lattice mark, exported as a standalone SVG you can upload anywhere. |

## The one-paragraph version

The mark that ships today is a **placeholder** — a navy tile with a serif "E" that the internal
design critique flagged as reading "placeholder rather than brand". The palette and typography,
however, are **settled**: navy `#0f4c81`, violet `#6246D9` as the single action colour, Inter +
Source Serif 4. There is an unmerged candidate mark (the "lattice") with a genuinely coherent idea
behind it — nodes are legal authorities, the lines between them are citations, and one highlighted
node is the authority you were searching for.

Two things to fix before briefing anyone: a **second, dead brand** still sits in the repo
(`contracts/design-tokens/evidara-tokens.css` — cream paper, muted gold, no violet, imported by
nothing), and the **asset layer is at zero** — no favicon, no OG image, no manifest.

## Source of truth

`styles/tokens/tokens.css` is the live palette. Nothing else is, whatever it looks like.
