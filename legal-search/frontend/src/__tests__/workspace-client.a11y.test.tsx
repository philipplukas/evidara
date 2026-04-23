import { axe, toHaveNoViolations } from "jest-axe";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import WorkspaceClient from "@/app/WorkspaceClient";
import { filters, searchContext, searchResults } from "@/lib/mock-data";
import { renderWithProviders } from "./helpers/render-with-providers";

expect.extend(toHaveNoViolations);

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

describe("WorkspaceClient route-level accessibility", () => {
  it("has no accessibility violations in default workspace state", async () => {
    const { container } = renderWithProviders(
      <WorkspaceClient searchContext={searchContext} filters={filters} />,
      { initialResults: searchResults },
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("has no accessibility violations with selected item URL state", async () => {
    const { container } = renderWithProviders(
      <WorkspaceClient searchContext={searchContext} filters={filters} />,
      { initialResults: searchResults, searchParams: { item: "law-1" } },
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
