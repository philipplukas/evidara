import { describe, expect, it } from "vitest";
import { filterByDensity } from "@/lib/metadata-visibility";
import type { MetadataField } from "@/lib/types";

// German labels on purpose: the BFF localizes them, and #787 was a set of
// English label regexes that could never match one. Nothing in this module
// may read `label` again.
const FIELDS: MetadataField[] = [
  { label: "Zuständigkeit", value: "Schweiz", visibility: "always" },
  { label: "Behörde", value: "Bundesrat", visibility: "default" },
  { label: "Quelle", value: "Amtliche Quelle", visibility: "expanded" },
];

describe("filterByDensity", () => {
  it("keeps only 'always' rows at compact density", () => {
    expect(filterByDensity(FIELDS, "compact").map((f) => f.label)).toEqual(["Zuständigkeit"]);
  });

  it("drops only 'expanded' rows at default density", () => {
    expect(filterByDensity(FIELDS, "default").map((f) => f.label)).toEqual([
      "Zuständigkeit",
      "Behörde",
    ]);
  });

  it("keeps every row at expanded density", () => {
    expect(filterByDensity(FIELDS, "expanded")).toHaveLength(3);
  });

  it("filters on visibility alone, never on the localized label", () => {
    // The same rows, relabelled with the English words the deleted rules
    // matched. The outcome must be identical — if it is not, a label
    // heuristic has come back.
    const relabelled = FIELDS.map((field, i) => ({
      ...field,
      label: ["Jurisdiction", "Court", "Obscure field"][i] as string,
    }));

    for (const density of ["compact", "default", "expanded"] as const) {
      expect(filterByDensity(relabelled, density).map((f) => f.visibility)).toEqual(
        filterByDensity(FIELDS, density).map((f) => f.visibility),
      );
    }
  });
});
