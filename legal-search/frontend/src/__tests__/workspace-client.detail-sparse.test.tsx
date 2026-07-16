import { screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import WorkspaceClient from "@/app/WorkspaceClient";
import { filters, searchContext, searchResults } from "@/lib/mock-data";
import type { DetailViewModel } from "@/lib/types";
import { renderWithProviders } from "./helpers/render-with-providers";

const sparseDetail: DetailViewModel = {
  id: "law-1",
  type: "law",
  title: "",
  subtitle: "",
  breadcrumbs: [],
  metadata: [],
  contentText: "",
  contentLanguage: {
    display: "en",
    original: "de",
    isTranslation: true,
    label: "",
  },
  tabs: [{ key: "details", label: "Details" }],
  relatedGroups: [],
  references: [],
  annotations: [],
};

vi.mock("@/hooks/use-desktop", () => ({
  useDesktop: () => true,
}));

vi.mock("@/hooks/use-detail", () => ({
  useDetail: () => ({
    data: sparseDetail,
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
  AppHeader: () => <div>app-header</div>,
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

describe("WorkspaceClient sparse detail integration", () => {
  it("renders detail fallback UI for sparse payloads through real DetailPanel", () => {
    renderWithProviders(<WorkspaceClient searchContext={searchContext} filters={filters} />, {
      initialResults: searchResults,
      searchParams: { item: "law-1" },
    });

    expect(screen.getByText("Dokument ohne Titel")).toBeInTheDocument();
    expect(screen.getByText("Keine Zusammenfassung verfügbar")).toBeInTheDocument();
    expect(screen.getByText("Übersetzter Inhalt")).toBeInTheDocument();
    expect(screen.getByText("Keine Dokumentdetails")).toBeInTheDocument();
  });
});
