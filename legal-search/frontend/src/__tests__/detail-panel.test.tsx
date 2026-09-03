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
import { articleDetail, decisionDetail } from "@/lib/mock-data";
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

  it("copies a citation-like title and subtitle when detail has source context", () => {
    const writeText = vi.fn();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    renderWithProviders(
      <DetailPanel
        detail={articleDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
    );

    fireEvent.click(screen.getByTitle("Zitat kopieren"));
    expect(writeText).toHaveBeenCalledWith(
      "Art. 754 OR - Verantwortlichkeit — Haftung der Verwaltung und der Geschäftsführung",
    );
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

  it("renders a graceful empty state for the content tab when the document has no body", () => {
    // A document with no body at all. The API omits the `content` tab in that
    // case, so this is the defensive path: the tab arriving anyway must not
    // leave a blank panel.
    const contentDetail = {
      ...articleDetail,
      tabs: [
        { key: "content", label: "Inhalt" },
        { key: "details", label: "Details" },
      ],
      contentText: undefined,
      localStructure: { items: [] },
    };

    renderWithProviders(
      <DetailPanel
        detail={contentDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
      { searchParams: { tab: "content" } },
    );

    expect(screen.getByText("Kein Inhalt verfügbar")).toBeInTheDocument();
  });

  // #609: the Inhalt tab used to render the structure outline whenever
  // `localStructure` was present — byte-identical to the Struktur tab, with a
  // heading reading "LOKALE STRUKTUR" under a tab labelled "Inhalt".
  it("renders the document body — not the structure outline — on the content tab", () => {
    const contentDetail = {
      ...articleDetail,
      tabs: [
        { key: "content", label: "Inhalt" },
        { key: "details", label: "Details" },
      ],
      contentText: "Erste Erwägung.\n\nZweite Erwägung.",
      localStructure: { items: [{ id: "sec-1", label: "Allgemeine Bestimmungen", active: false }] },
    };

    renderWithProviders(
      <DetailPanel
        detail={contentDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
      { searchParams: { tab: "content" } },
    );

    expect(screen.getByText("Erste Erwägung.")).toBeInTheDocument();
    expect(screen.getByText("Zweite Erwägung.")).toBeInTheDocument();
    expect(screen.queryByText("Allgemeine Bestimmungen")).not.toBeInTheDocument();
  });

  it("never leaves a blank panel for an unknown tab key (contract-drift guard)", () => {
    const oddDetail = {
      ...articleDetail,
      tabs: [
        { key: "brandNewTab", label: "New" },
        { key: "details", label: "Details" },
      ],
    };

    renderWithProviders(
      <DetailPanel
        detail={oddDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
      { searchParams: { tab: "brandNewTab" } },
    );

    expect(screen.getByText("Kein Inhalt verfügbar")).toBeInTheDocument();
  });

  // The body is plain text — markup inside it is content to be shown, not
  // markup to be executed. Nothing is interpreted, so nothing needs stripping.
  it("renders markup-looking detail content as literal text", () => {
    const unsafeDetail = {
      ...articleDetail,
      contentText:
        'Safe paragraph<img src="x" onerror="window.__evidara_test_xss=1"><script>window.__evidara_test_xss=1</script>',
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

    // Scoped to the markup the body text contains — the panel legitimately
    // renders its own <img> for the jurisdiction flag.
    expect(container.querySelector('img[src="x"]')).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(
      screen.getByText(
        'Safe paragraph<img src="x" onerror="window.__evidara_test_xss=1"><script>window.__evidara_test_xss=1</script>',
      ),
    ).toBeInTheDocument();
  });

  // The API emits `citations` for the reference groups (see `composeTabs` in
  // document-detail.mapper.ts); the mock's vocabulary is `references`. The
  // panel handled only the mock's key, so the tab the API actually advertises
  // rendered "nothing here" over real citation data (#622).
  it.each([
    "references",
    "citations",
  ])("renders the reference groups for the %s tab key", (tabKey) => {
    renderWithProviders(
      <DetailPanel
        detail={articleDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
      { searchParams: { tab: tabKey } },
    );

    expect(screen.getByText("Art. 756 OR")).toBeInTheDocument();
    expect(screen.queryByText("Kein Inhalt verfügbar")).not.toBeInTheDocument();
  });

  // The composition seam. `Regeste`, `mapDetail` and the BFF mapper each have
  // their own tests, and all of them stayed green with the panel passing
  // `text={undefined}` — the feature can be wholly dead at the one line that
  // delivers it and nothing notices. That seam is #609 (the body mapped
  // everywhere but the view) and #728 (a DTO that worked in every test layer
  // and was inert in the built app). This is the test that fails if the header
  // stops handing the headnote to `Regeste` (#760).
  it("renders the regeste on the detail panel for a decision that carries one", () => {
    renderWithProviders(
      <DetailPanel
        detail={decisionDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
    );

    expect(screen.getByRole("region", { name: "Regeste" })).toBeInTheDocument();
    expect(
      screen.getByText(/Verantwortlichkeit der Verwaltungsratsmitglieder; Beweislastverteilung/),
    ).toBeInTheDocument();
  });

  it("renders no Regeste region for a document that carries none", () => {
    // `articleDetail` is a statute — no headnote — and must not get an empty
    // labelled box.
    renderWithProviders(
      <DetailPanel
        detail={articleDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
    );

    expect(screen.queryByRole("region", { name: "Regeste" })).not.toBeInTheDocument();
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
