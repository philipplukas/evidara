/**
 * Workspace Reducer — Unit Tests
 *
 * WHY THESE TESTS EXIST:
 * The workspace reducer owns the navigation model: result sets, pivots,
 * back-stack, trail, and pinned items. This is the "memory" of the
 * user's exploration session.
 *
 * If pivoting breaks the back-stack, users lose their navigation trail.
 * If pinning fails, users lose their bookmarked documents.
 * Both are session-destroying bugs in an exploratory legal research tool.
 *
 * WHAT WE TEST:
 * - PIVOT pushes current result set to stack and sets new one
 * - BACK pops the stack correctly
 * - PIN/UNPIN are idempotent and don't duplicate
 * - Trail grows on PUSH_TRAIL
 *
 * WHAT WE DON'T TEST:
 * - URL parameter sync (?item=) — that's WorkspaceClient's responsibility
 * - Detail panel rendering — that's a component concern
 */

import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import type { SearchResultViewModel } from "@/lib/types";
import { useWorkspace, WorkspaceProvider } from "@/lib/workspace-store";

const mockResults: SearchResultViewModel[] = [
  {
    id: "r1",
    title: "Art. 754 OR",
    subtitle: "Verantwortlichkeit",
    snippet: "Die Mitglieder des Verwaltungsrates...",
    type: "law",
    badges: [{ label: "Law", colorKey: "blue" }],
    metadataRows: [],
    relatedCounts: [],
    actions: [],
  },
];

const pivotResults: SearchResultViewModel[] = [
  {
    id: "r2",
    title: "BGer 4A_123/2022",
    subtitle: "Federal Supreme Court",
    snippet: "In consideration of...",
    type: "decision",
    badges: [{ label: "Decision", colorKey: "pink" }],
    metadataRows: [],
    relatedCounts: [],
    actions: [],
  },
];

function wrapper({ children }: { children: ReactNode }) {
  return (
    <WorkspaceProvider initialResults={mockResults} initialQuery="Art 754 OR">
      {children}
    </WorkspaceProvider>
  );
}

