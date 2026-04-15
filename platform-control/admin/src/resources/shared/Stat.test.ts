import { describe, expect, it } from "vitest";
import { successRateTone } from "./Stat";

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
});
