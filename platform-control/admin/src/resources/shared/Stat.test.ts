import { describe, expect, it } from "vitest";
import { statToneBorder, successRateTone } from "./Stat";
import { adminLevelBorder } from "./StatusBadge";

describe("statToneBorder", () => {
  it("matches StatusBadge border tokens for stat tones", () => {
    expect(statToneBorder("success")).toBe(adminLevelBorder("healthy"));
    expect(statToneBorder("error")).toBe(adminLevelBorder("critical"));
    expect(statToneBorder("warning")).toBe(adminLevelBorder("degraded"));
    expect(statToneBorder("info")).toBe(adminLevelBorder("info"));
    expect(statToneBorder("default")).toBe(adminLevelBorder("neutral"));
  });
});

describe("successRateTone", () => {
  it("treats dash as unknown", () => {
    expect(successRateTone("-")).toBe("default");
  });

  it("flags rates under eighty percent as critical tone", () => {
    expect(successRateTone("40%")).toBe("error");
    expect(successRateTone("79%")).toBe("error");
  });

  it("warns between eighty and ninety-four percent", () => {
    expect(successRateTone("80%")).toBe("warning");
    expect(successRateTone("94%")).toBe("warning");
  });

  it("uses success tone at ninety-five percent or higher", () => {
    expect(successRateTone("95%")).toBe("success");
    expect(successRateTone("100%")).toBe("success");
  });

  it("treats whitespace-only and non-numeric percentages as default", () => {
    expect(successRateTone("")).toBe("default");
    expect(successRateTone("   ")).toBe("default");
    expect(successRateTone("n/a")).toBe("default");
  });

  it("parses integers after stripping percent sign", () => {
    expect(successRateTone("81")).toBe("warning");
    expect(successRateTone(" 94% ")).toBe("warning");
  });

  /** Boundary table: <80 critical, 80–94 warning, ≥95 success (see Stat.tsx). */
  it("pins boundary at seventy-nine vs eighty percent", () => {
    expect(successRateTone("79%")).toBe("error");
    expect(successRateTone("80%")).toBe("warning");
  });

  it("pins boundary at ninety-four vs ninety-five percent", () => {
    expect(successRateTone("94%")).toBe("warning");
    expect(successRateTone("95%")).toBe("success");
  });
});
