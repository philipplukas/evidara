/**
 * Guards the in-memory localStorage polyfill installed in `setup.ts`.
 *
 * Node >= 24 ships an experimental built-in `localStorage` global that resolves
 * to `undefined` without `--localstorage-file`, shadowing jsdom's Storage under
 * Vitest. Without the polyfill, every suite touching storage fails with
 * "Cannot read properties of undefined (reading 'clear')" on workstations
 * running newer Node than CI's pinned 22. This test makes that regression
 * surface here — as one legible failure — rather than across a dozen suites.
 * See #596.
 */
import { describe, expect, it } from "vitest";

describe("test-environment localStorage", () => {
  it("is defined and usable via window and the bare global (same instance)", () => {
    expect(window.localStorage).toBeDefined();
    expect(typeof window.localStorage.clear).toBe("function");

    window.localStorage.setItem("evidara:probe", "1");
    // Components read via both `window.localStorage` and bare `localStorage`;
    // both must observe the same store.
    expect(localStorage.getItem("evidara:probe")).toBe("1");

    window.localStorage.clear();
    expect(window.localStorage.getItem("evidara:probe")).toBeNull();
  });
});
