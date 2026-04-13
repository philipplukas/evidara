import { describe, expect, it } from "vitest";
import { describeLegalSearchHandoff, resolveLegalSearchHandoff } from "./navigationContext";

describe("navigationContext", () => {
  it("resolves a namespaced legal-search handoff payload", () => {
    const handoff = resolveLegalSearchHandoff(
      new URLSearchParams({
        from: "legal-search",
        ls_return_to: "/?q=Art%20754%20OR&item=doc-1",
        ls_query: "Art 754 OR",
        ls_scope: 'Results for "Art 754 OR"',
        ls_item: "doc-1",
      }),
      "https://search.example/search",
    );

    expect(handoff).toEqual({
      hasOrigin: true,
      returnToUrl: "https://search.example/?q=Art%20754%20OR&item=doc-1",
      query: "Art 754 OR",
      scopeLabel: 'Results for "Art 754 OR"',
      selectedId: "doc-1",
    });
    expect(describeLegalSearchHandoff(handoff)).toBe(
      'Results for "Art 754 OR" · Search "Art 754 OR"',
    );
  });

  it("falls back to the configured legal-search URL when returnTo targets another origin", () => {
    const handoff = resolveLegalSearchHandoff(
      new URLSearchParams({
        from: "legal-search",
        ls_return_to: "https://evil.example/?q=steal",
      }),
      "https://search.example/",
    );

    expect(handoff.returnToUrl).toBe("https://search.example/");
  });

  it("falls back to the configured legal-search URL when returnTo is malformed", () => {
    const handoff = resolveLegalSearchHandoff(
      new URLSearchParams({
        from: "legal-search",
        ls_return_to: "javascript:alert('xss')",
      }),
      "https://search.example/",
    );

    expect(handoff.returnToUrl).toBe("https://search.example/");
  });
});
