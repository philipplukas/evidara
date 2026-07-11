/**
 * Unit coverage for the corrections state machine surfaced by `CorrectionShow`.
 *
 * `correctionTransitions` mirrors the server contract (PR #440) that decides
 * which lifecycle buttons the detail page offers. Keeping it a pure export lets
 * the legal-transition matrix be proven without rendering the ra-core show
 * controller or standing up a router.
 */
import { describe, expect, it } from "vitest";
import { correctionTransitions } from "./CorrectionShow";

describe("correctionTransitions", () => {
  it("offers apply + reject from pending", () => {
    expect(correctionTransitions("pending")).toEqual(["applied", "rejected"]);
  });

  it("offers only supersede from applied", () => {
    expect(correctionTransitions("applied")).toEqual(["superseded"]);
  });

  it("offers no transitions from terminal states", () => {
    expect(correctionTransitions("rejected")).toEqual([]);
    expect(correctionTransitions("superseded")).toEqual([]);
  });
});
