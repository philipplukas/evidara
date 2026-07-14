/**
 * Shared `BrandMark` — the Evidara lattice.
 *
 * First real component in `@evidara/shell` (ADR-0028), and the brand-mark
 * unification ADR-0027 anticipated. It replaces the placeholder tile — a navy
 * gradient square with a serif "E" — that was inlined in four places across the
 * two surfaces.
 *
 * ── The mark ──
 *
 * A diamond's hardness comes from its lattice: carbon is worthless until its
 * atoms bond, and then it is the hardest thing there is. Precedent works the
 * same way — a ruling alone is an opinion, a ruling bonded to the authorities
 * it cites is not. So: nodes are authorities, bonds are citations, and the one
 * accent node is the authority you were looking for. It is deliberately
 * off-centre; the asymmetry is what stops the mark settling into a snowflake.
 *
 * ── Colour ──
 *
 * The lattice is drawn in `currentColor`, NOT in `--brand`. This is load
 * bearing: workspace renders the mark on a light header (so it inherits navy)
 * while admin renders it on a dark navy header (so it inherits near-white). A
 * hardcoded navy would be invisible on the admin bar. Each surface sets `color`
 * on the wrapper and the mark follows.
 *
 * The accent node reads `--brand-mark-accent` from `styles/tokens/tokens.css`;
 * admin re-points it at a lighter violet so it still carries on its brand
 * header. Drift on either is caught by the brand-mark parity tests.
 *
 * ── Why two variants ──
 *
 * The full lattice does not survive a browser tab. On a 32-unit grid a 0.9
 * stroke renders at 16px as a 0.45-PHYSICAL-pixel line, and r=1.35 nodes become
 * 0.675px dots — every element falls below one pixel and the mark turns to grey
 * mush. Heavier strokes alone do not fix it; the node count has to come down.
 *
 * So `BrandMark` is tuned for >=24px (stroke 1.7, 8 nodes), and `BrandMarkCompact`
 * is its small-size sibling for favicons and anywhere under ~24px: the
 * silhouette, the two diagonals that carry the hit, one centre node, and the hit
 * itself. At that size nobody reads a citation graph — they recognise a shape.
 * A mark plus a simplified small-size lockup is standard practice.
 */

/** Lattice sites — authorities. The bonds between them are the citations. */
const NODES: ReadonlyArray<readonly [number, number]> = [
  [16, 2],
  [2, 16],
  [30, 16],
  [16, 30],
  [16, 16],
  [9, 9],
  [9, 23],
  [23, 23],
];

/** The site the search resolved to. Off-centre on purpose. */
const HIT: readonly [number, number] = [23, 9];

const FRAME = "M16 2 L30 16 L16 30 L2 16 Z";
const AXES = ["M16 2 L16 30", "M2 16 L30 16"] as const;
const DIAGONALS = ["M9 9 L23 23", "M23 9 L9 23"] as const;

export interface BrandMarkProps {
  /** Rendered edge length in px. The geometry is authored on a 32x32 grid. */
  size?: number;
  className?: string;
}

export function BrandMark({ size = 32, className }: BrandMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      className={className}
      role="img"
      aria-label="Evidara"
    >
      <g stroke="currentColor" strokeWidth={1.7} strokeLinejoin="round">
        <path d={FRAME} />
        {AXES.map((d) => (
          <path key={d} d={d} />
        ))}
        {DIAGONALS.map((d) => (
          <path key={d} d={d} />
        ))}
      </g>
      <g fill="currentColor">
        {NODES.map(([cx, cy]) => (
          <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={1.8} />
        ))}
      </g>
      <circle cx={HIT[0]} cy={HIT[1]} r={3.3} fill="var(--brand-mark-accent)" />
    </svg>
  );
}

/**
 * Small-size sibling of {@link BrandMark}. Use below ~24px — favicons, app
 * icons, dense chrome. Keeps the silhouette and the off-centre hit; drops
 * everything that cannot render at 16px.
 */
export function BrandMarkCompact({ size = 16, className }: BrandMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      className={className}
      role="img"
      aria-label="Evidara"
    >
      <g stroke="currentColor" strokeWidth={2.4} strokeLinejoin="round">
        <path d={FRAME} />
        {DIAGONALS.map((d) => (
          <path key={d} d={d} />
        ))}
      </g>
      <circle cx={16} cy={16} r={2} fill="currentColor" />
      <circle cx={HIT[0]} cy={HIT[1]} r={4.2} fill="var(--brand-mark-accent)" />
    </svg>
  );
}
