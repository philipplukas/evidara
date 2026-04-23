import { fireEvent, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import WorkspaceClient from "@/app/WorkspaceClient";
import { filters, searchContext, searchResults } from "@/lib/mock-data";
import { useWorkspace } from "@/lib/workspace-store";
import { renderWithProviders } from "./helpers/render-with-providers";

vi.mock("@/hooks/use-desktop", () => ({
  useDesktop: () => true,
}));

vi.mock("@/hooks/use-detail", () => ({
  useDetail: () => ({
    data: null,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
}));

vi.mock("@/components/ui/resizable-panels", () => ({
  ResizablePanelGroup: ({ children }: { children: ReactNode }) => (
    <div data-testid="panel-group">{children}</div>
  ),
  ResizablePanel: ({ children }: { children: ReactNode }) => (
    <section data-testid="panel">{children}</section>
  ),
  ResizableHandle: () => <div data-testid="panel-handle" />,
}));

vi.mock("@/components/layout/AppHeader", () => ({
  AppHeader: function MockAppHeader() {
    const { state } = useWorkspace();
    return (
      <div>
        <span>trail-count-{state.trail.length}</span>
        <span>pinned-count-{state.pinned.length}</span>
      </div>
    );
  },
}));

vi.mock("@/components/layout/ContextBar", () => ({
  ContextBar: () => <div>context-bar</div>,
}));

vi.mock("@/components/filters/FilterPanel", () => ({
  FilterPanel: () => <div>filter-panel</div>,
}));

vi.mock("@/components/results/ResultSetScopeBar", () => ({
  ResultSetScopeBar: () => <div>scope-bar</div>,
}));

vi.mock("@/components/results/ResultContextHeader", () => ({
  ResultContextHeader: () => <div>result-context-header</div>,
}));

vi.mock("@/components/detail/DetailPanel", () => ({
  DetailPanel: () => <div>detail-panel</div>,
}));

vi.mock("@/components/results/ResultList", () => ({
  ResultList: function MockResultList({
    results,
    selectedId,
    onFocus,
  }: {
    results: { id: string }[];
    selectedId: string | null;
    onFocus: (id: string) => void;
  }) {
    return (
      <div>
        <div>selected-{selectedId ?? "none"}</div>
        <button type="button" onClick={() => onFocus(results[0].id)}>
          focus-first
        </button>
      </div>
    );
  },
}));

describe("WorkspaceClient interactions", () => {
  it("hydrates selection from URL state", () => {
    renderWithProviders(<WorkspaceClient searchContext={searchContext} filters={filters} />, {
      initialResults: searchResults,
      searchParams: { item: "law-1" },
    });

    expect(screen.getByText("selected-law-1")).toBeInTheDocument();
  });

  it("records trail entry when focusing a result", () => {
    renderWithProviders(<WorkspaceClient searchContext={searchContext} filters={filters} />, {
      initialResults: searchResults,
    });

    fireEvent.click(screen.getByRole("button", { name: "focus-first" }));

    expect(screen.getByText("selected-law-1")).toBeInTheDocument();
    expect(screen.getByText("trail-count-1")).toBeInTheDocument();
  });

  it("clears URL selection on Escape", () => {
    renderWithProviders(<WorkspaceClient searchContext={searchContext} filters={filters} />, {
      initialResults: searchResults,
      searchParams: { item: "law-1" },
    });

    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.getByText("selected-none")).toBeInTheDocument();
  });
});
