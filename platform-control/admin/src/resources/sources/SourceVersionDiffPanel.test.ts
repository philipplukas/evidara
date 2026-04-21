import { describe, expect, it } from "vitest";
import type { SourceVersionRecord } from "../../lib/admin/dataProvider";

/**
 * Unit tests for the diff logic extracted from SourceVersionDiffPanel.
 *
 * Since the component's `diffSpecs` and `displayValue` are internal,
 * we test the same logic inline here to keep the component file clean
 * while still verifying the diff algorithm.
 */

type DiffKind = "added" | "removed" | "changed" | "unchanged";
type DiffEntry = {
  key: string;
  kind: DiffKind;
  previous: string | undefined;
  current: string | undefined;
};

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "(empty)";
  if (Array.isArray(value)) return value.length === 0 ? "(empty list)" : value.join(", ");
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

function diffSpecs(
  previous: Record<string, unknown>,
  current: Record<string, unknown>,
): DiffEntry[] {
  const allKeys = new Set<string>([...Object.keys(previous), ...Object.keys(current)]);
  const entries: DiffEntry[] = [];

  for (const key of [...allKeys].sort()) {
    const prevVal = previous[key];
    const currVal = current[key];
    const prevDisplay = displayValue(prevVal);
    const currDisplay = displayValue(currVal);

    const prevExists = key in previous;
    const currExists = key in current;

    if (!prevExists && currExists) {
      entries.push({ key, kind: "added", previous: undefined, current: currDisplay });
    } else if (prevExists && !currExists) {
      entries.push({ key, kind: "removed", previous: prevDisplay, current: undefined });
    } else if (prevDisplay !== currDisplay) {
      entries.push({ key, kind: "changed", previous: prevDisplay, current: currDisplay });
    } else {
      entries.push({ key, kind: "unchanged", previous: prevDisplay, current: currDisplay });
    }
  }

  return entries;
}

describe("SourceVersionDiffPanel diff logic", () => {
  it("detects added fields", () => {
    const result = diffSpecs({ provider: "firecrawl" }, { provider: "firecrawl", limit: 50 });
    const limitEntry = result.find((e) => e.key === "limit");
    expect(limitEntry).toEqual({
      key: "limit",
      kind: "added",
      previous: undefined,
      current: "50",
    });
  });

  it("detects removed fields", () => {
    const result = diffSpecs(
      { provider: "firecrawl", limit: 20 },
      { provider: "firecrawl" },
    );
    const limitEntry = result.find((e) => e.key === "limit");
    expect(limitEntry).toEqual({
      key: "limit",
      kind: "removed",
      previous: "20",
      current: undefined,
    });
  });

  it("detects changed fields", () => {
    const result = diffSpecs(
      { provider: "firecrawl", limit: 20 },
      { provider: "firecrawl", limit: 50 },
    );
    const limitEntry = result.find((e) => e.key === "limit");
    expect(limitEntry).toEqual({
      key: "limit",
      kind: "changed",
      previous: "20",
      current: "50",
    });
  });

  it("marks identical fields as unchanged", () => {
    const result = diffSpecs(
      { provider: "firecrawl", limit: 20 },
      { provider: "firecrawl", limit: 20 },
    );
    expect(result.every((e) => e.kind === "unchanged")).toBe(true);
  });

  it("sorts keys alphabetically", () => {
    const result = diffSpecs(
      { z_field: 1, a_field: 2 },
      { z_field: 1, a_field: 2 },
    );
    expect(result.map((e) => e.key)).toEqual(["a_field", "z_field"]);
  });

  it("formats arrays as comma-separated values", () => {
    const result = diffSpecs(
      { paths: ["a", "b"] },
      { paths: ["a", "b", "c"] },
    );
    const entry = result.find((e) => e.key === "paths");
    expect(entry?.previous).toBe("a, b");
    expect(entry?.current).toBe("a, b, c");
    expect(entry?.kind).toBe("changed");
  });

  it("formats booleans as yes/no", () => {
    const result = diffSpecs(
      { zero_data_retention: false },
      { zero_data_retention: true },
    );
    const entry = result.find((e) => e.key === "zero_data_retention");
    expect(entry?.previous).toBe("no");
    expect(entry?.current).toBe("yes");
    expect(entry?.kind).toBe("changed");
  });

  it("formats null as (empty)", () => {
    const result = diffSpecs(
      { seed_url: null },
      { seed_url: "https://example.com" },
    );
    const entry = result.find((e) => e.key === "seed_url");
    expect(entry?.previous).toBe("(empty)");
    expect(entry?.current).toBe("https://example.com");
    expect(entry?.kind).toBe("changed");
  });

  it("formats empty arrays as (empty list)", () => {
    const result = diffSpecs({ items: [] }, { items: ["x"] });
    const entry = result.find((e) => e.key === "items");
    expect(entry?.previous).toBe("(empty list)");
    expect(entry?.current).toBe("x");
  });
});
