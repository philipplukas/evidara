import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DetailSheet } from "@/components/layout/DetailSheet";
import { renderWithProviders } from "./helpers/render-with-providers";

vi.mock("@/components/detail/DetailPanel", () => ({
  DetailPanel: () => <div>detail-panel</div>,
}));

type MatchMediaFn = (query: string) => MediaQueryList;

function mockMatchMedia(matches: (query: string) => boolean): MatchMediaFn {
  return (query: string) =>
    ({
      matches: matches(query),
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

describe("DetailSheet responsive presentation", () => {
  it("renders as a bottom sheet when the mobile media query matches", () => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: mockMatchMedia((q) => q === "(max-width: 767px)"),
    });

    renderWithProviders(<DetailSheet open={true} onOpenChange={() => {}} detail={null} />);

    const content = document.querySelector("[data-slot='sheet-content']");
    expect(content).not.toBeNull();
    expect(content).toHaveAttribute("data-side", "bottom");
    // Decorative drag handle is present only on mobile.
    expect(content?.querySelector("div[aria-hidden='true']")).not.toBeNull();
  });

  it("renders as a right drawer when the mobile media query does not match", () => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: mockMatchMedia(() => false),
    });

    renderWithProviders(<DetailSheet open={true} onOpenChange={() => {}} detail={null} />);

    const content = document.querySelector("[data-slot='sheet-content']");
    expect(content).not.toBeNull();
    expect(content).toHaveAttribute("data-side", "right");
    // No decorative drag handle on desktop.
    expect(content?.querySelector("div[aria-hidden='true']")).toBeNull();
    // Sanity: close button stays available for keyboard dismiss.
    expect(screen.getByRole("button", { name: /close/i })).toBeInTheDocument();
  });
});
