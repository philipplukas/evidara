import { describe, expect, it } from "vitest";
import type { CorrectionRecord } from "../../lib/admin/dataProvider";
import {
  buildCorrectionFollowUpHref,
  CORRECTION_STATUS_LABEL,
  CORRECTION_TYPE_LABEL,
  correctionStatusToLevel,
  DEFAULT_CORRECTION_QUEUE_FILTER,
  describeTarget,
  summarizeRationale,
} from "./correctionQueue";

const baseCorrection: CorrectionRecord = {
  id: "cor_01",
  correction_id: "cor_01",
  target_entity_type: "commentary_insight",
  target_entity_id: "ins_01",
  correction_type: "field_edit",
  payload: { claim: "x" },
  original_snapshot: { claim: "y" },
  operator_id: "op_anna@evidara.dev",
  pipeline_run_id: null,
  rationale: "Tightened wording.",
  status: "pending",
  created_at: "2026-04-25T09:14:02Z",
  applied_at: null,
};

describe("correction queue helpers", () => {
  it("defaults the queue filter to status=pending", () => {
    expect(DEFAULT_CORRECTION_QUEUE_FILTER).toEqual({ status: "pending" });
  });

  it("labels every documented correction status and type", () => {
    // Sanity that adding a new enum value won't silently render a raw key.
    expect(CORRECTION_STATUS_LABEL.pending).toBe("Pending");
    expect(CORRECTION_STATUS_LABEL.applied).toBe("Applied");
    expect(CORRECTION_TYPE_LABEL.field_edit).toBe("Field edit");
    expect(CORRECTION_TYPE_LABEL.rescore_request).toBe("Rescore request");
  });

  it("colours pending neutral-ish and applied healthy", () => {
    expect(correctionStatusToLevel("pending")).toBe("info");
    expect(correctionStatusToLevel("applied")).toBe("healthy");
    expect(correctionStatusToLevel("rejected")).toBe("degraded");
    expect(correctionStatusToLevel("superseded")).toBe("degraded");
  });

  it("describes the target entity label and id", () => {
    expect(describeTarget(baseCorrection)).toBe("Commentary insight · ins_01");
  });

  it("truncates long rationales without slicing mid-word", () => {
    const long =
      "This rationale spans more than the maximum allowed length so we need to ensure the helper trims it cleanly without cutting words in half.";
    const result = summarizeRationale(long, 60);
    expect(result.endsWith("…")).toBe(true);
    expect(result.length).toBeLessThanOrEqual(61);
    // The truncation must land on a word that exists in the original — i.e.
    // the helper should not slice off a partial token that doesn't appear
    // verbatim in the source rationale.
    const lastWord = result.slice(0, -1).trim().split(/\s+/).pop() ?? "";
    expect(long).toContain(lastWord);
  });

  it("returns the original rationale when within the limit", () => {
    expect(summarizeRationale("Short rationale.")).toBe("Short rationale.");
  });

  it("builds a follow-up link for commentary-insight targets only", () => {
    expect(buildCorrectionFollowUpHref(baseCorrection)).toBe("/commentary-insights/ins_01");
    expect(
      buildCorrectionFollowUpHref({
        ...baseCorrection,
        target_entity_type: "search_projection",
      }),
    ).toBeNull();
  });
});