describe("WorkspaceProvider", () => {
  /**
   * WHY: The initial state defines what the user sees on first load.
   * The result set must contain the search results, the scope label
   * must reflect the query, and the back-stack must be empty.
   */
  it("initializes with search results and empty stack", () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });

    expect(result.current.state.resultSet.items).toHaveLength(1);
    expect(result.current.state.resultSet.source).toEqual({
      type: "search",
      query: "Art 754 OR",
    });
    expect(result.current.state.resultSetStack).toHaveLength(0);
    expect(result.current.state.trail).toHaveLength(0);
    expect(result.current.state.pinned).toHaveLength(0);
  });

  /**
   * WHY: PIVOT is how users "drill into" related content — e.g., from
   * a statute to its court decisions. The current result set MUST be
   * pushed to the stack so BACK works. If this fails, users lose their
   * original search results with no way to return.
   */
  it("PIVOT pushes current results to stack and sets new results", () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });

    act(() => {
      result.current.dispatch({
        type: "PIVOT",
        source: {
          type: "pivot",
          label: "Decisions",
          parentSource: result.current.state.resultSet.source,
        },
        results: pivotResults,
        scopeLabel: "Decisions for Art. 754 OR",
      });
    });

    // New result set is the pivot results
    expect(result.current.state.resultSet.items).toEqual(pivotResults);
    expect(result.current.state.resultSet.scopeLabel).toBe("Decisions for Art. 754 OR");

    // Previous result set is on the stack
    expect(result.current.state.resultSetStack).toHaveLength(1);
    expect(result.current.state.resultSetStack[0].items).toEqual(mockResults);
  });

  /**
   * WHY: BACK must restore the previous result set exactly.
   * If it corrupts state or doesn't pop the stack, users either
   * see wrong results or can't navigate back at all.
   */
  it("BACK restores previous result set from stack", () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });

    // Pivot first
    act(() => {
      result.current.dispatch({
        type: "PIVOT",
        source: {
          type: "pivot",
          label: "Decisions",
          parentSource: result.current.state.resultSet.source,
        },
        results: pivotResults,
        scopeLabel: "Decisions for Art. 754 OR",
      });
    });

    // Then go back
    act(() => {
      result.current.dispatch({ type: "BACK" });
    });

    expect(result.current.state.resultSet.items).toEqual(mockResults);
    expect(result.current.state.resultSetStack).toHaveLength(0);
  });

  /**
   * WHY: BACK on an empty stack must be a no-op. If it crashes or
   * corrupts state, the entire workspace breaks.
   */
  it("BACK on empty stack is a no-op", () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });

    const stateBefore = result.current.state;
    act(() => {
      result.current.dispatch({ type: "BACK" });
    });

    expect(result.current.state).toBe(stateBefore);
  });

  /**
   * WHY: Pinned items persist across pivots — they're the user's
   * "working set" of important documents. PIN must be idempotent
   * (pinning the same item twice doesn't duplicate it).
   */
  it("PIN is idempotent — no duplicates", () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });

    act(() => {
      result.current.dispatch({
        type: "PIN",
        item: { id: "r1", title: "Art. 754 OR", type: "law" },
      });
      result.current.dispatch({
        type: "PIN",
        item: { id: "r1", title: "Art. 754 OR", type: "law" },
      });
    });

    expect(result.current.state.pinned).toHaveLength(1);
  });

  /**
   * WHY: UNPIN must remove exactly the specified item.
   * Note we don't test "UNPIN on non-existent item" because
   * the reducer handles it gracefully (filter returns same array).
   */
  it("UNPIN removes the specified item", () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });

    act(() => {
      result.current.dispatch({
        type: "PIN",
        item: { id: "r1", title: "Art. 754 OR", type: "law" },
      });
      result.current.dispatch({
        type: "PIN",
        item: { id: "r2", title: "BGer 4A_123", type: "decision" },
      });
    });
    expect(result.current.state.pinned).toHaveLength(2);

    act(() => {
      result.current.dispatch({ type: "UNPIN", id: "r1" });
    });
    expect(result.current.state.pinned).toHaveLength(1);
    expect(result.current.state.pinned[0].id).toBe("r2");
  });

  /**
   * WHY: The trail records the user's exploration path. It's used
   * for breadcrumb-like UI and session replay. Each PUSH_TRAIL
   * must append, not replace.
   */
  it("PUSH_TRAIL appends entries", () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });

    act(() => {
      result.current.dispatch({
        type: "PUSH_TRAIL",
        entry: { id: "r1", title: "Art. 754 OR", type: "law", timestamp: 1000 },
      });
      result.current.dispatch({
        type: "PUSH_TRAIL",
        entry: { id: "r2", title: "BGer 4A_123", type: "decision", timestamp: 2000 },
      });
    });

    expect(result.current.state.trail).toHaveLength(2);
    expect(result.current.state.trail[0].id).toBe("r1");
    expect(result.current.state.trail[1].id).toBe("r2");
  });

  it("RESET_FROM_BOOT synchronizes workspace to latest bootstrap state", () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });

    act(() => {
      result.current.dispatch({
        type: "PIVOT",
        source: {
          type: "pivot",
          label: "Decisions",
          parentSource: result.current.state.resultSet.source,
        },
        results: pivotResults,
        scopeLabel: "Decisions",
      });
      result.current.dispatch({
        type: "PUSH_TRAIL",
        entry: { id: "r2", title: "BGer 4A_123", type: "decision", timestamp: 1 },
      });
    });

    act(() => {
      result.current.dispatch({
        type: "RESET_FROM_BOOT",
        query: "New query",
        results: mockResults,
      });
    });

    expect(result.current.state.resultSet.source).toEqual({ type: "search", query: "New query" });
    expect(result.current.state.resultSetStack).toEqual([]);
    expect(result.current.state.trail).toEqual([]);
  });
});
