import { describe, expect, it } from "vitest";
import { toParagraphs } from "@/lib/document-body";

describe("toParagraphs", () => {
  it("splits on blank lines, the only structure the body carries", () => {
    expect(toParagraphs("Erste Erwägung.\n\nZweite Erwägung.")).toEqual([
      "Erste Erwägung.",
      "Zweite Erwägung.",
    ]);
  });

  // The corpus arrives hard-wrapped mid-sentence (`seed-diverse.ts` indexes
  // OpenCaseLaw `full_text` verbatim, wrapped at ~60 chars). Keeping those
  // newlines would reproduce the source file's ragged right edge on screen.
  it("collapses hard wraps inside a paragraph so the text reflows", () => {
    expect(toParagraphs("Der beanzeigte Anwalt macht\nein Versehen geltend.")).toEqual([
      "Der beanzeigte Anwalt macht ein Versehen geltend.",
    ]);
  });

  it("treats runs of blank lines and indented blank lines as one break", () => {
    expect(toParagraphs("Eins.\n\n\n\nZwei.\n \nDrei.")).toEqual(["Eins.", "Zwei.", "Drei."]);
  });

  it("yields nothing for absent or whitespace-only bodies", () => {
    expect(toParagraphs(undefined)).toEqual([]);
    expect(toParagraphs("")).toEqual([]);
    expect(toParagraphs("   \n\n  \n ")).toEqual([]);
  });
});
