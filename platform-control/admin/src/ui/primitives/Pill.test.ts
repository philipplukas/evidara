import { describe, expect, it } from "vitest";
import { pillLabel } from "./Pill";

describe("pillLabel", () => {
  it("joins multi-child JSX without React's array commas", () => {
    // Dashboard bug: `<Pill>{status}: {count}</Pill>` hands React the array
    // ["failed", ": ", 1], and the old `String(children)` rendered the pill as
    // "failed,: ,1".
    expect(pillLabel(["failed", ": ", 1])).toBe("failed: 1");
    expect(pillLabel(["ok", ": ", 0])).toBe("ok: 0");
    expect(pillLabel(["in progress", ": ", 12])).toBe("in progress: 12");
  });

  it("passes single string and number children through unchanged", () => {
    expect(pillLabel("completed")).toBe("completed");
    expect(pillLabel(3)).toBe("3");
  });

  it("drops nullish and boolean children instead of printing them", () => {
    expect(pillLabel(null)).toBe("");
    expect(pillLabel(undefined)).toBe("");
    expect(pillLabel(["blocked", null, ": ", false, 2])).toBe("blocked: 2");
  });

  it("flattens nested arrays", () => {
    expect(pillLabel([["a", "b"], ": ", 1])).toBe("ab: 1");
  });
});
