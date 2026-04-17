/**
 * Design tokens shared across the admin surface.
 *
 * Mirrors the `--shadow-card`, motion timing, and `--accent-core` family from
 * `legal-search/frontend/src/app/globals.css` so both surfaces read from a
 * single vocabulary for elevation, state signalling, and motion.
 *
 * See: `legal-search/frontend/docs/design-system.md` §"Surface elevation &
 * shadows" and §"Accent-core token family" (Sprint 1 — TAR-244).
 */

export const SHADOW_CARD = "0 1px 3px rgba(15, 76, 129, 0.08), 0 1px 2px rgba(15, 76, 129, 0.04)";
export const SHADOW_CARD_HOVER =
  "0 6px 18px rgba(15, 76, 129, 0.10), 0 2px 6px rgba(15, 76, 129, 0.06)";

export const MOTION_DURATION_SHORT = "120ms";
export const MOTION_DURATION_MEDIUM = "180ms";
export const MOTION_DURATION_LONG = "240ms";
export const MOTION_EASING_STANDARD = "cubic-bezier(0.2, 0, 0, 1)";

/**
 * Evidara violet. Hex approximation of `oklch(0.55 0.24 285)` — used
 * wherever MUI expects a static color string (sx props, theme overrides).
 *
 * **Use for:** active-state signalling (selected nav item, active tab
 * indicator, count badges on tabs). **Do not use for:** primary CTAs
 * ("Launch run", "Suchen" — those stay `--brand`) or destructive state.
 */
export const ACCENT_CORE = "#7c3aed";
export const ACCENT_CORE_FOREGROUND = "#fffdf8";
export const ACCENT_CORE_SUBTLE = "rgba(124, 58, 237, 0.12)";
export const ACCENT_CORE_MUTED = "rgba(124, 58, 237, 0.2)";
