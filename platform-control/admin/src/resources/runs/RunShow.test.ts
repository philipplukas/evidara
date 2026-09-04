import { describe, expect, it } from "vitest";
import { buildRunRecord } from "../../lib/admin/__fixtures__/runs";
import type { RunRecord } from "../../lib/admin/dataProvider";
import type { LegalSearchHandoff } from "../../lib/admin/navigationContext";
import { buildRunHandoffGuidance, describeRunReplay, describeRunScope } from "./RunShow";
import { formatDuration } from "./RunShowV2";

const baseRun = buildRunRecord({
  id: "run-123",
  run_id: "run-123",
  mode: "production",
  status: "running",
  started_at: "2026-04-10T09:00:00Z",
  completed_at: null,
  artifacts_count: 3,
  created_at: "2026-04-10T08:59:00Z",
  updated_at: "2026-04-10T09:15:00Z",
});

const handoff: LegalSearchHandoff = {
  hasOrigin: true,
  returnToUrl: "http://localhost:3101/?q=Art.%20754",
  query: "Art. 754 OR Verantwortlichkeit",
  scopeLabel: "Swiss federal law",
  selectedId: "decision-1",
};

describe("RunShow handoff guidance", () => {
  it("frames the legal-search context for run detail operators", () => {
    const guidance = buildRunHandoffGuidance(baseRun, handoff);

    expect(guidance?.whyYouAreHere).toContain("legal search");
    expect(guidance?.whyYouAreHere).toContain("Selected item: decision-1");
    expect(guidance?.whatToCheckNext).toContain("selected item (decision-1)");
    expect(guidance?.whatToCheckNext).toContain("source/version pair");
  });
});

describe("formatDuration", () => {
  it("formats a normal elapsed time", () => {
    expect(
      formatDuration({
        ...baseRun,
        started_at: "2026-07-18T17:45:24.412Z",
        completed_at: "2026-07-18T17:45:24.685Z",
      }),
    ).toBe("273ms");
  });

  it("returns a placeholder when the run has not finished", () => {
    expect(formatDuration({ ...baseRun, completed_at: null })).toBe("\u2014");
  });

  it("refuses to render a negative duration", () => {
    // The failed ZH repro run rendered "Duration -1ms" on the run detail page:
    // completed_at preceded started_at. Say nothing rather than say something
    // impossible.
    expect(
      formatDuration({
        ...baseRun,
        started_at: "2026-07-17T20:16:20.945182Z",
        completed_at: "2026-07-17T20:16:20.944165Z",
      }),
    ).toBe("\u2014");
  });
});

describe("detail-only fields on a record that may be a list row", () => {
  /**
   * React-admin seeds `useShowController` from the list cache. That cache holds
   * `RunListItemResponse` rows, which carry neither `scope` nor `replay`, so on a
   * row click the detail page renders a record whose static `RunResponse` type is
   * a lie for one frame. `run.scope.kind` threw there and the whole page fell
   * behind react-admin's "Something went wrong" boundary — reachable only by
   * clicking a row, never by loading the URL directly, which is why no fixture
   * caught it.
   */
  it("does not throw on a list-shaped record and does not invent a scope", () => {
    // Deliberately the shape react-admin actually hands over: a list row, with
    // no `scope` key at all. The cast is the point — TypeScript believes this is
    // a `RunResponse` at that moment and it is not.
    const listShaped = { run_id: "run-123" } as Partial<RunRecord>;
    expect(describeRunScope(listShaped)).toEqual({ value: "not loaded", known: false });
  });

  it("refuses to claim 'not a replay' before the detail response has landed", () => {
    // `replay` is legitimately null on a non-replay run, so its own absence
    // cannot distinguish "not a replay" from "not fetched yet". Saying the former
    // is an assertion about the run we have no field to support.
    expect(describeRunReplay({})).toEqual({ value: "not loaded", known: false });
    expect(describeRunReplay({ scope: { kind: "full_source" }, replay: null })).toEqual({
      value: "not a replay",
      known: true,
    });
  });

  it("names the replay mode and its parent once the detail response is in", () => {
    expect(
      describeRunReplay({
        scope: { kind: "full_source" },
        replay: { mode: "backfill", parent_run_id: "run_parent" },
      }),
    ).toEqual({ value: "backfill \u00b7 parent run_parent", known: true });
    expect(describeRunScope({ scope: { kind: "time_window" } })).toEqual({
      value: "time_window",
      known: true,
    });
  });
});
