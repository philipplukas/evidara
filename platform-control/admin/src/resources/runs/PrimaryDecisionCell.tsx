/**
 * `PrimaryDecisionCell` — elevated, full-width variant of `DecisionCell` that
 * leads the decision-support block (issue #393). Shares `DecisionCell`'s
 * structure and token vocabulary but bumps the label scale and swaps the
 * shadow token from `--shadow-card` to `--shadow-card-hover` so the operator's
 * primary cue reads as the anchor rather than a co-equal quadrant.
 *
 * Lifted from `RunShowV2.tsx` as a sibling export so the hierarchy can be
 * exercised by a unit test — see `PrimaryDecisionCell.test.tsx`.
 */
export function PrimaryDecisionCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[12px] border border-[rgba(29,41,61,0.1)] bg-white p-4 space-y-1 shadow-[var(--shadow-card-hover)]">
      <span className="block text-[15px] font-semibold uppercase tracking-[0.08em] text-[rgba(29,41,61,0.8)] leading-[1.2]">
        {label}
      </span>
      <p className="text-[14px] text-[var(--foreground)] leading-snug">{value}</p>
    </div>
  );
}
