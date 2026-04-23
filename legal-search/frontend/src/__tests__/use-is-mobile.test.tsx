import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useIsMobile } from "@/hooks/use-is-mobile";

type MatchMediaFn = (query: string) => MediaQueryList;

function mockMatchMedia(shouldMatch: boolean): MatchMediaFn {
  return (query: string) =>
    ({
      matches: shouldMatch,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

const originalMatchMedia = window.matchMedia;

afterEach(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: originalMatchMedia,
  });
});

describe("useIsMobile", () => {
  it("returns true when the (max-width: 767px) media query matches", () => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: mockMatchMedia(true),
    });

    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(true);
  });

  it("returns false when the media query does not match", () => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: mockMatchMedia(false),
    });

    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);
  });
});
