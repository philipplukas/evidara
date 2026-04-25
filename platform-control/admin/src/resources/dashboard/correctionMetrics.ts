/**
 * Pure helpers for the correction metrics widget (`/v1/corrections/metrics`).
 *
 * These are split out from `CorrectionMetricsCard.tsx` so the totals,
 * empty-state predicate, and label maps can be unit-tested under the
 * node-environment Vitest config (the React component is the thin shell).
 *
 * The shape mirrors the platform-control read model: one bucket per ISO
 * week, pre-seeded by the backend so empty weeks render as zero cards.
 * See #432 for the dashboard rationale.
 */

import type {
  CorrectionMetricsResponse,
  CorrectionMetricsWeek,
  CorrectionTargetEntityType,
  CorrectionType,
} from "../../lib/admin/dataProvider";

/**
 * Display labels for the correction-type bar in each week card.
 *
 * Kept in sync with `CORRECTION_TYPE_LABEL` from `corrections/correctionQueue.ts`
 * but duplicated locally so the dashboard module doesn't import a sibling
 * resource (which would force `'use client'` / Next.js plumbing into the
 * test surface). The narrow surface — five enum values — makes the duplication
 * cheap to keep aligned.
 */
export const METRICS_CORRECTION_TYPE_LABEL: Record<CorrectionType, string> = {
  field_edit: "Field edit",
  annotation: "Annotation",
  reject: "Reject",
  rescore_request: "Rescore",
};

export const METRICS_TARGET_LABEL: Record<CorrectionTargetEntityType, string> = {
  commentary_insight: "Commentary",
  search_projection: "Search projection",
  document: "Document",
  section: "Section",
  citation: "Citation",
};

export type CorrectionMetricsTotals = {
  totalCorrections: number;
  totalApplied: number;
  totalRescores: number;
  rescoreOutcomes: { changed: number; unchanged: number; failed: number };
  /** Distinct operators with at least one applied correction across the window. */
  uniqueOperators: number;
};

/**
 * Compute the summary stats shown above the per-week timeline.
 *
 * Aggregating in the browser (rather than asking the API for another
 * endpoint) keeps the read model compact. The numbers are derived from
 * the same week buckets the table renders, so the totals can never
 * disagree with the visible breakdown.
 */
export function summarizeMetrics(response: CorrectionMetricsResponse): CorrectionMetricsTotals {
  let totalCorrections = 0;
  let totalRescores = 0;
  const rescoreOutcomes = { changed: 0, unchanged: 0, failed: 0 };
  const operators = new Set<string>();
  let totalApplied = 0;

  for (const week of response.weeks) {
    for (const count of Object.values(week.by_correction_type)) {
      totalCorrections += count;
    }
    totalRescores += week.by_correction_type.rescore_request ?? 0;
    rescoreOutcomes.changed += week.rescore_outcomes.changed;
    rescoreOutcomes.unchanged += week.rescore_outcomes.unchanged;
    rescoreOutcomes.failed += week.rescore_outcomes.failed;
    for (const entry of week.operator_throughput) {
      operators.add(entry.operator_id);
      totalApplied += entry.applied;
    }
  }

  return {
    totalCorrections,
    totalApplied,
    totalRescores,
    rescoreOutcomes,
    uniqueOperators: operators.size,
  };
}

/**
 * `true` when the entire response carries zero corrections — used to
 * render the empty state instead of a row of zero pills.
 */
export function isMetricsEmpty(response: CorrectionMetricsResponse): boolean {
  return response.weeks.every(
    (week) =>
      Object.keys(week.by_correction_type).length === 0 &&
      Object.keys(week.by_entity_type).length === 0 &&
      week.operator_throughput.length === 0 &&
      week.rescore_outcomes.changed === 0 &&
      week.rescore_outcomes.unchanged === 0 &&
      week.rescore_outcomes.failed === 0,
  );
}

/** Sum the per-correction-type counts in one week bucket. */
export function weekTotal(week: CorrectionMetricsWeek): number {
  let total = 0;
  for (const count of Object.values(week.by_correction_type)) {
    total += count;
  }
  return total;
}

/**
 * Round-trip a percentage onto a 0..100 integer used for the inline bars.
 * Returns 0 when `total` is 0 so empty weeks don't render NaN-width bars.
 */
export function percentOfTotal(count: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((count / total) * 100);
}

/**
 * Format an ISO week-start date as a short "Apr 13" / "Dec 30" label.
 * Falls back to the raw string when `Intl.DateTimeFormat` is unavailable
 * (which shouldn't happen in production but keeps the helper test-safe).
 */
export function formatWeekLabel(weekStart: string, locale = "en-CH"): string {
  const date = new Date(`${weekStart}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return weekStart;
  try {
    return new Intl.DateTimeFormat(locale, {
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    }).format(date);
  } catch {
    return weekStart;
  }
}

/**
 * Ranked top operators across the entire window. Used by the "operator
 * throughput" sidebar so a 12-week window reads as a single leaderboard,
 * not 12 disjoint per-week lists.
 */
export function topOperators(
  response: CorrectionMetricsResponse,
  limit = 5,
): Array<{ operator_id: string; applied: number }> {
  const totals = new Map<string, number>();
  for (const week of response.weeks) {
    for (const entry of week.operator_throughput) {
      totals.set(entry.operator_id, (totals.get(entry.operator_id) ?? 0) + entry.applied);
    }
  }
  return [...totals.entries()]
    .map(([operator_id, applied]) => ({ operator_id, applied }))
    .sort((a, b) =>
      b.applied !== a.applied ? b.applied - a.applied : a.operator_id.localeCompare(b.operator_id),
    )
    .slice(0, Math.max(limit, 0));
}
