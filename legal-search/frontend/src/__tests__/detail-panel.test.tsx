/**
 * DetailPanel — Component Render Tests
 *
 * WHY THESE TESTS EXIST:
 * DetailPanel is the primary document view. If it fails to render,
 * users cannot inspect any search result.
 *
 * WHAT WE TEST:
 * - Shows empty state when detail is null
 * - Renders title, breadcrumbs, metadata when detail is provided
 * - A11y: no violations
 */

import { fireEvent, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it, vi } from "vitest";
import { DetailPanel } from "@/components/detail/DetailPanel";
import { articleDetail } from "@/lib/mock-data";
import { renderWithProviders } from "./helpers/render-with-providers";

expect.extend(toHaveNoViolations);

describe("DetailPanel", () => {
  it("falls back to safe title/subtitle and copy text for sparse detail", () => {
    const writeText = vi.fn();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    const sparseDetail = {
      ...articleDetail,
      title: "",
      subtitle: "",
    };

    renderWithProviders(
      <DetailPanel
        detail={sparseDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
    );

    expect(screen.getByText("Dokument ohne Titel")).toBeInTheDocument();
    expect(screen.getByText("Keine Zusammenfassung verfügbar")).toBeInTheDocument();

    fireEvent.click(screen.getByTitle("Zitat kopieren"));
    expect(writeText).toHaveBeenCalledWith("Dokument ohne Titel");
  });

  it("shows a fallback translation badge label when translation label is missing", () => {
    const translatedSparseDetail = {
      ...articleDetail,
      contentLanguage: {
        display: "en",
        original: "de",
        isTranslation: true,
        label: "",
      },
    };

    renderWithProviders(
      <DetailPanel
        detail={translatedSparseDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
    );

    expect(screen.getByText("Übersetzter Inhalt")).toBeInTheDocument();
  });

  it("shows empty state when detail is null", () => {
    renderWithProviders(<DetailPanel detail={null} />);

    expect(screen.getByText("Kein Ergebnis ausgewählt")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Wählen Sie ein Ergebnis, um Dokumentdetails, verknüpfte Materialien und Verweise zu öffnen\./,
      ),
    ).toBeInTheDocument();
  });

  it("renders title and subtitle when detail is provided", () => {
    renderWithProviders(
      <DetailPanel
        detail={articleDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
    );

    expect(screen.getByText("Art. 754 OR")).toBeInTheDocument();
    expect(
      screen.getByText("Verantwortlichkeit — Haftung der Verwaltung und der Geschäftsführung"),
    ).toBeInTheDocument();
  });

  it("renders tab labels", () => {
    renderWithProviders(
      <DetailPanel
        detail={articleDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
    );

    expect(screen.getByText("Details")).toBeInTheDocument();
    expect(screen.getByText("Related")).toBeInTheDocument();
    expect(screen.getByText("References")).toBeInTheDocument();
    expect(screen.getByText("Annotation")).toBeInTheDocument();
    expect(screen.getByText("Structure")).toBeInTheDocument();
  });

  it("renders metadata rows", () => {
    renderWithProviders(
      <DetailPanel
        detail={articleDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
    );

    expect(screen.getAllByText("Switzerland").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Obligationenrecht (OR)")).toBeInTheDocument();
  });

  it("sanitizes unsafe HTML in detail content", () => {
    const unsafeDetail = {
      ...articleDetail,
      contentHtml:
        '<p>Safe paragraph</p><img src="x" onerror="window.__evidara_test_xss=1"><script>window.__evidara_test_xss=1</script>',
    };

    const { container } = renderWithProviders(
      <DetailPanel
        detail={unsafeDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
    );

    const img = container.querySelector("img");
    expect(img).not.toBeNull();
    expect(img?.getAttribute("onerror")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText("Safe paragraph")).toBeInTheDocument();
  });

  it("has no accessibility violations (empty state)", async () => {
    const { container } = renderWithProviders(<DetailPanel detail={null} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("has no accessibility violations (with detail)", async () => {
    const { container } = renderWithProviders(
      <DetailPanel
        detail={articleDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
