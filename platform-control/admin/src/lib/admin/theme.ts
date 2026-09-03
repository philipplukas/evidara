/**
 * Theme plumbing for the admin shell.
 *
 * There was no dark mode at all: light and dark screenshots of the running app
 * were byte-identical, and the compiled stylesheet contained zero
 * `prefers-color-scheme` rules. What made that surprising is that the *palette*
 * had existed the whole time — `styles/tokens/tokens.css` carries a complete
 * `.dark` block for every shared token. Nothing put the class on the document.
 *
 * `react-admin` already models the mode. `useTheme()` reads
 * `prefers-color-scheme` as its default (only when a `darkTheme` is supplied —
 * which is the bit this repo never did), persists an explicit operator choice in
 * its own store under `RaStore.theme`, and drives the MUI `ThemeProvider`.
 * Running a second theme system beside it would give two sources of truth for
 * one question, so this module does the opposite: it reads RA's value and
 * mirrors it onto the document element, where the token block keys off it.
 *
 * Everything here is pure so the pre-paint script and the React component
 * cannot drift apart on what "dark" means.
 */

/** The `ra-core` store key `useTheme()` writes. `RaStore` is `ra-core`'s prefix. */
export const RA_THEME_STORAGE_KEY = "RaStore.theme";

export type ThemeMode = "light" | "dark";

/**
 * Apply a mode to the document element.
 *
 * `classList` (not a `data-` attribute) because `styles/tokens/tokens.css`
 * already defines its dark palette under `.dark`; keying off anything else
 * would mean restating the entire palette.
 */
export function applyThemeToDocument(root: HTMLElement, mode: ThemeMode): void {
  root.classList.toggle("dark", mode === "dark");
  // Native form controls, scrollbars and the canvas behind the page follow
  // `color-scheme`, and none of them read a CSS class.
  root.style.colorScheme = mode;
}

/**
 * Resolve the mode the *first paint* should use, from what is knowable before
 * React mounts: the persisted choice, else the OS preference.
 *
 * Returning "light" for an unreadable store is deliberate — a private window
 * where `localStorage` throws must still render, and light is what the app
 * rendered for its whole life before this.
 */
export function resolveInitialThemeMode(input: {
  storedValue: string | null;
  prefersDark: boolean;
}): ThemeMode {
  const stored = parseStoredThemeMode(input.storedValue);
  if (stored) {
    return stored;
  }
  return input.prefersDark ? "dark" : "light";
}

/**
 * Read a mode out of the raw string `ra-core`'s localStorage store holds.
 *
 * The store JSON-encodes its values, so the key holds `"dark"` *with* quotes.
 * Both forms are accepted rather than assuming an encoding this module does not
 * own; anything else is `null`, meaning "no choice recorded".
 */
export function parseStoredThemeMode(raw: string | null): ThemeMode | null {
  if (!raw) {
    return null;
  }
  const value = raw.trim().replace(/^"|"$/g, "");
  return value === "dark" || value === "light" ? value : null;
}

/** The other mode. Used by the header toggle. */
export function toggleThemeMode(mode: ThemeMode): ThemeMode {
  return mode === "dark" ? "light" : "dark";
}

/**
 * The pre-paint script, as a string for `layout.tsx`.
 *
 * It runs before React and before first paint, so an operator whose OS is dark
 * never sees a white flash of the light theme. Wrapped in try/catch because
 * `localStorage` *throws* (not returns null) in some privacy modes, and a theme
 * preference is never worth a blank page.
 *
 * Kept as a literal rather than serialising the functions above: those are
 * modules, and this has to be inlineable, self-contained and dependency-free.
 * The token-level contract it must match is exactly two lines — the `dark`
 * class and `color-scheme` — and `theme.test.ts` asserts the script contains
 * both alongside the shared storage key.
 */
export const THEME_PRE_PAINT_SCRIPT = `
(function () {
  try {
    var stored = window.localStorage.getItem(${JSON.stringify(RA_THEME_STORAGE_KEY)});
    var value = stored ? stored.trim().replace(/^"|"$/g, "") : null;
    var mode =
      value === "dark" || value === "light"
        ? value
        : window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light";
    document.documentElement.classList.toggle("dark", mode === "dark");
    document.documentElement.style.colorScheme = mode;
  } catch (error) {
    /* No storage, no media query, no theme. The app still renders. */
  }
})();
`.trim();
