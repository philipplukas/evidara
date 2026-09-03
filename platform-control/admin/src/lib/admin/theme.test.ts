import { describe, expect, it } from "vitest";
import {
  applyThemeToDocument,
  parseStoredThemeMode,
  RA_THEME_STORAGE_KEY,
  resolveInitialThemeMode,
  THEME_PRE_PAINT_SCRIPT,
  toggleThemeMode,
} from "./theme";

describe("parseStoredThemeMode", () => {
  it("reads the JSON-encoded value ra-core's store writes", () => {
    expect(parseStoredThemeMode('"dark"')).toBe("dark");
    expect(parseStoredThemeMode('"light"')).toBe("light");
  });

  it("also accepts the bare value, rather than assuming an encoding it does not own", () => {
    expect(parseStoredThemeMode("dark")).toBe("dark");
  });

  it("treats anything else as no recorded choice", () => {
    expect(parseStoredThemeMode(null)).toBeNull();
    expect(parseStoredThemeMode("")).toBeNull();
    expect(parseStoredThemeMode('"sepia"')).toBeNull();
  });
});

describe("resolveInitialThemeMode", () => {
  it("honours an explicit stored choice over the OS preference", () => {
    expect(resolveInitialThemeMode({ storedValue: '"light"', prefersDark: true })).toBe("light");
    expect(resolveInitialThemeMode({ storedValue: '"dark"', prefersDark: false })).toBe("dark");
  });

  it("falls back to the OS preference — the case that was broken", () => {
    // An operator on a dark OS used to get a full-brightness white panel with
    // no toggle. Without a stored choice, the OS is the answer.
    expect(resolveInitialThemeMode({ storedValue: null, prefersDark: true })).toBe("dark");
    expect(resolveInitialThemeMode({ storedValue: null, prefersDark: false })).toBe("light");
  });
});

describe("applyThemeToDocument", () => {
  it("keys off the `dark` class the shared token palette already defines", () => {
    const root = document.createElement("html");

    applyThemeToDocument(root, "dark");
    expect(root.classList.contains("dark")).toBe(true);
    expect(root.style.colorScheme).toBe("dark");

    applyThemeToDocument(root, "light");
    expect(root.classList.contains("dark")).toBe(false);
    expect(root.style.colorScheme).toBe("light");
  });
});

describe("toggleThemeMode", () => {
  it("flips", () => {
    expect(toggleThemeMode("light")).toBe("dark");
    expect(toggleThemeMode("dark")).toBe("light");
  });
});

describe("THEME_PRE_PAINT_SCRIPT", () => {
  it("agrees with applyThemeToDocument on what applying a theme means", () => {
    // The script cannot import the helper (it is inlined before any bundle
    // runs), so this is the seam where the two could drift.
    expect(THEME_PRE_PAINT_SCRIPT).toContain(JSON.stringify(RA_THEME_STORAGE_KEY));
    expect(THEME_PRE_PAINT_SCRIPT).toContain('classList.toggle("dark"');
    expect(THEME_PRE_PAINT_SCRIPT).toContain("style.colorScheme");
    expect(THEME_PRE_PAINT_SCRIPT).toContain("prefers-color-scheme: dark");
  });

  it("cannot blank the page when storage throws", () => {
    // localStorage throws rather than returning null in some privacy modes.
    expect(THEME_PRE_PAINT_SCRIPT).toContain("try {");
    expect(THEME_PRE_PAINT_SCRIPT).toContain("catch");
  });
});
