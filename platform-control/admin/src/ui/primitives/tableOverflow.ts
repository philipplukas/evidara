/**
 * Pure geometry helper behind `DataTable`'s horizontal-scroll affordance.
 *
 * The table already scrolled — `overflow-x: auto` has been on the wrapper since
 * the column-clipping fix. What it never did was *say so*. Measured on the run
 * queue at 1440px: `scrollWidth 1160 > clientWidth 1054`, wrapper computed
 * `box-shadow: none, mask-image: none`. `UPDATED` and `ACTIONS` sat past the
 * right edge with nothing on screen to suggest they existed, and `ACTIONS` is
 * where cancel and retry live — the only two levers an operator has on a live
 * run. A scroll container with no cue is a hidden control, not a compact table.
 *
 * Kept free of React and the DOM (it takes three numbers) because the branch
 * that matters — "there is more to the right" — cannot be exercised in jsdom,
 * which has no layout engine and reports every dimension as 0.
 */

export type TableOverflow = {
  /** Content is wider than the viewport of the scroll container. */
  overflowing: boolean;
  /** There is content scrolled off the left edge. */
  canScrollLeft: boolean;
  /** There is content still to the right. */
  canScrollRight: boolean;
};

export const NO_TABLE_OVERFLOW: TableOverflow = {
  overflowing: false,
  canScrollLeft: false,
  canScrollRight: false,
};

/**
 * Sub-pixel slack. Browsers report fractional `scrollWidth`/`clientWidth` under
 * zoom and fractional layouts, so an exactly-fitting table can report
 * `scrollWidth` a fraction larger than `clientWidth`. Without the tolerance the
 * cue flickers on for tables that do not actually scroll.
 */
const EPSILON = 1;

export function resolveTableOverflow(metrics: {
  scrollLeft: number;
  scrollWidth: number;
  clientWidth: number;
}): TableOverflow {
  const { scrollLeft, scrollWidth, clientWidth } = metrics;
  const overflowing = scrollWidth - clientWidth > EPSILON;
  if (!overflowing) {
    return NO_TABLE_OVERFLOW;
  }
  return {
    overflowing: true,
    canScrollLeft: scrollLeft > EPSILON,
    canScrollRight: scrollWidth - clientWidth - scrollLeft > EPSILON,
  };
}

/**
 * Value equality.
 *
 * `resolveTableOverflow` returns a fresh object, and the component re-measures
 * after every render — so without this the `setState` would always see a new
 * identity and render again, forever. Comparing the three booleans lets the
 * update no-op, which is what makes render-time measurement safe.
 */
export function sameTableOverflow(a: TableOverflow, b: TableOverflow): boolean {
  return (
    a.overflowing === b.overflowing &&
    a.canScrollLeft === b.canScrollLeft &&
    a.canScrollRight === b.canScrollRight
  );
}

/**
 * The value written to `data-overflow` on the scroll container. Exposed as an
 * attribute so an e2e test can assert the *state the user sees* rather than
 * re-deriving the geometry, and so a future CSS-only cue has a hook.
 */
export function tableOverflowState(overflow: TableOverflow): "none" | "left" | "right" | "both" {
  if (!overflow.overflowing) return "none";
  if (overflow.canScrollLeft && overflow.canScrollRight) return "both";
  if (overflow.canScrollLeft) return "left";
  return "right";
}
