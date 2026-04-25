/**
 * ResultList — Component Tests
 *
 * WHY THESE TESTS EXIST:
 * ResultList orchestrates the result cards, empty states, and pagination.
 * If it fails, users see nothing after searching.
 *
 * WHAT WE TEST:
 * - Shows "no results" empty state
 * - Shows "start searching" state when no query
 * - Renders result count and cards
 * - Shows "Load more" button when results exceed PAGE_SIZE
 * - Loading state shows spinner
 */

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResultList } from "@/components/results/ResultList";
import type { SearchResultViewModel } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace-store";
import { renderWithProviders } from "./helpers/render-with-providers";

function makeResults(count: number): SearchResultViewModel[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `r-${i}`,
    title: `Result ${i + 1}`,
    subtitle: "Subtitle",
    snippet: "Snippet text",
    type: "law",
    badges: [{ label: "Law", colorKey: "blue" }],
    metadataRows: [],
    relatedCounts: [],
    actions: [],
  }));
}

describe("ResultList", () => {
  it("shows contextual empty state when query is provided", () => {
    renderWithProviders(
      <ResultList
        results={[]}
        selectedId={null}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        pinnedIds={new Set()}
        query="nonexistent"
      />,
    );

    expect(screen.getByText(/Keine Ergebnisse für/)).toBeInTheDocument();
    // No reset button when constraints are at their defaults.
    expect(screen.queryByRole("button", { name: "Filter zurücksetzen" })).not.toBeInTheDocument();
  });

  it("shows filtered empty state with a reset button when constraints are active", () => {
    renderWithProviders(
      <ResultList
        results={[]}
        selectedId={null}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        pinnedIds={new Set()}
        query="Art. 754"
      />,
      // Non-default jurisdictions trigger `hasActiveSearchConstraints`.
      { searchParams: { jurisdictions: "CH,AT" } },
    );

    expect(screen.getByText("Keine Treffer mit den aktiven Filtern.")).toBeInTheDocument();
    expect(
      screen.getByText("Lockern Sie einen Filter oder setzen Sie alle Filter zurück."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Filter zurücksetzen" })).toBeInTheDocument();
  });

  it("shows start-searching state when no query", () => {
    renderWithProviders(
      <ResultList
        results={[]}
        selectedId={null}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        pinnedIds={new Set()}
      />,
    );

    expect(screen.getByText("Suche starten")).toBeInTheDocument();
  });

  it("shows loading spinner when isLoading", () => {
    renderWithProviders(
      <ResultList
        results={[]}
        selectedId={null}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        pinnedIds={new Set()}
        isLoading
      />,
    );

    expect(screen.getByText("Aktuellen Bereich durchsuchen…")).toBeInTheDocument();
  });

  it("renders result count and cards", () => {
    renderWithProviders(
      <ResultList
        results={makeResults(3)}
        selectedId={null}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        pinnedIds={new Set()}
      />,
    );

    expect(screen.getAllByText("3 Ergebnisse").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Result 1")).toBeInTheDocument();
    expect(screen.getByText("Result 2")).toBeInTheDocument();
    expect(screen.getByText("Result 3")).toBeInTheDocument();
  });

  it("shows Load more button when results exceed page size", () => {
    // Default resultsPerPage preference is 25
    renderWithProviders(
      <ResultList
        results={makeResults(30)}
        selectedId={null}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        pinnedIds={new Set()}
      />,
    );

    expect(screen.getByText("Weitere Ergebnisse laden")).toBeInTheDocument();
    expect(screen.getByText("(5 verbleibend)")).toBeInTheDocument();
    // Only first 25 visible
    expect(screen.getByText("Result 1")).toBeInTheDocument();
    expect(screen.getByText("Result 25")).toBeInTheDocument();
    expect(screen.queryByText("Result 26")).not.toBeInTheDocument();
  });

  it("loads more results when button is clicked", () => {
    // Default resultsPerPage preference is 25
    renderWithProviders(
      <ResultList
        results={makeResults(30)}
        selectedId={null}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        pinnedIds={new Set()}
      />,
    );

    fireEvent.click(screen.getByText("Weitere Ergebnisse laden"));
    expect(screen.getByText("Result 26")).toBeInTheDocument();
    expect(screen.getByText("Result 30")).toBeInTheDocument();
    // No more "Load more" button
    expect(screen.queryByText("Weitere Ergebnisse laden")).not.toBeInTheDocument();
  });

  it("renders mixed document + commentary cards without regressing document hits (#431)", () => {
    const mixed: SearchResultViewModel[] = [
      {
        id: "law-1",
        title: "Art. 754 OR",
        subtitle: "Switzerland · Federal law",
        snippet: "Die Mitglieder des Verwaltungsrates...",
        type: "law",
        badges: [{ label: "Law", colorKey: "blue" }],
        metadataRows: [],
        relatedCounts: [],
        actions: [],
        commentarySupportCount: 3,
      },
      {
        id: "commentary-1",
        title: "BSK OR I — Art. 754",
        subtitle: "Basler Kommentar",
        snippet: "Die Verantwortlichkeitsklage…",
        type: "commentary",
        badges: [{ label: "Commentary", colorKey: "purple" }],
        metadataRows: [],
        relatedCounts: [],
        actions: [],
        recordKind: "commentary",
        sourceDocumentIds: ["law-1"],
      },
    ];

    const { container } = renderWithProviders(
      <ResultList
        results={mixed}
        selectedId={null}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        pinnedIds={new Set()}
      />,
    );

    // Both cards render.
    expect(screen.getByText("Art. 754 OR")).toBeInTheDocument();
    expect(screen.getByText("BSK OR I — Art. 754")).toBeInTheDocument();

    // Document hit keeps its untagged data-record-kind contract.
    const documentArticle = container.querySelector('article[data-record-kind="document"]');
    expect(documentArticle).not.toBeNull();
    // Commentary hit is tagged distinctly.
    const commentaryArticle = container.querySelector('article[data-record-kind="commentary"]');
    expect(commentaryArticle).not.toBeNull();

    // Document card surfaces the support pill.
    expect(screen.getByText("3 Kommentare")).toBeInTheDocument();
    // Commentary card surfaces the source-document pivot strip.
    expect(screen.getByTestId("commentary-source-links")).toBeInTheDocument();
  });

  it("shows pivot-aware empty state when the current scope is empty", async () => {
    function PivotEmptyHarness() {
      const { state, dispatch } = useWorkspace();

      return (
        <div>
          <button
            type="button"
            onClick={() =>
              dispatch({
                type: "PIVOT",
                source: {
                  type: "pivot",
                  label: "Commentary",
                  parentSource: state.resultSet.source,
                },
                results: [],
                scopeLabel: "Commentary for Art. 754 OR",
              })
            }
          >
            pivot-empty
          </button>
          <ResultList
            results={[]}
            selectedId={null}
            onFocus={vi.fn()}
            onPivot={vi.fn()}
            onPin={vi.fn()}
            pinnedIds={new Set()}
          />
        </div>
      );
    }

    renderWithProviders(<PivotEmptyHarness />);
    fireEvent.click(screen.getByRole("button", { name: "pivot-empty" }));

    await waitFor(() => {
      expect(screen.getByText("Keine Ergebnisse in diesem Pivot")).toBeInTheDocument();
    });
  });
});
