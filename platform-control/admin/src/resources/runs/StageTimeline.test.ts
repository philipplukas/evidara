import { describe, expect, it } from "vitest";
import { formatCount, formatDuration, orderStages, totalDurationUs } from "./StageTimeline";

type Stage = Parameters<typeof orderStages>[0][number];

const stage = (name: Stage["name"], duration_us: number, extra: Partial<Stage> = {}): Stage =>
  ({ name, duration_us, ...extra }) as Stage;

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

describe("totalDurationUs", () => {
  it("sums the measured durations", () => {
    expect(totalDurationUs([stage("normalize", 120), stage("finalize", 8)])).toBe(128);
  });

  it("is 0 for an empty ledger", () => {
    expect(totalDurationUs([])).toBe(0);
  });
});

describe("formatDuration", () => {
  /**
   * The reason the wire unit is microseconds. Rendering sub-millisecond work as
   * "0 ms" reads as "nothing was measured" rather than "fast", which is the
   * absence-versus-zero conflation the whole feature exists to avoid.
   *
   * Make this round to milliseconds and every one of these collapses to "0 ms".
   */
  it("keeps sub-millisecond work legible instead of rounding it to 0 ms", () => {
    expect(formatDuration(0)).toBe("0 µs");
    expect(formatDuration(1)).toBe("1 µs");
    expect(formatDuration(842)).toBe("842 µs");
    expect(formatDuration(999)).toBe("999 µs");
  });

  it("switches to milliseconds at 1 ms, keeping one decimal while it matters", () => {
    expect(formatDuration(1_000)).toBe("1.0 ms");
    expect(formatDuration(4_500)).toBe("4.5 ms");
    expect(formatDuration(45_000)).toBe("45 ms");
  });

  it("switches to seconds at a million microseconds", () => {
    expect(formatDuration(1_000_000)).toBe("1.00 s");
    expect(formatDuration(12_340_000)).toBe("12.34 s");
  });

  it("renders a measured zero as 0 µs — not a dash, which marks an absent count", () => {
    expect(formatDuration(0)).toBe("0 µs");
    expect(formatDuration(0)).not.toBe(formatCount(undefined));
  });
});
