import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import WorkspaceClient from "@/app/WorkspaceClient";
import { filters, searchContext, searchResults } from "@/lib/mock-data";
import { renderWithProviders } from "./helpers/render-with-providers";

const runSearchMock = vi.fn();

vi.mock("@/hooks/use-desktop", () => ({
  useDesktop: () => false,
}));

vi.mock("@/hooks/use-detail", () => ({
  useDetail: () => ({
    data: null,
    isLoading: false,
    isError: false,
  }),
}));

vi.mock("@/hooks/use-search", () => ({
  runSearch: (...args: unknown[]) => runSearchMock(...args),
}));

vi.mock("@/components/layout/AppHeader", () => ({
  AppHeader: ({ onSearch }: { onSearch?: (query: string) => Promise<void> }) => (
    <button
      type="button"
      onClick={() => {
        if (onSearch) {
          void onSearch("mobile query");
        }
      }}
    >
      mobile-search
    </button>
  ),
}));

vi.mock("@/components/layout/MobileWorkspace", () => ({
  MobileWorkspace: ({
    onSearch,
    results,
  }: {
    onSearch: (query: string) => Promise<void>;
    results: { id: string }[];
  }) => (
    <div>
      <button type="button" onClick={() => void onSearch("mobile query")}>
        run-mobile-search
      </button>
      <div>results-count-{results.length}</div>
    </div>
  ),
}));

vi.mock("@/components/layout/ContextBar", () => ({
  ContextBar: () => <div>context-bar</div>,
}));

vi.mock("@/components/filters/FilterPanel", () => ({
  FilterPanel: () => <div>filter-panel</div>,
}));

vi.mock("@/components/results/ResultSetScopeBar", () => ({
  ResultSetScopeBar: () => <div>scope</div>,
}));

vi.mock("@/components/results/ResultContextHeader", () => ({
  ResultContextHeader: () => <div>context-header</div>,
}));

vi.mock("@/components/results/ResultList", () => ({
  ResultList: () => <div>results</div>,
}));

vi.mock("@/components/detail/DetailPanel", () => ({
  DetailPanel: () => <div>detail</div>,
}));

vi.mock("@/components/ui/resizable-panels", () => ({
  ResizablePanelGroup: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ResizablePanel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ResizableHandle: () => <div />,
}));

describe("WorkspaceClient mobile behavior", () => {
  it("wires mobile header/search trigger to workspace search dispatch", async () => {
    runSearchMock.mockResolvedValue({
      results: [searchResults[0]],
      filters,
    });

    renderWithProviders(<WorkspaceClient searchContext={searchContext} filters={filters} />, {
      initialResults: searchResults,
      searchParams: { q: "Art. 754 OR" },
    });

    fireEvent.click(screen.getByRole("button", { name: "run-mobile-search" }));

    await waitFor(() => {
      expect(runSearchMock).toHaveBeenCalledWith(
        "mobile query",
        expect.objectContaining({
          context: expect.any(Object),
          refinements: expect.any(Array),
        }),
        expect.objectContaining({
          pageSize: expect.any(Number),
        }),
      );
    });
  });
});
