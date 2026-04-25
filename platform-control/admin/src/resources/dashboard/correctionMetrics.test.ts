import { describe, expect, it } from "vitest";
import type { CorrectionMetricsResponse } from "../../lib/admin/dataProvider";
import {
  formatWeekLabel,
  isMetricsEmpty,
  percentOfTotal,
  summarizeMetrics,
  topOperators,
  weekTotal,
} from "./correctionMetrics";

const baseResponse: CorrectionMetricsResponse = {
  since: "2026-04-06",
  weeks: [
    {
      week_start: "2026-04-06",
      by_entity_type: { commentary_insight: 4 },
      by_correction_type: {
        field_edit: 3,
        annotation: 1,
      },
      operator_throughput: [
        { operator_id: "op_anna", applied: 2 },
        { operator_id: "op_ben", applied: 1 },
      ],
      rescore_outcomes: { changed: 0, unchanged: 0, failed: 0 },
    },
    {
      week_start: "2026-04-13",
      by_entity_type: { commentary_insight: 3 },
      by_correction_type: {
        field_edit: 1,
        rescore_request: 2,
      },
      operator_throughput: [{ operator_id: "op_anna", applied: 1 }],
      rescore_outcomes: { changed: 1, unchanged: 1, failed: 0 },
    },
    {
      week_start: "2026-04-20",
      by_entity_type: {},
      by_correction_type: {},
      operator_throughput: [],
      rescore_outcomes: { changed: 0, unchanged: 0, failed: 0 },
    },
  ],
};

describe("correction metrics helpers", () => {
  it("summarises totals across the entire window", () => {
    const totals = summarizeMetrics(baseResponse);
    expect(totals.totalCorrections).toBe(7);
    expect(totals.totalRescores).toBe(2);
    expect(totals.rescoreOutcomes).toEqual({ changed: 1, unchanged: 1, failed: 0 });
    expect(totals.uniqueOperators).toBe(2);
    // Applied count sums every operator_throughput row across the window.
    expect(totals.totalApplied).toBe(4);
  });

  it("treats an all-zero response as empty", () => {
    expect(
      isMetricsEmpty({
        since: "2026-04-06",
        weeks: [
          {
            week_start: "2026-04-06",
            by_entity_type: {},
            by_correction_type: {},
            operator_throughput: [],
            rescore_outcomes: { changed: 0, unchanged: 0, failed: 0 },
          },
        ],
      }),
    ).toBe(true);
  });

  it("treats any non-zero week as populated", () => {
    expect(isMetricsEmpty(baseResponse)).toBe(false);
  });

  it("sums per-correction-type counts within one bucket", () => {
    expect(weekTotal(baseResponse.weeks[0]!)).toBe(4);
    expect(weekTotal(baseResponse.weeks[1]!)).toBe(3);
    expect(weekTotal(baseResponse.weeks[2]!)).toBe(0);
  });

  it("computes percentage of total without dividing by zero", () => {
    expect(percentOfTotal(2, 4)).toBe(50);
    expect(percentOfTotal(1, 0)).toBe(0);
    expect(percentOfTotal(0, 5)).toBe(0);
  });

  it("formats ISO week-start dates as short labels", () => {
    // The exact rendering varies by locale, but it must include the day
    // ("13") and not be the raw date string.
    const formatted = formatWeekLabel("2026-04-13");
    expect(formatted).toContain("13");
    expect(formatted).not.toBe("2026-04-13");
  });

  it("falls back to the raw string when the date is invalid", () => {
    expect(formatWeekLabel("not-a-date")).toBe("not-a-date");
  });

  it("ranks top operators across the window with ties broken alphabetically", () => {
    const ranked = topOperators(baseResponse, 5);
    expect(ranked).toEqual([
      { operator_id: "op_anna", applied: 3 },
      { operator_id: "op_ben", applied: 1 },
    ]);
  });

  it("respects the limit when reporting top operators", () => {
    const many: CorrectionMetricsResponse = {
      since: "2026-04-06",
      weeks: [
        {
          week_start: "2026-04-06",
          by_entity_type: {},
          by_correction_type: {},
          operator_throughput: [
            { operator_id: "op_a", applied: 5 },
            { operator_id: "op_b", applied: 4 },
            { operator_id: "op_c", applied: 3 },
          ],
          rescore_outcomes: { changed: 0, unchanged: 0, failed: 0 },
        },
      ],
    };
    expect(topOperators(many, 2)).toEqual([
      { operator_id: "op_a", applied: 5 },
      { operator_id: "op_b", applied: 4 },
    ]);
  });
});
