/**
 * Temporal validity — "was this norm in force on 2019-06-01?" (ADR-0033).
 *
 * A municipal ban enacted in 2019 must be judged against the law in force in
 * 2019, not the law in force today. Documents carried `effective_date` but no
 * repeal date, so the question had no answer at all.
 *
 * The state is deliberately FOUR-valued, not a boolean. ADR-0033 §2: the agent
 * must be able to refuse. `unknown` — "this norm is marked repealed but we do
 * not hold the date" or "we do not hold a start date" — is a correct and useful
 * answer; a `false` invented from a missing field is not, and a `true` invented
 * from one is worse. Collapsing `unknown` into `true` is exactly the confident
 * fabrication the ADR exists to prevent.
 */

/** Fields a projection row must carry for temporal validity to be answerable. */
export type InForceFields = {
  /**
   * First date the norm was in force. The projection builder falls back to
   * `effective_date` when the upstream document does not carry an explicit one,
   * so this is the single field to range-query on.
   */
  in_force_from?: string;
  /**
   * Last date the norm WAS in force — inclusive. Absent means "not repealed as
   * far as we know", which is not the same as "never repealed".
   */
  in_force_until?: string;
  lifecycle_status?: string;
};

export type InForceState =
  /** In force on the given date. */
  | 'in_force'
  /** The date precedes the norm's entry into force. */
  | 'not_yet_in_force'
  /** The norm had been repealed by the given date. */
  | 'repealed'
  /** We do not hold the dates needed to answer. Say so; do not guess. */
  | 'unknown';

/** ISO `YYYY-MM-DD` strings compare correctly as plain strings. */
function isIsoDate(value: string | undefined): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value);
}

/**
 * Resolve whether `document` was in force on `at` (an ISO `YYYY-MM-DD` date).
 *
 * Order matters: a known repeal date settles the question even when the start
 * date is missing, because "repealed before the date asked about" is knowable
 * without knowing when it began.
 */
export function resolveInForceState(document: InForceFields, at: string): InForceState {
  const from = isIsoDate(document.in_force_from) ? document.in_force_from.slice(0, 10) : undefined;
  const until = isIsoDate(document.in_force_until)
    ? document.in_force_until.slice(0, 10)
    : undefined;
  const asOf = at.slice(0, 10);

  if (until && asOf > until) return 'repealed';
  if (from && asOf < from) return 'not_yet_in_force';

  // Marked repealed but with no date: we know it ended, not when. On any date
  // at or after its start we cannot tell whether it had already fallen away.
  if (document.lifecycle_status === 'repealed' && !until) return 'unknown';

  return from ? 'in_force' : 'unknown';
}

/**
 * OpenSearch clauses that exclude documents *known* to be outside force on
 * `at`, expressed as `must_not` ranges.
 *
 * Documents missing the field do not match a range clause, so `must_not` keeps
 * them — which is the point: an unknown-dated norm stays in the result set and
 * is reported as `unknown`. Filtering it out would silently hide law from the
 * agent, and silence is indistinguishable from absence.
 */
export function inForceExclusionClauses(at: string): Record<string, unknown>[] {
  return [{ range: { in_force_until: { lt: at } } }, { range: { in_force_from: { gt: at } } }];
}
