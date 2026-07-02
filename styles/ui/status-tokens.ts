/**
 * Status-level token map for the shared `StatusBadge` primitive.
 *
 * Co-located with `StatusBadge.tsx` in `@evidara/ui` so both surfaces
 * (`legal-search/frontend` and `platform-control/admin`) consume the same
 * `StatusLevel` vocabulary and the same icon + Tailwind-class wiring. The
 * Tailwind utilities below resolve through the `@theme inline` block in each
 * surface's `globals.css`, which maps `--color-status-*` onto the shared
 * CSS custom properties from `styles/tokens/tokens.css`. So a primitive that
 * uses these utilities stays token-bound on both surfaces — see
 * `docs/adr/0027-workspace-admin-visual-language.md`.
 */

import { AlertTriangle, CheckCircle, Info, MinusCircle, XCircle } from "lucide-react";
import type { ComponentType } from "react";

export type StatusLevel = "healthy" | "degraded" | "critical" | "neutral" | "info";

export interface StatusTokens {
  color: string;
  subtleBg: string;
  icon: ComponentType<{ className?: string }>;
  defaultLabel: string;
}

export const STATUS_TOKEN_MAP: Record<StatusLevel, StatusTokens> = {
  healthy: {
    color: "text-status-healthy",
    subtleBg: "bg-status-healthy-subtle",
    icon: CheckCircle,
    defaultLabel: "Healthy",
  },
  degraded: {
    color: "text-status-degraded",
    subtleBg: "bg-status-degraded-subtle",
    icon: AlertTriangle,
    defaultLabel: "Degraded",
  },
  critical: {
    color: "text-status-critical",
    subtleBg: "bg-status-critical-subtle",
    icon: XCircle,
    defaultLabel: "Critical",
  },
  neutral: {
    color: "text-status-neutral",
    subtleBg: "bg-status-neutral-subtle",
    icon: MinusCircle,
    defaultLabel: "Neutral",
  },
  info: {
    color: "text-status-info",
    subtleBg: "bg-status-info-subtle",
    icon: Info,
    defaultLabel: "Info",
  },
};
