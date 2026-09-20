/**
 * Reading mode: where the columns sit, and what is given up first when the
 * window cannot hold all of them.
 *
 * ## Why this is a module and not a media query
 *
 * Opening a document turns the workspace from three co-equal panes into a
 * reading surface: the text takes the centre, the outline sits on the left
 * where reading order expects it, and the evidence for the text — what it
 * points at, and what it points at that the corpus does not hold — sits on the
 * right. The filter rail collapses, because it answers nothing about a
 * document you already have open (#1053).
 *
 * Four columns plus a result strip do not fit at every desktop width, so
 * something has to go, and the ORDER is a decision rather than a side effect:
 *
 *   1. The **evidence rail** collapses first. It is reference material; you
 *      consult it after reading a passage, not to find one.
 *   2. The **outline** collapses second, and only to a strip that still states
 *      the position — losing the text's width costs more than losing the
 *      labels, but losing "where am I in 1,377 sections" costs more than
 *      either.
 *   3. The reader itself never collapses. It is the thing being used.
 *
 * Written here as a pure function of the viewport width so the rule can be
 * asserted without a browser, and so the two rails cannot drift apart by each
 * carrying its own breakpoint. `reading-layout.test.ts` fails if the order is
 * inverted or a threshold is removed; `e2e/workspace-panels.spec.ts` measures
 * the rendered geometry the rule produces.
 *
 * ## The numbers
 *
 * Measured at 1440 on the production build (#1053): the shell frame is
 * `max-w-[var(--container-max)]` with `lg:px-6`, so the panel row is 1392px
 * wide and the separators cost 1px of layout each (`RESIZE_HANDLE_HIT_AREA_PX`
 * is pulled back by negative margins). Percentages below are of that row and
 * MUST total exactly 100 per state — react-resizable-panels renormalizes any
 * other total against the sum it is given, which is how an 18/82 split
 * silently became 18.75% the moment a fourth panel appeared.
 */

/** Which rails are open, in the order they are given up. */
export type ReadingRailState =
  /** Everything open: result strip, outline, reader, evidence. */
  | "full"
  /** The evidence rail is a strip. The outline still lists sections. */
  | "evidenceCollapsed"
  /** The evidence rail is a strip and the outline is one too. */
  | "outlineCollapsed";

/**
 * Below this viewport width the evidence rail collapses.
 *
 * At 1400 the four columns and the result strip still leave the reader a
 * 65-character measure; below it they do not, and the evidence rail is the
 * column whose absence costs the reader least.
 */
export const EVIDENCE_RAIL_MIN_VIEWPORT_PX = 1400;

/**
 * Below this viewport width the outline collapses to a strip.
 *
 * Strictly below {@link EVIDENCE_RAIL_MIN_VIEWPORT_PX}: the order is the
 * point. A window narrow enough to lose the outline has already lost the
 * evidence rail.
 */
export const OUTLINE_RAIL_MIN_VIEWPORT_PX = 1180;

/**
 * The rails a viewport of this width can carry.
 *
 * Note this is the *viewport* width, not the panel row's — the shell gutters
 * are constant and the thresholds are stated in the units a window is resized
 * in.
 */
export function readingRailStateFor(viewportWidth: number): ReadingRailState {
  if (viewportWidth >= EVIDENCE_RAIL_MIN_VIEWPORT_PX) return "full";
  if (viewportWidth >= OUTLINE_RAIL_MIN_VIEWPORT_PX) return "evidenceCollapsed";
  return "outlineCollapsed";
}

/** The five columns of reading mode, as percentages of the panel row. */
export interface ReadingSplit {
  /** Collapsed to the icon rail — see `FILTER_RAIL_COLLAPSED_PX`. */
  filters: number;
  /** The narrow result strip. Retiring it belongs to #1040, not here. */
  results: number;
  outline: number;
  reader: number;
  evidence: number;
}

/**
 * The split per rail state. Each totals exactly 100 (asserted in the tests).
 *
 * The reader's share grows as the rails collapse, which is what keeps the
 * measure inside the 65-75 character band from 1024 up to the 1600px container
 * cap rather than only at the design width.
 */
export const READING_SPLIT: Record<ReadingRailState, ReadingSplit> = {
  full: { filters: 4, results: 14, outline: 14, reader: 53, evidence: 15 },
  evidenceCollapsed: { filters: 4, results: 15, outline: 17, reader: 60, evidence: 4 },
  outlineCollapsed: { filters: 4, results: 16, outline: 5, reader: 71, evidence: 4 },
};

/** Whether the evidence rail renders as a strip in this state. */
export function isEvidenceRailCollapsed(state: ReadingRailState): boolean {
  return state !== "full";
}

/** Whether the outline renders as a strip in this state. */
export function isOutlineRailCollapsed(state: ReadingRailState): boolean {
  return state === "outlineCollapsed";
}

// ─── Turning the split into pixels ───
//
// These three restate values that CSS owns: `--container-max` in
// `styles/tokens/tokens.css`, `lg:px-6` on `.shell-frame`, and the 1px of net
// layout a `ResizableHandle` occupies after its negative margins
// (`resizable-panels.tsx`). A model of the layout is not the layout, so the
// arithmetic here is checked against a browser rather than trusted: the
// measured-geometry tests in `e2e/workspace-panels.spec.ts` assert the same
// widths against a rendered page, and they go red if one of those CSS values
// moves while these do not.

/** `--container-max` in `styles/tokens/tokens.css`. */
export const CONTAINER_MAX_PX = 1600;

/** `.shell-frame`'s `lg:px-6`, per side. */
export const SHELL_GUTTER_PX = 24;

/** Separators between the five reading columns, at 1px of layout each. */
export const READING_SEPARATOR_COUNT = 4;

/** Width the five reading columns share at a given viewport width, in px. */
export function readingPanelRowPx(viewportWidth: number): number {
  return Math.min(viewportWidth, CONTAINER_MAX_PX) - 2 * SHELL_GUTTER_PX - READING_SEPARATOR_COUNT;
}

/** Rendered width of one reading column at a given viewport width, in px. */
export function readingColumnPx(viewportWidth: number, column: keyof ReadingSplit): number {
  const state = readingRailStateFor(viewportWidth);
  return (readingPanelRowPx(viewportWidth) * READING_SPLIT[state][column]) / 100;
}
