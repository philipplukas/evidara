/**
 * Undo for destructive filter reset (#400)
 *
 * WHY THESE TESTS EXIST:
 * `RESET_ALL` wipes every active constraint (jurisdictions, languages,
 * source type, official-only, refinements) with no server round-trip —
 * so the only recovery path is client-side. If `UNDO_RESET` loses or
 * corrupts the snapshot, the undo affordance is a lie and the user has
 * no way back to their previous filter set.
 *
 * WHAT WE TEST (reducer-level, no rendering):
 * - RESET_ALL still clears state (regression guard for the existing behavior)
 * - UNDO_RESET after RESET_ALL restores the pre-reset constraints exactly
 * - UNDO_RESET is a no-op when no snapshot is available (e.g. page load)
 * - A subsequent user filter edit invalidates the snapshot, so UNDO_RESET
 *   after that edit no longer resurrects stale state
 */

import { act, renderHook } from "@testing-library/react";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { SearchConstraintsProvider, useSearchConstraints } from "@/lib/search-constraints-store";

function wrapper({ children }: { children: ReactNode }) {
  return (
    <NuqsTestingAdapter>
      <SearchConstraintsProvider>{children}</SearchConstraintsProvider>
    </NuqsTestingAdapter>
  );
}

describe("SearchConstraintsProvider — UNDO_RESET", () => {
  it("RESET_ALL followed by UNDO_RESET restores pre-reset constraints", () => {
    const { result } = renderHook(() => useSearchConstraints(), { wrapper });

    // Establish a non-default state the user would be surprised to lose.
    act(() => {
      result.current.dispatch({ type: "TOGGLE_JURISDICTION", jurisdiction: "at" });
      result.current.dispatch({ type: "TOGGLE_LANGUAGE", language: "fr" });
      result.current.dispatch({ type: "SET_SOURCE_TYPE", sourceType: "decision" });
      result.current.dispatch({ type: "SET_OFFICIAL_ONLY", value: true });
      result.current.dispatch({
        type: "SET_REFINEMENT",
        field: "legal_area",
        refinement: { field: "legal_area", type: "terms", values: ["civil"] },
      });
    });

    const beforeReset = result.current.state;
    expect(beforeReset.context.jurisdictions).toEqual(["ch", "at"]);
    expect(beforeReset.context.languages).toEqual(["de", "fr"]);
    expect(beforeReset.context.sourceType).toBe("decision");
    expect(beforeReset.context.officialOnly).toBe(true);
    expect(beforeReset.refinements).toHaveLength(1);

    // Destructive reset wipes everything.
    act(() => {
      result.current.dispatch({ type: "RESET_ALL" });
    });
    expect(result.current.state.context.jurisdictions).toEqual(["ch"]);
    expect(result.current.state.context.languages).toEqual(["de"]);
    expect(result.current.state.context.sourceType).toBeNull();
    expect(result.current.state.context.officialOnly).toBe(false);
    expect(result.current.state.refinements).toEqual([]);

    // Undo brings everything back.
    act(() => {
      result.current.dispatch({ type: "UNDO_RESET" });
    });
    expect(result.current.state.context.jurisdictions).toEqual(beforeReset.context.jurisdictions);
    expect(result.current.state.context.languages).toEqual(beforeReset.context.languages);
    expect(result.current.state.context.sourceType).toBe(beforeReset.context.sourceType);
    expect(result.current.state.context.officialOnly).toBe(beforeReset.context.officialOnly);
    expect(result.current.state.refinements).toEqual(beforeReset.refinements);
  });

  it("UNDO_RESET is a no-op when no snapshot has been captured", () => {
    const { result } = renderHook(() => useSearchConstraints(), { wrapper });

    // Move off defaults so we can observe that undo does *not* touch state.
    act(() => {
      result.current.dispatch({ type: "TOGGLE_LANGUAGE", language: "fr" });
    });
    const beforeUndo = result.current.state;
    expect(beforeUndo.context.languages).toEqual(["de", "fr"]);

    act(() => {
      result.current.dispatch({ type: "UNDO_RESET" });
    });

    expect(result.current.state.context.languages).toEqual(beforeUndo.context.languages);
  });

  it("clears the snapshot when the user makes an explicit filter change after reset", () => {
    const { result } = renderHook(() => useSearchConstraints(), { wrapper });

    // Populate, reset (captures snapshot), then edit — which must invalidate
    // the snapshot so a late UNDO_RESET doesn't resurrect stale state.
    act(() => {
      result.current.dispatch({ type: "TOGGLE_JURISDICTION", jurisdiction: "at" });
    });
    act(() => {
      result.current.dispatch({ type: "RESET_ALL" });
    });
    act(() => {
      result.current.dispatch({ type: "TOGGLE_LANGUAGE", language: "fr" });
    });

    const afterEdit = result.current.state;
    expect(afterEdit.context.jurisdictions).toEqual(["ch"]);
    expect(afterEdit.context.languages).toEqual(["de", "fr"]);

    act(() => {
      result.current.dispatch({ type: "UNDO_RESET" });
    });

    // Snapshot was invalidated by the TOGGLE_LANGUAGE above → undo is a no-op,
    // and the user's most recent edit is preserved.
    expect(result.current.state.context.jurisdictions).toEqual(afterEdit.context.jurisdictions);
    expect(result.current.state.context.languages).toEqual(afterEdit.context.languages);
  });
});
