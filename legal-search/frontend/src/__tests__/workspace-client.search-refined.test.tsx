/**
 * Lawyer-journey telemetry: #403 Slice 2 — search.refined.
 *
 * SEARCH_REFINED is the re-execution that happens when a user changes a
 * constraint (official-only toggle, jurisdiction, refinement) while the
 * query text is unchanged. Distinct from SEARCH_EXECUTED, which fires on
 * new-query submission.
 *
 * Test strategy:
 *   1. First executeSearch run (from mount with a URL query) fires
 *      SEARCH_EXECUTED — no prior signature to compare against.
 *   2. Toggle an off-default constraint via a ContextBar stub that dispatches
 *      directly to SearchConstraintsProvider.
 *   3. The effect re-runs executeSearch with the same query, which now
 *      classifies as a refinement.
 */

import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import WorkspaceClient from "@/app/WorkspaceClient";
import { AnalyticsEvent, registerProvider, resetAnalytics } from "@/lib/analytics";
import { filters, searchContext, searchResults } from "@/lib/mock-data";
import { renderWithProviders } from "./helpers/render-with-providers";

const runSearchMock = vi.fn();

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

vi.mock("@/hooks/use-search", () => ({
  runSearch: (...args: unknown[]) => runSearchMock(...args),
}));

vi.mock("@/components/ui/resizable-panels", () => ({
  ResizablePanelGroup: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ResizablePanel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ResizableHandle: () => <div />,
}));

vi.mock("@/components/layout/AppHeader", () => ({
  AppHeader: () => <div>app-header</div>,
}));

// ContextBar stub that exposes a button to flip an off-default constraint.
// We keep the real SearchConstraintsProvider in the provider tree so
// dispatching here drives the real URL state update that the WorkspaceClient
// effect observes.
vi.mock("@/components/layout/ContextBar", async () => {
  const { useSearchConstraints } = await import("@/lib/search-constraints-store");
  return {
    ContextBar: function MockContextBar() {
      const { dispatch } = useSearchConstraints();
      return (
        <button type="button" onClick={() => dispatch({ type: "SET_OFFICIAL_ONLY", value: true })}>
          toggle-official-only
        </button>
      );
    },
  };
});

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

describe("WorkspaceClient — search.refined analytics (#403)", () => {
  const events: Array<{ event: string; properties?: Record<string, unknown> }> = [];

  beforeEach(() => {
    events.length = 0;
    runSearchMock.mockReset();
    runSearchMock.mockResolvedValue({
      results: [searchResults[0]],
      filters,
    });
    resetAnalytics();
    registerProvider({
      track: (event, properties) => {
        events.push({ event, properties });
      },
    });
  });

  afterEach(() => {
    resetAnalytics();
  });

  it("classifies a same-query constraint-change re-execution as SEARCH_REFINED", async () => {
    renderWithProviders(<WorkspaceClient searchContext={searchContext} filters={filters} />, {
      initialResults: searchResults,
      // Non-default jurisdictions so the initial-mount guard lets the first
      // executeSearch run.
      searchParams: { q: "Art. 754 OR", jurisdictions: "at" },
    });

    // First run: SEARCH_EXECUTED — no prior signature.
    await waitFor(() => {
      expect(events.some((e) => e.event === AnalyticsEvent.SEARCH_EXECUTED)).toBe(true);
    });

    const executedBefore = events.filter((e) => e.event === AnalyticsEvent.SEARCH_EXECUTED).length;
    const refinedBefore = events.filter((e) => e.event === AnalyticsEvent.SEARCH_REFINED).length;
    expect(refinedBefore).toBe(0);

    // Flip an off-default constraint → same query, new constraint → refinement.
    fireEvent.click(screen.getByRole("button", { name: "toggle-official-only" }));

    await waitFor(() => {
      expect(events.filter((e) => e.event === AnalyticsEvent.SEARCH_REFINED).length).toBe(1);
    });

    // SEARCH_EXECUTED count must not increase on refinement — the two events
    // are mutually exclusive per executeSearch call.
    expect(events.filter((e) => e.event === AnalyticsEvent.SEARCH_EXECUTED).length).toBe(
      executedBefore,
    );

    const refined = events.find((e) => e.event === AnalyticsEvent.SEARCH_REFINED);
    expect(refined?.properties).toMatchObject({
      query: "Art. 754 OR",
      resultCount: 1,
    });
    expect(
      (refined?.properties as { changedFilterCount: number }).changedFilterCount,
    ).toBeGreaterThan(0);
  });
});
