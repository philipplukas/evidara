import { describe, expect, it } from "vitest";
import { sanitizeSnippetHtml, stripHighlightTags } from "./highlight";

describe("sanitizeSnippetHtml", () => {
  it("keeps the highlight markup the search API emits", () => {
    expect(sanitizeSnippetHtml("Die <mark>Kündigungsfrist</mark> beträgt drei Monate.")).toBe(
      "Die <mark>Kündigungsfrist</mark> beträgt drei Monate.",
    );
  });

  it("strips markup that is not a highlight, keeping the text", () => {
    const sanitized = sanitizeSnippetHtml('<a href="#">Art. 1</a> und <b>Art. 2</b>');
    expect(sanitized).toBe("Art. 1 und Art. 2");
  });

  it("does not render script content from document text", () => {
    const sanitized = sanitizeSnippetHtml('<script>alert("xss")</script><mark>Treu</mark>');
    expect(sanitized).not.toContain("<script");
    expect(sanitized).not.toContain("alert");
    expect(sanitized).toContain("<mark>Treu</mark>");
  });

  it("drops attributes on the highlight tag", () => {
    const sanitized = sanitizeSnippetHtml('<mark onclick="steal()">Treu</mark>');
    expect(sanitized).toBe("<mark>Treu</mark>");
  });

  it("returns an empty string for an empty snippet", () => {
    expect(sanitizeSnippetHtml("")).toBe("");
  });
});

describe("stripHighlightTags", () => {
  it("returns plain text for non-HTML contexts such as CSV export", () => {
    expect(stripHighlightTags("Die <mark>Kündigungsfrist</mark> beträgt drei Monate.")).toBe(
      "Die Kündigungsfrist beträgt drei Monate.",
    );
  });

  it("returns an empty string for an empty snippet", () => {
    expect(stripHighlightTags("")).toBe("");
  });
});
