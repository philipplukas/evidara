/**
 * ResultCard — Component Render Tests
 *
 * WHY THESE TESTS EXIST:
 * ResultCard is the primary interactive element in the search UI.
 * If it fails to render, the entire search experience is broken.
 * If click handlers don't fire, users can't navigate.
 *
 * WHAT WE TEST:
 * - Renders title, subtitle, snippet, badges
 * - Fires onFocus callback on click
 * - Shows pin state
 * - Fires onPivot on related count click
 * - A11y: no violations
 */

import { fireEvent, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it, vi } from "vitest";
import { ResultCard } from "@/components/results/ResultCard";
import type { SearchResultViewModel } from "@/lib/types";
import { renderWithProviders } from "./helpers/render-with-providers";

expect.extend(toHaveNoViolations);

const mockResult: SearchResultViewModel = {
  id: "law-1",
  title: "Art. 754 OR",
  subtitle: "Switzerland · Federal law",
  snippet: "Die Mitglieder des Verwaltungsrates...",
  type: "law",
  badges: [{ label: "Law", colorKey: "blue" }],
  metadataRows: [{ label: "Enacted", value: "1911" }],
  relatedCounts: [
    { label: "Commentary", count: 8 },
    { label: "Court decisions", count: 142 },
  ],
  actions: [{ label: "Open article", icon: "file-text" }],
};

describe("ResultCard", () => {
  it("renders title, subtitle, and snippet", () => {
    renderWithProviders(
      <ResultCard result={mockResult} isSelected={false} onFocus={vi.fn()} isPinned={false} />,
    );

    expect(screen.getByText("Art. 754 OR")).toBeInTheDocument();
    expect(screen.getByText("Switzerland · Federal law")).toBeInTheDocument();
    expect(screen.getByText("Die Mitglieder des Verwaltungsrates...")).toBeInTheDocument();
  });

  it("renders badges", () => {
    renderWithProviders(
      <ResultCard result={mockResult} isSelected={false} onFocus={vi.fn()} isPinned={false} />,
    );

    expect(screen.getByText("Law")).toBeInTheDocument();
  });

  it("renders metadata rows", () => {
    renderWithProviders(
      <ResultCard result={mockResult} isSelected={false} onFocus={vi.fn()} isPinned={false} />,
    );

    expect(screen.getByText("Enacted:")).toBeInTheDocument();
    expect(screen.getByText("1911")).toBeInTheDocument();
  });

  it("fires onFocus on click", () => {
    const onFocus = vi.fn();
    renderWithProviders(
      <ResultCard result={mockResult} isSelected={false} onFocus={onFocus} isPinned={false} />,
    );

    fireEvent.click(screen.getByText("Art. 754 OR"));
    expect(onFocus).toHaveBeenCalledWith("law-1");
  });

  /**
   * #648 — the title was a `<button>` with no `href`, so a result could not be
   * opened in a new tab, middle-clicked, or copied as a link. For a legal
   * research tool a shareable, citable document link is a core affordance.
   */
  it("renders the title as a real link to the result's deep link", () => {
    renderWithProviders(
      <ResultCard result={mockResult} isSelected={false} onFocus={vi.fn()} isPinned={false} />,
    );

    const link = screen.getByRole("link", { name: "Art. 754 OR" });
    expect(link).toHaveAttribute("href", expect.stringContaining("item=law-1"));
  });

  it("leaves modified clicks to the browser so new-tab still works", () => {
    const onFocus = vi.fn();
    renderWithProviders(
      <ResultCard result={mockResult} isSelected={false} onFocus={onFocus} isPinned={false} />,
    );

    fireEvent.click(screen.getByRole("link", { name: "Art. 754 OR" }), { metaKey: true });
    expect(onFocus).not.toHaveBeenCalled();
  });

  it("fires onPivot on related count click", () => {
    const onPivot = vi.fn();
    renderWithProviders(
      <ResultCard
        result={mockResult}
        isSelected={false}
        onFocus={vi.fn()}
        onPivot={onPivot}
        isPinned={false}
      />,
    );

    fireEvent.click(screen.getByText("Commentary"));
    expect(onPivot).toHaveBeenCalledWith("Commentary", "law-1");
  });

  it("shows selected style when isSelected is true", () => {
    const { container } = renderWithProviders(
      <ResultCard result={mockResult} isSelected={true} onFocus={vi.fn()} isPinned={false} />,
    );

    const article = container.querySelector("article");
    expect(article?.className).toContain("border-l-accent-core");
    expect(article?.getAttribute("aria-current")).toBe("true");
    expect(screen.getByText("Ausgewählt")).toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    const { container } = renderWithProviders(
      <ResultCard result={mockResult} isSelected={false} onFocus={vi.fn()} isPinned={false} />,
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
