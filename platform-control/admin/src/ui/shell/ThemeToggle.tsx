/**
 * `ThemeSync` + `ThemeToggle` — the two halves of the admin's dark mode.
 *
 * The app had none. Light and dark screenshots were byte-identical and the
 * stylesheet held zero `prefers-color-scheme` rules, so an operator whose OS is
 * dark got a full-brightness white control plane at whatever hour they were
 * paged. The palette was never the missing piece — `styles/tokens/tokens.css`
 * has always carried a complete `.dark` block.
 *
 * `react-admin` owns the mode value (`useTheme()` — OS default, explicit choice
 * persisted in its store, MUI driven from it). These components do not
 * introduce a second one:
 *
 *   `ThemeSync`   reads RA's resolved mode and mirrors it onto <html>, which is
 *                 where the token palette keys off. Renders nothing.
 *   `ThemeToggle` writes RA's mode. One control, in the header, where an
 *                 operator can find it.
 */
"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect } from "react";
import { useTheme } from "react-admin";
import { applyThemeToDocument, type ThemeMode, toggleThemeMode } from "../../lib/admin/theme";

/**
 * `useTheme()` is typed as returning a `RaThemeOptions | ThemeType`-ish union
 * across versions; the only values it ever stores are the two mode strings.
 * Narrowing here keeps the coercion in one place instead of at both call sites.
 */
function asMode(value: unknown): ThemeMode {
  return value === "dark" ? "dark" : "light";
}

/**
 * Mirrors react-admin's theme mode onto `document.documentElement`.
 *
 * Mounted inside `AppShell`, i.e. inside `<Admin>`, because `useTheme` needs
 * react-admin's store and theme context. The inline script in `layout.tsx` has
 * already applied the same value before paint; this keeps it in step when the
 * operator changes it, and when another tab does (RA's localStorage store
 * publishes cross-tab).
 */
export function ThemeSync() {
  const [theme] = useTheme();
  const mode = asMode(theme);

  useEffect(() => {
    applyThemeToDocument(document.documentElement, mode);
  }, [mode]);

  return null;
}

const NEXT_LABEL: Record<ThemeMode, string> = {
  light: "Switch to dark theme",
  dark: "Switch to light theme",
};

/**
 * Header control. Two states, not three: react-admin's store holds only
 * `light` / `dark`, and a "system" option would need a third value it does not
 * model. The OS preference is still honoured — it is the default until an
 * operator overrides it here.
 */
export function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const mode = asMode(theme);
  const Icon = mode === "dark" ? Sun : Moon;

  return (
    <button
      type="button"
      onClick={() => setTheme(toggleThemeMode(mode))}
      aria-label={NEXT_LABEL[mode]}
      title={NEXT_LABEL[mode]}
      data-testid="theme-toggle"
      data-theme-mode={mode}
      className="inline-flex items-center justify-center rounded-full border border-[var(--admin-on-brand-border)] bg-[var(--admin-on-brand-wash)] text-[var(--admin-on-brand)] transition-colors hover:bg-[var(--admin-on-brand-wash-hover)] hover:border-[var(--admin-on-brand-border-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] focus-visible:ring-offset-2 w-11 h-11 sm:w-10 sm:h-10 shrink-0"
    >
      <Icon size={16} strokeWidth={2.2} aria-hidden />
    </button>
  );
}
