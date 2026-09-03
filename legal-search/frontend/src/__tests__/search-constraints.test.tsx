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
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import type { ReactNode } from "react";
// Import the actual provider to test through React hooks
import {
  countActiveSearchConstraints,
  SearchConstraintsProvider,
  useSearchConstraints,
} from "@/lib/search-constraints-store";
import { DEFAULT_JURISDICTIONS, DEFAULT_LANGUAGES } from "@/lib/search-params";
import type { SearchRefinement } from "@/lib/types";

function wrapper({ children }: { children: ReactNode }) {
  return (
    <NuqsTestingAdapter>
      <SearchConstraintsProvider>{children}</SearchConstraintsProvider>
    </NuqsTestingAdapter>
  );
}

function wrapperWithSearchParams(searchParams: Record<string, string>) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NuqsTestingAdapter searchParams={searchParams}>
        <SearchConstraintsProvider>{children}</SearchConstraintsProvider>
      </NuqsTestingAdapter>
    );
  };
}

describe("SearchConstraintsProvider", () => {
  /**
   * WHY: The initial state defines the "default search scope."
   * If defaults change accidentally (e.g., jurisdiction shifts from CH to AT),
   * every user sees wrong results on first load.
   */
  it("provides correct initial state", () => {
    const { result } = renderHook(() => useSearchConstraints(), { wrapper });

    expect(result.current.state.context.jurisdictions).toEqual(["ch"]);
    expect(result.current.state.context.languages).toEqual(["de"]);
    // The exported defaults must be the values the store actually reports, not
    // just the values the parser returns. `searchParamsParsers.jurisdictions`
    // used to be documented as canonical while holding `["CH"]`, which
    // `normalizeJurisdictions` lower-cases on the way in — so no consumer ever
    // saw it, and a Server Component adopting `searchParamsCache` would have
    // rendered `CH` and hydrated `ch` (#822).
    expect(result.current.state.context.jurisdictions).toEqual(DEFAULT_JURISDICTIONS);
    expect(result.current.state.context.languages).toEqual(DEFAULT_LANGUAGES);
    expect(result.current.state.context.sourceType).toBeNull();
    expect(result.current.state.context.officialOnly).toBe(false);
    expect(result.current.state.refinements).toEqual([]);
  });

  it("normalizes URL-backed source type and drops invalid refinements", () => {
    const { result } = renderHook(() => useSearchConstraints(), {
      wrapper: wrapperWithSearchParams({
        sourceType: "UNSUPPORTED",
        refinements: JSON.stringify([
          { field: "unknown_field", type: "terms", values: ["x"] },
          { field: "legal_area", type: "terms", values: [" CIVIL ", "unknown"] },
        ]),
      }),
    });

    expect(result.current.state.context.sourceType).toBeNull();
    expect(result.current.state.refinements).toEqual([
      { field: "legal_area", type: "terms", values: ["civil"] },
    ]);
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
      result.current.dispatch({ type: "TOGGLE_JURISDICTION", jurisdiction: "at" });
    });
    expect(result.current.state.context.jurisdictions).toEqual(["ch", "at"]);

    // Remove CH
    act(() => {
      result.current.dispatch({ type: "TOGGLE_JURISDICTION", jurisdiction: "ch" });
    });
    expect(result.current.state.context.jurisdictions).toEqual(["at"]);
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
      field: "legal_area",
      type: "terms",
      values: ["civil"],
    };

    // Set first refinement
    act(() => {
      result.current.dispatch({
        type: "SET_REFINEMENT",
        field: "legal_area",
        refinement: refinement1,
      });
    });
    expect(result.current.state.refinements).toHaveLength(1);
    expect(result.current.state.refinements[0].values).toEqual(["civil"]);

    // Update same field — should replace, not append
    const refinement2: SearchRefinement = {
      field: "legal_area",
      type: "terms",
      values: ["civil", "criminal"],
    };

    act(() => {
      result.current.dispatch({
        type: "SET_REFINEMENT",
        field: "legal_area",
        refinement: refinement2,
      });
    });
    expect(result.current.state.refinements).toHaveLength(1);
    expect(result.current.state.refinements[0].values).toEqual(["civil", "criminal"]);
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
        field: "legal_area",
        refinement: { field: "legal_area", type: "terms", values: ["civil"] },
      });
    });
    act(() => {
      result.current.dispatch({
        type: "SET_REFINEMENT",
        field: "court_level",
        refinement: { field: "court_level", type: "terms", values: ["supreme"] },
      });
    });
    expect(result.current.state.refinements).toHaveLength(2);

    act(() => {
      result.current.dispatch({ type: "CLEAR_REFINEMENT", field: "legal_area" });
    });
    expect(result.current.state.refinements).toHaveLength(1);
    expect(result.current.state.refinements[0].field).toBe("court_level");
  });

  it("CLEAR_ALL_REFINEMENTS removes all refinement filters", () => {
    const { result } = renderHook(() => useSearchConstraints(), { wrapper });

    act(() => {
      result.current.dispatch({
        type: "SET_REFINEMENT",
        field: "legal_area",
        refinement: { field: "legal_area", type: "terms", values: ["civil"] },
      });
    });
    act(() => {
      result.current.dispatch({
        type: "SET_REFINEMENT",
        field: "court_level",
        refinement: { field: "court_level", type: "terms", values: ["supreme"] },
      });
    });
    expect(result.current.state.refinements).toHaveLength(2);

    act(() => {
      result.current.dispatch({ type: "CLEAR_ALL_REFINEMENTS" });
    });

    expect(result.current.state.refinements).toEqual([]);
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
        field: "legal_area",
        refinement: { field: "legal_area", type: "terms", values: ["civil"] },
      });
    });

    // Reset
    act(() => {
      result.current.dispatch({ type: "RESET_ALL" });
    });

    expect(result.current.state.context.jurisdictions).toEqual(["ch"]);
    expect(result.current.state.context.languages).toEqual(["de"]);
    expect(result.current.state.context.sourceType).toBeNull();
    expect(result.current.state.context.officialOnly).toBe(false);
    expect(result.current.state.refinements).toEqual([]);
  });
});

