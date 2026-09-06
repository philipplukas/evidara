import { describe, expect, it } from "vitest";
import { formatCount, orderStages, totalDurationMs } from "./StageTimeline";

type Stage = Parameters<typeof orderStages>[0][number];

const stage = (name: Stage["name"], duration_ms: number, extra: Partial<Stage> = {}): Stage =>
  ({ name, duration_ms, ...extra }) as Stage;

describe("orderStages", () => {
  it("puts the stages in execution order regardless of arrival order", () => {
    const ordered = orderStages([
      stage("finalize", 8),
      stage("normalize", 120),
      stage("enrich", 310),
      stage("sectionize", 45),
    ]);

    expect(ordered.map((s) => s.name)).toEqual(["normalize", "sectionize", "enrich", "finalize"]);
  });

  it("does not mutate its input", () => {
    const input = [stage("finalize", 8), stage("normalize", 120)];
    orderStages(input);
    expect(input.map((s) => s.name)).toEqual(["finalize", "normalize"]);
  });
});

describe("formatCount", () => {
  /**
   * The load-bearing case. `items_in`/`items_out` are absent when the stage did
   * not measure them, and `0` is a claim about the work. Rendering absence as
   * `0` is the silent-zero failure this repo has paid for repeatedly (#605,
   * #675, #713).
   *
   * Change the `typeof` check to a truthiness check and this fails — because a
   * genuine `0` would then also render as a dash, collapsing the other
   * direction.
   */
  it("renders an unmeasured count as a dash, never as 0", () => {
    expect(formatCount(undefined)).toBe("—");
    expect(formatCount(null)).toBe("—");
  });

  it("renders a measured zero as 0, not as a dash", () => {
    expect(formatCount(0)).toBe("0");
  });

  it("renders a measured count", () => {
    expect(formatCount(24)).toBe("24");
  });
});

describe("totalDurationMs", () => {
  it("sums the measured durations", () => {
    expect(totalDurationMs([stage("normalize", 120), stage("finalize", 8)])).toBe(128);
  });

  it("is 0 for an empty ledger", () => {
    expect(totalDurationMs([])).toBe(0);
  });
});
