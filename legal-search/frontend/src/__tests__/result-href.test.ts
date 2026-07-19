/**
 * Result deep links (#648) — result cards used to be `<button>`s with no
 * `href`, so nothing could be opened in a new tab, middle-clicked, or copied
 * as a link. These cover the pure link-building side of the fix.
 */

import { describe, expect, it } from "vitest";
import { buildResultHref, isModifiedClick } from "@/lib/result-href";

function click(overrides: Partial<Parameters<typeof isModifiedClick>[0]> = {}) {
  return {
    metaKey: false,
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
    button: 0,
    ...overrides,
  };
}

describe("buildResultHref", () => {
  it("preserves the current search state and selects the result", () => {
    expect(buildResultHref("q=Pr%C3%A4ambel", "law-1")).toBe("/?q=Pr%C3%A4ambel&item=law-1");
  });

  it("replaces an already-selected item rather than appending a second one", () => {
    const href = buildResultHref("q=abc&item=law-1", "law-2");
    expect(new URL(href, "http://x").searchParams.getAll("item")).toEqual(["law-2"]);
  });

  it("works with no existing query string", () => {
    expect(buildResultHref("", "decision-9")).toBe("/?item=decision-9");
  });
});

describe("isModifiedClick", () => {
  it("lets the browser handle new-tab and new-window gestures", () => {
    expect(isModifiedClick(click({ metaKey: true }))).toBe(true);
    expect(isModifiedClick(click({ ctrlKey: true }))).toBe(true);
    expect(isModifiedClick(click({ shiftKey: true }))).toBe(true);
    expect(isModifiedClick(click({ altKey: true }))).toBe(true);
    expect(isModifiedClick(click({ button: 1 }))).toBe(true);
  });

  it("intercepts a plain left click for client-side selection", () => {
    expect(isModifiedClick(click())).toBe(false);
  });
});