/**
 * WHY: the mobile filter badge renders this count. Counting the seeded
 * `CH` / `de` defaults made it read "2" on a cold load — beside a desktop
 * panel that said "Keine Filter verfügbar" for the same state (#674). The
 * badge must count user choices, not the scope the app arrived with.
 */
describe("countActiveSearchConstraints", () => {
  it("counts nothing in the default state", () => {
    const { result } = renderHook(() => useSearchConstraints(), { wrapper });

    expect(countActiveSearchConstraints(result.current.state)).toBe(0);
  });

  it("counts each dimension the user moves away from the default", () => {
    const { result } = renderHook(() => useSearchConstraints(), { wrapper });

    act(() => {
      result.current.dispatch({ type: "SET_OFFICIAL_ONLY", value: true });
    });
    expect(countActiveSearchConstraints(result.current.state)).toBe(1);

    act(() => {
      result.current.dispatch({ type: "TOGGLE_JURISDICTION", jurisdiction: "AT" });
    });
    expect(countActiveSearchConstraints(result.current.state)).toBe(2);

    act(() => {
      result.current.dispatch({
        type: "SET_REFINEMENT",
        field: "legal_area",
        refinement: { field: "legal_area", type: "terms", values: ["civil"] },
      });
    });
    expect(countActiveSearchConstraints(result.current.state)).toBe(3);
  });

  it("returns to zero after RESET_ALL", () => {
    const { result } = renderHook(() => useSearchConstraints(), { wrapper });

    act(() => {
      result.current.dispatch({ type: "SET_OFFICIAL_ONLY", value: true });
      result.current.dispatch({ type: "RESET_ALL" });
    });

    expect(countActiveSearchConstraints(result.current.state)).toBe(0);
  });
});
