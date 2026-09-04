/**
 * `adminMuiTheme` — MUI theme bridge for legacy resource pages.
 *
 * Maps MUI's semantic palette slots to evidara brand tokens so existing
 * `<Button color="success">`, `<Chip color="error">`, etc. pick up the
 * workspace palette without per-call-site edits. This is a temporary
 * bridge for the v1 → v2 transition (ADR-0026 P4b); once every legacy
 * page is ported to Tailwind primitives this whole file goes away.
 *
 *   primary  → --accent-core      (violet — the one action color)
 *   success  → --accent-core      ("go" actions: Promote, Approve = primary)
 *   error    → --status-critical  (Cancel, Reject, destructive)
 *   warning  → --status-degraded  (attention, pending)
 *   info     → --status-info      (running, in-progress)
 *
 * Tokens are imported from `@evidara/tokens` (the canonical TS mirror of
 * `tokens.css`). MUI's `palette.<slot>.main` only takes a hex/rgb string,
 * not a CSS variable, so we read the literals here.
 *
 * `adminMuiDarkTheme` is the same map against the `.dark` values. Supplying it
 * is what *turns dark mode on*: `react-admin`'s `useTheme()` only consults
 * `prefers-color-scheme` when a `darkTheme` exists, and returns a hard-coded
 * `'light'` otherwise. That single missing prop is why light and dark
 * screenshots of this app were byte-identical. The Tailwind side follows the
 * same resolved mode through `ThemeSync`.
 *
 * Exported as a `RaThemeOptions` (plain options object, not the result of
 * `createTheme`). React-admin's `<Admin theme={…}>` calls `createTheme`
 * internally; pre-calling it caused a runtime page-load failure on the
 * admin shell when the e2e test navigated to `/runs-v2/run_01`.
 */
import {
  ACCENT_CORE,
  ACCENT_CORE_DARK,
  ACCENT_CORE_FOREGROUND,
  BRAND_STRONG_DARK,
  STATUS_CRITICAL,
  STATUS_CRITICAL_DARK,
  STATUS_DEGRADED,
  STATUS_DEGRADED_DARK,
  STATUS_INFO,
  STATUS_INFO_DARK,
  SURFACE_PAGE_DARK,
  SURFACE_PANEL_DARK,
} from "@evidara/tokens";
import type { RaThemeOptions } from "ra-ui-materialui";

export const adminMuiTheme: RaThemeOptions = {
  palette: {
    mode: "light",
    primary: { main: ACCENT_CORE, contrastText: ACCENT_CORE_FOREGROUND },
    success: { main: ACCENT_CORE, contrastText: ACCENT_CORE_FOREGROUND },
    error: { main: STATUS_CRITICAL },
    warning: { main: STATUS_DEGRADED },
    info: { main: STATUS_INFO },
  },
};

export const adminMuiDarkTheme: RaThemeOptions = {
  palette: {
    mode: "dark",
    // No `contrastText`: the dark palette's `--accent-core-foreground` is a near-
    // black in oklch with no hex mirror, and MUI computes a correct contrast
    // colour itself. Inventing a hex that is not in `tokens.css` would be worse
    // than letting MUI derive one.
    primary: { main: ACCENT_CORE_DARK },
    success: { main: ACCENT_CORE_DARK },
    error: { main: STATUS_CRITICAL_DARK },
    warning: { main: STATUS_DEGRADED_DARK },
    info: { main: STATUS_INFO_DARK },
    background: { default: SURFACE_PAGE_DARK, paper: SURFACE_PANEL_DARK },
    text: { primary: BRAND_STRONG_DARK },
  },
};
