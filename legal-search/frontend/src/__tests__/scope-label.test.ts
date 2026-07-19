/**
 * Scope label derivation (#648) — the workspace reducer is pure and cannot
 * translate, so it must not fabricate a display label. `Results for "…"` used
 * to be stored in English and rendered verbatim in the German UI.
 */

import { describe, expect, it } from "vitest";
import { describeResultSetScope } from "@/lib/scope-label";
import type { ResultSet } from "@/lib/types";

const t = (key: string, values?: Record<string, string>) =>
  key === "resultsFor" ? `Ergebnisse für „${values?.query}“` : key;

describe("describeResultSetScope", () => {
  it("derives (and therefore localizes) the label for a search scope", () => {
    const resultSet = {
      source: { type: "search", query: "Präambel" },
      items: [],
      scopeLabel: "",
    } as unknown as ResultSet;

    expect(describeResultSetScope(resultSet, t)).toBe("Ergebnisse für „Präambel“");
  });

  it("keeps the stored label for a pivot scope, which is localized at dispatch", () => {
    const resultSet = {
      source: { type: "pivot", label: "Urteile", parentSource: { type: "search", query: "x" } },
      items: [],
      scopeLabel: "Urteile zu Art. 754 OR",
    } as unknown as ResultSet;

    expect(describeResultSetScope(resultSet, t)).toBe("Urteile zu Art. 754 OR");
  });
});
