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

    expect(screen.getByText("3 Ergebnisse")).toBeInTheDocument();
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
