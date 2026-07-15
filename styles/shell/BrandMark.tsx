/**
 * Shared `BrandMark` — the Evidara lattice.
 *
 * First real component to land in `@evidara/shell` after the scaffolding gate
 * (ADR-0028), and the brand-mark unification that ADR anticipated. Both
 * surfaces consume it via the path alias declared in their respective
 * `tsconfig.json`:
 *
 *   "@evidara/shell":   ["../../styles/shell"],
 *   "@evidara/shell/*": ["../../styles/shell/*"]
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
 * while admin renders it on a dark navy header (so it inherits near-white).
 * A hardcoded navy would be invisible on the admin bar. Each surface sets
 * `color` on the wrapper and the mark follows.
 *
 * The accent node reads `--brand-mark-accent` from `styles/tokens/tokens.css`,
 * which admin re-points at a lighter violet so it still carries on its brand
 * header. Drift on either is caught by the brand-mark parity tests on both
 * surfaces.
 */

export interface BrandMarkProps {
  /** Rendered edge length in px. The geometry is authored on a 32×32 grid. */
  size?: number;
  className?: string;
}

/** Lattice sites — authorities. The bonds between them are the citations. */
const NODES: ReadonlyArray<readonly [number, number]> = [
  [16, 2],
  [9, 9],
  [16, 9],
  [2, 16],
  [9, 16],
  [16, 16],
  [23, 16],
  [30, 16],
  [9, 23],
  [16, 23],
  [23, 23],
  [16, 30],
];

/** The site the search resolved to. Off-centre on purpose. */
const HIT: readonly [number, number] = [23, 9];

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
      <g stroke="currentColor" strokeWidth={0.9}>
        <path d="M16 2 L30 16 L16 30 L2 16 Z" />
        <path d="M16 2 L16 30" />
        <path d="M2 16 L30 16" />
        <path d="M9 9 L23 23" />
        <path d="M23 9 L9 23" />
        <path d="M9 9 L23 9" />
        <path d="M9 23 L23 23" />
      </g>
      <g fill="currentColor">
        {NODES.map(([cx, cy]) => (
          <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={1.35} />
        ))}
      </g>
      <circle cx={HIT[0]} cy={HIT[1]} r={2.6} fill="var(--brand-mark-accent)" />
    </svg>
  );
}
