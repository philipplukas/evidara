import { describe, expect, it } from "vitest";
import { formatBuildLabel } from "./buildLabel";

const SHA = "4932ec2c29ee31ab591bd9dbb9caa3f59a1e0b13";

describe("formatBuildLabel", () => {
  it("renders the 8-char sha and the UTC calendar day", () => {
    expect(formatBuildLabel(SHA, "2026-09-06T10:25:00Z")).toBe("4932ec2c · 2026-09-06");
  });

  it("renders the sha alone when no build date was baked", () => {
    expect(formatBuildLabel(SHA, undefined)).toBe("4932ec2c");
  });

  // Guard: the caller renders nothing for null. Returning "" instead would put a
  // blank where a version belongs, which reads as "this build has no version"
  // rather than "not applicable" — and an empty <a> is still a clickable element.
  it.each([undefined, "", "   "])("returns null (not '') for sha %s", (sha) => {
    expect(formatBuildLabel(sha, "2026-09-06T10:25:00Z")).toBeNull();
  });

  // Guard: degrade to the sha rather than printing a fragment beside it.
  it.each([
    "not-a-date",
    "2026-09",
    "06/09/2026",
    "",
    "   ",
  ])("ignores an unparseable date %s", (date) => {
    expect(formatBuildLabel(SHA, date)).toBe("4932ec2c");
  });

  it("does not localise — the day is the UTC one, verbatim", () => {
    // A build timestamp is a fact about the release, not about the reader's
    // timezone. Two operators comparing notes must read the same string.
    expect(formatBuildLabel(SHA, "2026-09-06T23:59:59Z")).toBe("4932ec2c · 2026-09-06");
  });

  it("tolerates a sha shorter than 8 characters rather than padding it", () => {
    expect(formatBuildLabel("abc", undefined)).toBe("abc");
  });
});
