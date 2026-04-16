import { describe, expect, it } from "vitest";
import { enrichMetadataRows } from "@/lib/metadata-visibility";

describe("enrichMetadataRows", () => {
  it("uses BFF visibility when provided", () => {
    const fields = enrichMetadataRows(
      [{ label: "Custom", value: "x", visibility: "always" }],
      "law",
    );
    expect(fields[0]?.visibility).toBe("always");
  });

  it("falls back to heuristics when visibility is omitted", () => {
    const fields = enrichMetadataRows([{ label: "Obscure field", value: "y" }], "law");
    expect(fields[0]?.visibility).toBe("expanded");
  });
});
