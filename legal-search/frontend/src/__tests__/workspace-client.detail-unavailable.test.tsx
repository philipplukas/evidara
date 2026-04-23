import { fireEvent, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WorkspaceClient from "@/app/WorkspaceClient";
import { filters, searchContext, searchResults } from "@/lib/mock-data";
import { renderWithProviders } from "./helpers/render-with-providers";

const refetchMock = vi.fn();
const useDetailMock = vi.fn();

vi.mock("@/hooks/use-desktop", () => ({
  useDesktop: () => true,
}));

vi.mock("@/hooks/use-detail", () => ({
  useDetail: (...args: unknown[]) => useDetailMock(...args),
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
  AppHeader: () => <div>app-header</div>,
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
  ResultList: ({ selectedId }: { selectedId: string | null }) => (
    <div>selected-{selectedId ?? "none"}</div>
  ),
}));

vi.mock("@/components/detail/DetailPanel", () => ({
  DetailPanel: () => <div>detail-panel-real</div>,
}));

describe("WorkspaceClient detail unavailability", () => {
  beforeEach(() => {
    refetchMock.mockReset();
    useDetailMock.mockReset();
  });

  it("renders the not-found state when selectedId resolves to null (404)", () => {
    useDetailMock.mockReturnValue({
      data: null,
      isLoading: false,
      isError: false,
      refetch: refetchMock,
    });

    renderWithProviders(<WorkspaceClient searchContext={searchContext} filters={filters} />, {
      initialResults: searchResults,
      searchParams: { item: "stale-id" },
    });

    expect(screen.getByText("Dieses Dokument ist nicht mehr verfügbar.")).toBeInTheDocument();
    expect(
      screen.getByText("Möglicherweise wurde es entfernt oder der Link ist veraltet."),
    ).toBeInTheDocument();
    expect(screen.queryByText("detail-panel-real")).not.toBeInTheDocument();
  });

  it("closing the not-found panel clears ?item= from the URL", () => {
    useDetailMock.mockReturnValue({
      data: null,
      isLoading: false,
      isError: false,
      refetch: refetchMock,
    });

    renderWithProviders(<WorkspaceClient searchContext={searchContext} filters={filters} />, {
      initialResults: searchResults,
      searchParams: { item: "stale-id" },
    });

    expect(screen.getByText("selected-stale-id")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Zurück zur Ergebnisliste" }));
    expect(screen.getByText("selected-none")).toBeInTheDocument();
  });

  it("renders retry + close actions when the detail fetch errors (5xx)", () => {
    useDetailMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: refetchMock,
    });

    renderWithProviders(<WorkspaceClient searchContext={searchContext} filters={filters} />, {
      initialResults: searchResults,
      searchParams: { item: "law-1" },
    });

    expect(screen.getByText("Dokumentdetails konnten nicht geladen werden.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Erneut laden" }));
    expect(refetchMock).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Zurück zur Ergebnisliste" }));
    expect(screen.getByText("selected-none")).toBeInTheDocument();
  });
});
