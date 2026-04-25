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

  // ─── Commentary record kind (#431) ─────────────────────────────────────

  describe("commentary rendering", () => {
    const commentaryResult: SearchResultViewModel = {
      ...mockResult,
      id: "commentary-1",
      title: "Verantwortlichkeit der Verwaltungsräte — Kommentar",
      type: "commentary",
      recordKind: "commentary",
      sourceDocumentIds: ["law-1", "law-754-or"],
      badges: [{ label: "Commentary", colorKey: "purple" }],
    };

    it("renders the commentary badge with screen-reader label", () => {
      renderWithProviders(
        <ResultCard
          result={commentaryResult}
          isSelected={false}
          onFocus={vi.fn()}
          isPinned={false}
        />,
      );

      // The visible badge text and the aria-labeled region.
      expect(screen.getByText("Kommentar")).toBeInTheDocument();
      expect(screen.getByLabelText("Kommentar zur Rechtsquelle")).toBeInTheDocument();
    });

    it("tags the article with data-record-kind for downstream styling", () => {
      const { container } = renderWithProviders(
        <ResultCard
          result={commentaryResult}
          isSelected={false}
          onFocus={vi.fn()}
          isPinned={false}
        />,
      );

      const article = container.querySelector("article");
      expect(article?.getAttribute("data-record-kind")).toBe("commentary");
    });

    it("renders source-document links and fires onFocus when clicked", () => {
      const onFocus = vi.fn();
      renderWithProviders(
        <ResultCard
          result={commentaryResult}
          isSelected={false}
          onFocus={onFocus}
          isPinned={false}
        />,
      );

      const sourceStrip = screen.getByTestId("commentary-source-links");
      expect(sourceStrip).toBeInTheDocument();
      // The "Cited in:" prefix.
      expect(screen.getByText("Bezieht sich auf:")).toBeInTheDocument();

      const law1 = screen.getByRole("button", { name: /law-1/ });
      fireEvent.click(law1);
      // Clicking a source link focuses the linked document, not the
      // commentary card itself.
      expect(onFocus).toHaveBeenLastCalledWith("law-1");
    });

    it("hides the source-link strip when sourceDocumentIds is empty", () => {
      renderWithProviders(
        <ResultCard
          result={{ ...commentaryResult, sourceDocumentIds: [] }}
          isSelected={false}
          onFocus={vi.fn()}
          isPinned={false}
        />,
      );

      expect(screen.queryByTestId("commentary-source-links")).not.toBeInTheDocument();
    });

    it("does NOT render the commentary badge on document hits", () => {
      renderWithProviders(
        <ResultCard
          result={{ ...mockResult, recordKind: "document" }}
          isSelected={false}
          onFocus={vi.fn()}
          isPinned={false}
        />,
      );

      expect(screen.queryByText("Kommentar")).not.toBeInTheDocument();
      expect(screen.queryByLabelText("Kommentar zur Rechtsquelle")).not.toBeInTheDocument();
    });
  });

  // ─── Commentary support pill (#431) ────────────────────────────────────

  describe("commentary support pill", () => {
    it("renders the support pill when commentarySupportCount > 0", () => {
      renderWithProviders(
        <ResultCard
          result={{ ...mockResult, commentarySupportCount: 3 }}
          isSelected={false}
          onFocus={vi.fn()}
          isPinned={false}
        />,
      );

      expect(screen.getByTestId("commentary-support-pill")).toBeInTheDocument();
      expect(screen.getByText("3 Kommentare")).toBeInTheDocument();
    });

    it("uses the singular form when count is 1", () => {
      renderWithProviders(
        <ResultCard
          result={{ ...mockResult, commentarySupportCount: 1 }}
          isSelected={false}
          onFocus={vi.fn()}
          isPinned={false}
        />,
      );

      expect(screen.getByText("1 Kommentar")).toBeInTheDocument();
    });

    it("hides the pill when commentarySupportCount is 0", () => {
      renderWithProviders(
        <ResultCard
          result={{ ...mockResult, commentarySupportCount: 0 }}
          isSelected={false}
          onFocus={vi.fn()}
          isPinned={false}
        />,
      );

      expect(screen.queryByTestId("commentary-support-pill")).not.toBeInTheDocument();
    });

    it("hides the pill when commentarySupportCount is undefined", () => {
      renderWithProviders(
        <ResultCard result={mockResult} isSelected={false} onFocus={vi.fn()} isPinned={false} />,
      );

      expect(screen.queryByTestId("commentary-support-pill")).not.toBeInTheDocument();
    });

    it("hides the pill on commentary cards even if a count slipped through", () => {
      renderWithProviders(
        <ResultCard
          result={{
            ...mockResult,
            recordKind: "commentary",
            commentarySupportCount: 5,
          }}
          isSelected={false}
          onFocus={vi.fn()}
          isPinned={false}
        />,
      );

      expect(screen.queryByTestId("commentary-support-pill")).not.toBeInTheDocument();
    });
  });
});
