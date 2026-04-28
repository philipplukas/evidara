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
 * not a CSS variable, so we read the literals here. Dark-mode variants
 * exist in tokens.css; admin doesn't switch to dark mode today, so the
 * light values are sufficient.
 */

import {
  ACCENT_CORE,
  ACCENT_CORE_FOREGROUND,
  STATUS_CRITICAL,
  STATUS_DEGRADED,
  STATUS_INFO,
} from "@evidara/tokens";
import { createTheme } from "@mui/material/styles";

export const adminMuiTheme = createTheme({
  palette: {
    primary: { main: ACCENT_CORE, contrastText: ACCENT_CORE_FOREGROUND },
    success: { main: ACCENT_CORE, contrastText: ACCENT_CORE_FOREGROUND },
    error: { main: STATUS_CRITICAL },
    warning: { main: STATUS_DEGRADED },
    info: { main: STATUS_INFO },
  },
});
