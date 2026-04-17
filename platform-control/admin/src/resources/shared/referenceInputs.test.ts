import { describe, expect, it } from "vitest";
import {
  describeAuthoritySelectState,
  describeJurisdictionSelectState,
  referenceSlugValidator,
} from "./ReferenceInputs";

describe("ReferenceInputs helpers", () => {
  it("validates lowercase slug input", () => {
    expect(
      referenceSlugValidator("federal-supreme-court", {} as never, {} as never),
    ).toBeUndefined();
    expect(referenceSlugValidator("Federal Supreme Court", {} as never, {} as never)).toBe(
      "Use lowercase letters, numbers, and hyphens only.",
    );
  });

  it("describes empty jurisdiction state clearly", () => {
    expect(
      describeJurisdictionSelectState({
        isPending: false,
        hasError: false,
        choiceCount: 0,
      }),
    ).toEqual({
      severity: "warning",
      title: "No jurisdictions available",
      message: "Seed at least one jurisdiction before creating or editing authorities.",
    });
  });

  it("describes missing authority choices based on scope", () => {
    expect(
      describeAuthoritySelectState({
        isPending: false,
        hasError: false,
        choiceCount: 0,
        jurisdictionId: "ch-federal",
      }),
    ).toEqual({
      severity: "warning",
      title: "No matching authorities",
      message:
        "Create a scoped authority for this jurisdiction, or switch to a jurisdiction that already has one.",
    });
  });
});
