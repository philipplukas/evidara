/**
 * Search Constraints Reducer — Unit Tests
 *
 * WHY THESE TESTS EXIST:
 * The SearchConstraintsProvider owns all search intent state —
 * jurisdictions, languages, source types, and ES-ready refinements.
 * Every search API call will be derived from this state.
 *
 * If the reducer produces wrong state, users get wrong search results.
 * That's the highest-impact bug category for a legal search tool.
 *
 * WHAT WE TEST:
 * Pure reducer logic only — no rendering, no React. This is the cheapest
 * test type with the highest signal-to-noise ratio.
 *
 * WHAT WE DON'T TEST:
 * - React rendering of the provider (covered by integration tests)
 * - Specific UI interactions (covered by user flow tests)
 */

import { describe, expect, it } from "vitest";

// We test the reducer directly by re-implementing it inline.
// This avoids coupling to the module's internal export structure.
// When the store exports the reducer, we can import it directly.

import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
// Import the actual provider to test through React hooks
import { SearchConstraintsProvider, useSearchConstraints } from "@/lib/search-constraints-store";
import type { SearchRefinement } from "@/lib/types";

function wrapper({ children }: { children: ReactNode }) {
  return <SearchConstraintsProvider>{children}</SearchConstraintsProvider>;
}

describe("SearchConstraintsProvider", () => {
  /**
   * WHY: The initial state defines the "default search scope."
   * If defaults change accidentally (e.g., jurisdiction shifts from CH to AT),
   * every user sees wrong results on first load.
   */
  it("provides correct initial state", () => {
    const { result } = renderHook(() => useSearchConstraints(), { wrapper });

    expect(result.current.state.context.jurisdictions).toEqual(["CH"]);
    expect(result.current.state.context.languages).toEqual(["de"]);
    expect(result.current.state.context.sourceType).toBeNull();
    expect(result.current.state.context.officialOnly).toBe(false);
    expect(result.current.state.refinements).toEqual([]);
  });

  /**
   * WHY: Jurisdiction toggling directly controls which OpenSearch index
   * partitions are queried. A broken toggle means missing results or
   * results from the wrong legal system — a critical correctness bug.
   */
  it("TOGGLE_JURISDICTION adds and removes jurisdictions", () => {
    const { result } = renderHook(() => useSearchConstraints(), { wrapper });

    // Add AT
    act(() => {
      result.current.dispatch({ type: "TOGGLE_JURISDICTION", jurisdiction: "AT" });
    });
    expect(result.current.state.context.jurisdictions).toEqual(["CH", "AT"]);

    // Remove CH
    act(() => {
      result.current.dispatch({ type: "TOGGLE_JURISDICTION", jurisdiction: "CH" });
    });
    expect(result.current.state.context.jurisdictions).toEqual(["AT"]);
  });

  /**
   * WHY: Language toggling controls search-time language filtering.
   * Getting this wrong means users either miss translated content
   * or see content in languages they can't read.
   */
  it("TOGGLE_LANGUAGE adds and removes languages", () => {
    const { result } = renderHook(() => useSearchConstraints(), { wrapper });

    act(() => {
      result.current.dispatch({ type: "TOGGLE_LANGUAGE", language: "fr" });
    });
    expect(result.current.state.context.languages).toEqual(["de", "fr"]);

    act(() => {
      result.current.dispatch({ type: "TOGGLE_LANGUAGE", language: "de" });
    });
    expect(result.current.state.context.languages).toEqual(["fr"]);
  });

  /**
   * WHY: Refinements are the ES-ready filter shapes that map directly to
   * Elasticsearch aggregation queries. If SET_REFINEMENT doesn't properly
   * upsert (replace existing refinement on same field), we'd send
   * duplicate or conflicting filter clauses to ES.
   */
  it("SET_REFINEMENT upserts by field", () => {
    const { result } = renderHook(() => useSearchConstraints(), { wrapper });

    const refinement1: SearchRefinement = {
      field: "court",
      type: "terms",
      values: ["BGer"],
    };

    // Set first refinement
    act(() => {
      result.current.dispatch({
        type: "SET_REFINEMENT",
        field: "court",
        refinement: refinement1,
      });
    });
    expect(result.current.state.refinements).toHaveLength(1);
    expect(result.current.state.refinements[0].values).toEqual(["BGer"]);

    // Update same field — should replace, not append
    const refinement2: SearchRefinement = {
      field: "court",
      type: "terms",
      values: ["BGer", "BVGer"],
    };

    act(() => {
      result.current.dispatch({
        type: "SET_REFINEMENT",
        field: "court",
        refinement: refinement2,
      });
    });
    expect(result.current.state.refinements).toHaveLength(1);
    expect(result.current.state.refinements[0].values).toEqual(["BGer", "BVGer"]);
  });

  /**
   * WHY: CLEAR_REFINEMENT must remove exactly one field's refinement
   * without affecting others. A bug here silently drops user-applied filters.
   */
  it("CLEAR_REFINEMENT removes only the specified field", () => {
    const { result } = renderHook(() => useSearchConstraints(), { wrapper });

    act(() => {
      result.current.dispatch({
        type: "SET_REFINEMENT",
        field: "court",
        refinement: { field: "court", type: "terms", values: ["BGer"] },
      });
      result.current.dispatch({
        type: "SET_REFINEMENT",
        field: "year",
        refinement: { field: "year", type: "terms", values: ["2024"] },
      });
    });
    expect(result.current.state.refinements).toHaveLength(2);

    act(() => {
      result.current.dispatch({ type: "CLEAR_REFINEMENT", field: "court" });
    });
    expect(result.current.state.refinements).toHaveLength(1);
    expect(result.current.state.refinements[0].field).toBe("year");
  });

  /**
   * WHY: RESET_ALL is the "start over" escape hatch. If it leaves
   * stale refinements, users get confused by phantom filters.
   */
  it("RESET_ALL returns to initial state", () => {
    const { result } = renderHook(() => useSearchConstraints(), { wrapper });

    // Mutate state
    act(() => {
      result.current.dispatch({ type: "TOGGLE_JURISDICTION", jurisdiction: "AT" });
      result.current.dispatch({ type: "SET_OFFICIAL_ONLY", value: true });
      result.current.dispatch({
        type: "SET_REFINEMENT",
        field: "court",
        refinement: { field: "court", type: "terms", values: ["BGer"] },
      });
    });

    // Reset
    act(() => {
      result.current.dispatch({ type: "RESET_ALL" });
    });

    expect(result.current.state.context.jurisdictions).toEqual(["CH"]);
    expect(result.current.state.context.languages).toEqual(["de"]);
    expect(result.current.state.context.sourceType).toBeNull();
    expect(result.current.state.context.officialOnly).toBe(false);
    expect(result.current.state.refinements).toEqual([]);
  });
});
