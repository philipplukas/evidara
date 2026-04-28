/**
 * Evidara design tokens — canonical TypeScript source of truth.
 *
 * Consumed by JS-side themers (admin's MUI `createTheme`, any future TanStack
 * Table styling, etc.). Paired with `tokens.css` for CSS-variable consumers.
 * Keep both files in sync: change a value here, mirror it in `tokens.css`.
 *
 * Sync into app-local `src/lib/tokens/` copies with:
 *   node scripts/sync-tokens.mjs
 *
 * CI enforces drift via `scripts/sync-tokens.mjs --check`.
 */

// ─── Brand (navy — identity only: logo, wordmark, header chrome) ───
export const BRAND = "#0f4c81";
export const BRAND_HOVER = "#0b3d68";
export const BRAND_STRONG = "#1d293d";

// ─── Accent core (Evidara violet — the one action color: CTAs, active states, links, focus) ───
export const ACCENT_CORE = "#6246D9";
export const ACCENT_CORE_FOREGROUND = "#fffdf8";
export const ACCENT_CORE_SUBTLE = "rgba(98, 70, 217, 0.14)";
export const ACCENT_CORE_MUTED = "rgba(98, 70, 217, 0.22)";

// ─── Surfaces ───
export const SURFACE_PAGE = "#e4e9ef";
export const SURFACE_PANEL = "#f8fafc";
export const SURFACE_INPUT = "#f1f5f9";

// ─── Interactive (violet-tinted) ───
export const INTERACTIVE_ACCENT_SUBTLE = "rgba(98, 70, 217, 0.08)";
export const INTERACTIVE_ACCENT_MUTED = "rgba(98, 70, 217, 0.14)";

// ─── Focus ring ───
export const FOCUS_RING = "rgba(98, 70, 217, 0.24)";

// ─── Foreground / border (neutral text + dividers) ───
//
// Foreground ladder: --foreground (1.0) > MUTED (0.72) > SUBTLE (0.56) >
// FAINT (0.40) > GHOST (0.30). Pick by role, not exact opacity.
// Border ladder: BORDER_FAINT (0.08) < BORDER (0.12) < BORDER_STRONG (0.20).
export const FOREGROUND = "#1d293d";
export const FOREGROUND_MUTED = "rgba(29, 41, 61, 0.72)";
export const FOREGROUND_SUBTLE = "rgba(29, 41, 61, 0.56)";
export const FOREGROUND_FAINT = "rgba(29, 41, 61, 0.40)";
export const FOREGROUND_GHOST = "rgba(29, 41, 61, 0.30)";
// Secondary metadata text; WCAG AA on SURFACE_PAGE (6.03) + SURFACE_PANEL (7.04).
export const TEXT_META = "#46595e";
export const TEXT_META_DARK = "#b7b7b7";
export const BORDER_FAINT = "rgba(29, 41, 61, 0.08)";
export const BORDER = "rgba(29, 41, 61, 0.12)";
export const BORDER_STRONG = "rgba(29, 41, 61, 0.20)";

// ─── Attention (warm highlight, distinct from brand) ───
export const ATTENTION = "#92400e";
export const ATTENTION_SUBTLE = "#fef3c7";
export const ATTENTION_BORDER = "#fde68a";

// ─── Status ───
export const STATUS_HEALTHY = "#166534";
export const STATUS_HEALTHY_SUBTLE = "#f0fdf4";
export const STATUS_DEGRADED = "#92400e";
export const STATUS_DEGRADED_SUBTLE = "#fffbeb";
export const STATUS_CRITICAL = "#991b1b";
export const STATUS_CRITICAL_SUBTLE = "#fef2f2";
export const STATUS_NEUTRAL = "#525252";
export const STATUS_NEUTRAL_SUBTLE = "#f5f5f5";
export const STATUS_INFO = "#1e40af";
export const STATUS_INFO_SUBTLE = "#eff6ff";

// ─── Elevation ───
export const SHADOW_CARD = "0 1px 3px rgba(15, 76, 129, 0.08), 0 1px 2px rgba(15, 76, 129, 0.04)";
export const SHADOW_CARD_HOVER =
  "0 6px 18px rgba(15, 76, 129, 0.10), 0 2px 6px rgba(15, 76, 129, 0.06)";
export const SHADOW_PANEL = "0 20px 48px rgba(15, 23, 42, 0.08)";
export const SHADOW_SHELL = "0 18px 56px rgba(15, 23, 42, 0.08)";
export const SHADOW_RING_ACCENT = "inset 0 0 0 1px rgba(98, 70, 217, 0.18)";
export const SHADOW_RING_SUBTLE = "inset 0 0 0 1px rgba(15, 23, 42, 0.06)";

// ─── Motion ───
export const MOTION_DURATION_SHORT = "150ms";
export const MOTION_DURATION_MEDIUM = "200ms";
export const MOTION_EASING_STANDARD = "cubic-bezier(0.4, 0, 0.2, 1)";

// ─── Font weights ───
export const FONT_WEIGHT_REGULAR = 400;
export const FONT_WEIGHT_MEDIUM = 500;
export const FONT_WEIGHT_SEMIBOLD = 600;
export const FONT_WEIGHT_BOLD = 700;

// ─── Radii (base matches shadcn `--radius`; multipliers derived in CSS) ───
export const RADIUS_BASE = "0.625rem";
export const RADIUS_PILL = "9999px";
