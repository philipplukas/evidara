import { describe, expect, it } from "vitest";
import {
  describeComboboxStatus,
  filterComboboxChoices,
  normalizeSearchText,
} from "./comboboxFilter";

/**
 * #666: the jurisdiction picker rendered 250 of 2,169 options, alphabetically
 * truncated at "Bovernier", with no search and no indication anything was
 * missing. These tests pin the two properties that make the replacement honest.
 */

const REGISTRY = [
  { id: "jur_ch_zh", name: "Kanton Zürich (ch-zh)" },
  { id: "jur_ch_federal", name: "Swiss Confederation (ch)" },
  { id: "jur_ch_be", name: "Kanton Bern (ch-be)" },
  { id: "jur_de", name: "Germany (de)" },
  { id: "jur_gem_aarau", name: "Aarau (ch-gemeinde-4001)" },
];

describe("normalizeSearchText", () => {
  it("strips diacritics so an ASCII keyboard reaches Zürich", () => {
    expect(normalizeSearchText("Zürich")).toBe("zurich");
    expect(normalizeSearchText("  GENÈVE ")).toBe("geneve");
  });
});

describe("filterComboboxChoices", () => {
  it("finds Zürich by its ASCII spelling — the milestone's own jurisdiction", () => {
    const result = filterComboboxChoices(REGISTRY, "zurich", 50);
    expect(result.visible.map((choice) => choice.id)).toContain("jur_ch_zh");
  });

  it("finds a jurisdiction by pasted id, not only by name", () => {
    const result = filterComboboxChoices(REGISTRY, "jur_ch_federal", 50);
    expect(result.visible).toHaveLength(1);
    expect(result.visible[0].id).toBe("jur_ch_federal");
  });

  it("ranks prefix matches above interior matches", () => {
    const result = filterComboboxChoices(
      [
        { id: "b", name: "Oberkanton Bern" },
        { id: "a", name: "Bern" },
      ],
      "bern",
      50,
    );
    expect(result.visible[0].id).toBe("a");
  });

  it("reports truncation rather than hiding it", () => {
    const many = Array.from({ length: 2169 }, (_, index) => ({
      id: `jur_${index}`,
      name: `Jurisdiction ${index}`,
    }));
    const result = filterComboboxChoices(many, "", 50);

    expect(result.visible).toHaveLength(50);
    expect(result.matchCount).toBe(2169);
    expect(result.truncated).toBe(true);
  });
});

describe("describeComboboxStatus", () => {
  it("never presents a truncated option list as the whole registry", () => {
    const status = describeComboboxStatus({
      query: "",
      matchCount: 2169,
      visibleCount: 50,
      loadedCount: 2169,
      totalCount: 2169,
    });
    expect(status).toBe("Showing 50 of 2169 matches — keep typing to narrow");
  });

  it("says so when the fetch itself came back short — the exact 250-of-2169 bug", () => {
    const status = describeComboboxStatus({
      query: "",
      matchCount: 250,
      visibleCount: 50,
      loadedCount: 250,
      totalCount: 2169,
    });
    expect(status).toContain("searching only 250 of 2169 records");
  });

  it("reports a complete small list plainly", () => {
    expect(
      describeComboboxStatus({
        query: "",
        matchCount: 42,
        visibleCount: 42,
        loadedCount: 42,
        totalCount: 42,
      }),
    ).toBe("42 options");
  });

  it("distinguishes 'no match for this query' from 'nothing exists'", () => {
    expect(
      describeComboboxStatus({
        query: "zzz",
        matchCount: 0,
        visibleCount: 0,
        loadedCount: 2169,
        totalCount: 2169,
      }),
    ).toBe("No match for “zzz” in 2169 options");
  });
});
