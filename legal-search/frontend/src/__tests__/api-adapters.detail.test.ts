/**
 * mapDetail — DetailView → DetailViewModel
 *
 * WHY THIS TEST EXISTS:
 * This mapper is where #609 happened: every field of the API's `DetailView` was
 * carried across and `content` alone was left behind, so the API could return a
 * full document and the view would never see it. `regeste` (#760) is the same
 * shape of field — optional, prose, easy to drop silently — so the passthrough
 * is asserted rather than assumed.
 */

import { describe, expect, it } from "vitest";
import type { DetailView } from "@/lib/api/generated/model";
import { mapDetail } from "@/lib/api-adapters";

const base: DetailView = {
  id: "decision-1",
  type: "decision",
  title: "BGer 4A_123/2022",
  subtitle: "Verantwortlichkeit des Verwaltungsrats",
  metadata: [],
  tabs: [],
  relatedGroups: [],
  references: [],
  annotations: [],
};

describe("mapDetail", () => {
  it("carries the regeste across to the view model", () => {
    const view = mapDetail({ ...base, regeste: "Art. 754 OR; Verantwortlichkeit." });
    expect(view.regeste).toBe("Art. 754 OR; Verantwortlichkeit.");
  });

  it("leaves the regeste undefined when the response carries none", () => {
    expect(mapDetail(base).regeste).toBeUndefined();
  });
});
