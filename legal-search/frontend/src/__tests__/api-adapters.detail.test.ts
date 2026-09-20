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

  // `depth` and `text` are the second hop of #1040. The BFF sent both; this
  // mapper kept only `{id, label, active}`, so `StructureTab` had no depth to
  // indent by and no text to show, however deep the document was.
  it("carries section depth and text into the outline", () => {
    const view = mapDetail({
      ...base,
      localStructure: {
        items: [
          { id: "sec_1", label: "I. Allgemeine Bestimmungen", depth: 0, text: "Dieses Gesetz…" },
          { id: "sec_2", label: "§ 1 Meldepflicht", depth: 1 },
        ],
      },
    });

    expect(view.localStructure?.items).toEqual([
      {
        id: "sec_1",
        label: "I. Allgemeine Bestimmungen",
        active: false,
        depth: 0,
        text: "Dieses Gesetz…",
      },
      { id: "sec_2", label: "§ 1 Meldepflicht", active: false, depth: 1, text: undefined },
    ]);
  });

  it("carries a citation's text, target and resolution state", () => {
    const view = mapDetail({
      ...base,
      references: [
        {
          label: "SR",
          items: [
            {
              id: "cit_1",
              title: "Tierschutzgesetz",
              citation: "SR 455.1",
              resolved: true,
              targetDocumentId: "doc_tschg",
              href: "/documents/doc_tschg",
            },
            {
              id: "cit_2",
              title: "SR 210",
              citation: "SR 210",
              resolved: false,
              unresolvedReason: "no_target_in_corpus",
            },
          ],
        },
      ],
    });

    const items = view.references[0].items;
    expect(items[0].targetDocumentId).toBe("doc_tschg");
    expect(items[0].citation).toBe("SR 455.1");
    expect(items[1].resolved).toBe(false);
    expect(items[1].unresolvedReason).toBe("no_target_in_corpus");
    expect(items[1].targetDocumentId).toBeUndefined();
  });
});
