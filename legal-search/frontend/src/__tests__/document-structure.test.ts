/**
 * buildDocumentOutline — placing sections inside the body.
 *
 * WHY THIS TEST EXISTS:
 * A section click can only move the reader if the section has somewhere to go.
 * Measured live on 2026-09-19, a rendered statute contained zero headings and
 * zero anchors (#1040), so the outline pointed nowhere and its clicks were
 * routed to a document endpoint instead — 404 every time.
 *
 * The case that matters most is the one that does NOT match: a section with no
 * place in the body must be reported as unanchored rather than quietly
 * accepted, because a click that scrolls nowhere is indistinguishable from a
 * jump that worked.
 */

import { describe, expect, it } from "vitest";
import { buildDocumentOutline, relativeDepths, sectionAnchorId } from "@/lib/document-structure";
import type { LocalStructureItem } from "@/lib/types";

const item = (over: Partial<LocalStructureItem> & { id: string }): LocalStructureItem => ({
  label: over.id,
  active: false,
  ...over,
});

describe("buildDocumentOutline", () => {
  it("turns a paragraph that is the section title into a heading", () => {
    const text = "A. Allgemeine Bestimmungen\n\nDieses Gesetz regelt die Haltung von Hunden.";
    const outline = buildDocumentOutline(text, [
      item({ id: "sec_1", label: "A. Allgemeine Bestimmungen", depth: 0 }),
    ]);

    expect(outline.blocks).toEqual([
      { kind: "heading", sectionId: "sec_1", label: "A. Allgemeine Bestimmungen", depth: 0 },
      { kind: "paragraph", text: "Dieses Gesetz regelt die Haltung von Hunden." },
    ]);
    expect(outline.anchored.has("sec_1")).toBe(true);
  });

  it("inserts a heading before the paragraph its preview names", () => {
    // The body carries no heading line, so the outline supplies one and the
    // paragraph is kept.
    const text = "Wer einen Hund haelt, meldet ihn innert zehn Tagen der Wohnsitzgemeinde.";
    const outline = buildDocumentOutline(text, [
      item({
        id: "sec_2",
        label: "§ 1 Meldepflicht",
        depth: 1,
        text: "Wer einen Hund haelt, meldet ihn innert zehn Tagen",
      }),
    ]);

    expect(outline.blocks.map((b) => b.kind)).toEqual(["heading", "paragraph"]);
    expect(outline.anchored.has("sec_2")).toBe(true);
  });

  it("reports a section it cannot place as unanchored and leaves the body intact", () => {
    // GUARD. Delete the `if (titleIndex < 0 && textIndex < 0) continue;` line
    // and this goes red — every section would acquire an anchor whether or not
    // the body holds it.
    const text = "Dieses Gesetz regelt die Haltung von Hunden.";
    const outline = buildDocumentOutline(text, [
      item({ id: "sec_ghost", label: "§ 99 Nicht im Text", text: "Steht nirgends im Dokument" }),
    ]);

    expect(outline.anchored.size).toBe(0);
    expect(outline.blocks).toEqual([
      { kind: "paragraph", text: "Dieses Gesetz regelt die Haltung von Hunden." },
    ]);
  });

  it("never anchors a later section above an earlier one", () => {
    // Both sections carry the same boilerplate opening. Forward-only matching
    // is what stops § 2 from claiming § 1's paragraph.
    const text = ["§ 1", "Der Regierungsrat erlaesst die Ausfuehrungsbestimmungen.", "§ 2"].join(
      "\n\n",
    );
    const outline = buildDocumentOutline(text, [
      item({ id: "sec_a", label: "§ 1" }),
      item({ id: "sec_b", label: "§ 2" }),
    ]);

    const headings = outline.blocks.filter((b) => b.kind === "heading");
    expect(headings.map((h) => (h.kind === "heading" ? h.sectionId : ""))).toEqual([
      "sec_a",
      "sec_b",
    ]);
  });

  it("anchors one section per paragraph rather than stacking them", () => {
    const text = "Kapitel I\n\nKapitel I";
    const outline = buildDocumentOutline(text, [
      item({ id: "sec_x", label: "Kapitel I" }),
      item({ id: "sec_y", label: "Kapitel I" }),
    ]);

    expect(outline.anchored).toEqual(new Set(["sec_x", "sec_y"]));
    expect(outline.blocks).toHaveLength(2);
  });

  it("returns no blocks and no anchors for a document with no body", () => {
    const outline = buildDocumentOutline(undefined, [item({ id: "sec_1", label: "§ 1" })]);

    expect(outline.blocks).toEqual([]);
    expect(outline.anchored.size).toBe(0);
  });

  it("renders the body unchanged when the document has no outline", () => {
    const outline = buildDocumentOutline("Eins.\n\nZwei.", []);

    expect(outline.blocks).toEqual([
      { kind: "paragraph", text: "Eins." },
      { kind: "paragraph", text: "Zwei." },
    ]);
  });

  it("matches a title across differing dash characters and spacing", () => {
    const outline = buildDocumentOutline("Art. 754 – Haftung", [
      item({ id: "sec_d", label: "Art. 754 - Haftung" }),
    ]);

    expect(outline.anchored.has("sec_d")).toBe(true);
  });

  it("does not match on a preview too short to be distinctive", () => {
    // Under the 24-character floor two different articles would collide on
    // boilerplate, so a short preview anchors nothing rather than anchoring
    // the wrong paragraph.
    const outline = buildDocumentOutline("Aufgehoben.", [
      item({ id: "sec_s", label: "§ 7", text: "Aufgehoben." }),
    ]);

    expect(outline.anchored.size).toBe(0);
  });
});

describe("relativeDepths", () => {
  it("rebases a one-based outline so its top level renders flush", () => {
    const depths = relativeDepths([
      item({ id: "a", depth: 1 }),
      item({ id: "b", depth: 2 }),
      item({ id: "c", depth: 3 }),
    ]);

    expect([depths.get("a"), depths.get("b"), depths.get("c")]).toEqual([0, 1, 2]);
  });

  it("treats a section with no depth as top level", () => {
    expect(relativeDepths([item({ id: "a" })]).get("a")).toBe(0);
  });

  it("clamps a depth deeper than the outline renders", () => {
    expect(
      relativeDepths([item({ id: "a", depth: 0 }), item({ id: "b", depth: 99 })]).get("b"),
    ).toBe(5);
  });
});

describe("sectionAnchorId", () => {
  it("namespaces the id so it cannot collide with a document id", () => {
    expect(sectionAnchorId("sec_6524xdp5th69e860k86n5vxea7")).toBe(
      "section-sec_6524xdp5th69e860k86n5vxea7",
    );
  });
});
